"""
document_service.py

主要功能：
    处理知识库文档相关的业务规则。

主要部件：
    DocumentService：
        检查组织权限；
        校验文件类型和大小；
        计算SHA-256摘要；
        防止重复上传；
        上传文件到S3兼容对象存储；
        将文档元数据保存到PostgreSQL。

本地对象存储使用RustFS。
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.common.exceptions import (
    DocumentFileTooLargeError,
    DuplicateDocumentError,
    EmptyDocumentFileError,
    ObjectStorageUnavailableError,
    OrganizationAccessDeniedError,
    UnsupportedDocumentTypeError,
    DocumentNotFoundError
)
from enterprise_support_agent.application.identity.organization_roles import (
    OrganizationRole,
)
from enterprise_support_agent.config import settings
from enterprise_support_agent.infrastructure.database.models.knowledge_document import (
    KnowledgeDocument,
)
from enterprise_support_agent.infrastructure.database.repositories.document_repository import (
    DocumentRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)
from enterprise_support_agent.infrastructure.storage.object_storage import (
    object_storage,
)

# 为什么之前的 Service没有logger
# 之前 Service发生错误后，通常会继续向上抛：
# 异常会继续到达请求日志中间件或统一异常处理器，所以错误不会消失。
# 这里有被转换或被压住的底层错误，所以必须用 logger 把详情记录下来。例如：
# except Exception:
#     logger.exception(
#         "数据库保存失败，并且对象存储补偿删除失败"
#     )
logger = logging.getLogger(__name__)


# 允许上传的扩展名以及对应MIME类型。
#
# key：
#     文件扩展名。
#
# value：
#     这个扩展名允许使用的MIME类型集合。
ALLOWED_DOCUMENT_TYPES: dict[
    str,
    set[str],
] = {
    ".pdf": {
        "application/pdf",
    },
    ".docx": {
        (
            "application/vnd.openxmlformats-"
            "officedocument.wordprocessingml.document"
        ),
    },
    ".txt": {
        "text/plain",
    },
    ".md": {
        "text/markdown",
        "text/plain",
    },
}


class DocumentService:
    """知识库文档业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        创建文档业务服务。

        session：
            当前请求使用的AsyncSession对象。
        """

        self.session = session

        # 负责knowledge_documents表的数据库操作。
        self.document_repository = (
            DocumentRepository(
                session=session
            )
        )

        # 负责查询当前用户在组织中的身份。
        self.membership_repository = (
            MembershipRepository(
                session=session
            )
        )

    async def upload_document(
        self,
        organization_id: UUID,
        uploaded_by_user_id: UUID,
        original_filename: str,
        content_type: str,
        file_content: bytes,
    ) -> KnowledgeDocument:
        """
        校验并上传一份知识库文档。

        接收：
            organization_id：
                文档所属组织。

            uploaded_by_user_id：
                当前登录用户ID。

            original_filename：
                用户上传时的原始文件名。

            content_type：
                上传文件的MIME类型。

            file_content：
                上传文件的二进制内容。

        返回：
            创建完成的KnowledgeDocument ORM对象。

        权限：
            只有support和admin可以上传知识库文档。
        """

        # 查询当前用户在组织中的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=uploaded_by_user_id,
            )
        )

        # 不属于组织，或者只是普通员工，
        # 都不能上传企业知识库文档。
        if (
            membership is None
            or membership.role
            not in (
                OrganizationRole.SUPPORT,
                OrganizationRole.ADMIN,
            )
        ):
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # Path(...).name只保留最后的文件名，
        # 去掉客户端可能携带的目录部分。
        #
        # 例如：
        # C:\Users\ljc\manual.pdf
        # 最终只保留manual.pdf。
        safe_filename = Path(
            original_filename
        ).name

        # suffix取得文件扩展名，
        # lower()统一转换成小写。
        file_extension = Path(
            safe_filename
        ).suffix.lower()

        # 根据扩展名查找允许的MIME类型。
        allowed_content_types = (
            ALLOWED_DOCUMENT_TYPES.get(
                file_extension
            )
        )

        # 扩展名不支持，或者MIME类型不匹配，
        # 都拒绝上传。
        if (
            allowed_content_types is None
            or content_type
            not in allowed_content_types
        ):
            raise UnsupportedDocumentTypeError(
                content_type
            )

        # len(bytes)取得文件内容大小，单位为字节。
        file_size_bytes = len(
            file_content
        )

        # 空文件不能进入知识库。
        if file_size_bytes == 0:
            raise EmptyDocumentFileError()

        # 文件超过配置中的最大大小时拒绝上传。
        if (
            file_size_bytes
            > settings.document_max_file_size_bytes
        ):
            raise DocumentFileTooLargeError(
                file_size_bytes=file_size_bytes,
                max_size_bytes=(
                    settings
                    .document_max_file_size_bytes
                ),
            )

        # 根据整个文件内容计算SHA-256摘要。
        #
        # hexdigest()返回64位十六进制字符串。
        checksum_sha256 = hashlib.sha256(
            file_content
        ).hexdigest()

        # 检查当前组织是否已经上传过
        # 内容完全相同的文件。
        existing_document = (
            await self.document_repository
            .get_by_checksum_and_organization(
                organization_id=organization_id,
                checksum_sha256=checksum_sha256,
            )
        )

        if existing_document is not None:
            raise DuplicateDocumentError(
                existing_document_id=(
                    existing_document.id
                )
            )

        # 提前生成文档ID，
        # 因为上传文件前就需要它构造object_key。
        document_id = uuid4()

        # 文件在Bucket中的唯一存储位置。
        object_key = (
            f"organizations/{organization_id}/"
            f"documents/{document_id}/"
            f"{safe_filename}"
        )

        try:
            # boto3是同步客户端。
            #
            # to_thread()把上传操作放到工作线程，
            # 避免阻塞FastAPI事件循环。

            #  asyncio.to_thread() 的参数设计就是：
            # asyncio.to_thread(
            #     要执行的方法,
            #     传给这个方法的位置参数,
            #     传给这个方法的关键字参数,
            # )
            await asyncio.to_thread(
                object_storage.upload_bytes,
                object_key=object_key,
                file_content=file_content,
                content_type=content_type,
            )

        except (
            BotoCoreError,
            ClientError,
            OSError,
        ) as error:
            # 记录底层错误供开发人员排查，
            # 但不把内部错误直接返回给客户端。
            logger.exception(
                "上传文档到对象存储失败"
            )

            raise ObjectStorageUnavailableError() from error

        try:
            # 文件上传成功后，
            # 在PostgreSQL中创建文档元数据。
            document = (
                await self.document_repository.create(
                    document_id=document_id,
                    organization_id=organization_id,
                    uploaded_by_user_id=(
                        uploaded_by_user_id
                    ),
                    original_filename=safe_filename,
                    content_type=content_type,
                    file_size_bytes=file_size_bytes,
                    object_key=object_key,
                    checksum_sha256=(
                        checksum_sha256
                    ),
                )
            )

            # 元数据创建成功后提交事务。
            await self.session.commit()

            return document

        except Exception:
            # 数据库写入失败时先回滚事务。
            await self.session.rollback()

            # 文件已经上传成功，
            # 但数据库元数据保存失败。
            #
            # 尝试删除已经上传的文件，
            # 避免对象存储中出现孤立文件。
            try:
                await asyncio.to_thread(
                    object_storage.delete_object,
                    object_key=object_key,
                )

            except Exception:
                # 补偿删除失败只记录日志，
                # 不能覆盖最初的数据库异常。
                logger.exception(
                    "数据库保存失败，并且对象存储补偿删除失败"
                )

            # 将最初的数据库异常继续向上抛出。
            raise
    async def get_document(
        self,
        organization_id: UUID,
        document_id: UUID,
        current_user_id: UUID,
    ) -> KnowledgeDocument:
        """
        查询指定组织中的一份文档元数据。

        接收：
            organization_id：当前组织ID；
            document_id：需要查询的文档ID；
            current_user_id：当前登录用户ID。

        返回：
            有权限访问的KnowledgeDocument ORM对象。

        权限：
            当前用户只要属于该组织，就可以查看。
        """

        # 查询当前用户是否属于该组织。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        if membership is None:
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 同时根据组织ID和文档ID查询，
        # 防止查询其他组织的文档。
        document = (
            await self.document_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                document_id=document_id,
            )
        )

        if document is None:
            raise DocumentNotFoundError(
                organization_id=organization_id,
                document_id=document_id,
            )

        return document

    async def list_documents(
        self,
        organization_id: UUID,
        current_user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[
        list[KnowledgeDocument],
        int,
        int,
    ]:
        """
        分页查询指定组织的知识库文档。

        接收：
            organization_id：当前组织ID；
            current_user_id：当前登录用户ID；
            page：当前页码；
            page_size：每页记录数量。

        返回：
            当前页文档列表；
            文档总数；
            总页数。

        权限：
            当前用户只要属于该组织，就可以查看。
        """

        # 查询当前用户是否属于该组织。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        if membership is None:
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 把页码转换成数据库需要跳过的记录数量。
        offset = (
            page - 1
        ) * page_size

        documents, total = (
            await self.document_repository
            .list_page_by_organization(
                organization_id=organization_id,
                offset=offset,
                limit=page_size,
            )
        )

        # 向上取整计算总页数。
        total_pages = (
            total + page_size - 1
        ) // page_size

        return (
            documents,
            total,
            total_pages,
        )

    async def delete_document(
        self,
        organization_id: UUID,
        document_id: UUID,
        current_user_id: UUID,
    ) -> None:
        """
        删除一份知识库文档。

        接收：
            organization_id：当前组织ID；
            document_id：需要删除的文档ID；
            current_user_id：当前登录用户ID。

        返回：
            没有返回值。

        权限：
            只有组织admin可以删除知识库文档。
        """

        # 查询当前用户在组织中的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 用户不属于组织，或者不是管理员，
        # 都不能删除知识库文档。
        if (
            membership is None
            or membership.role
            != OrganizationRole.ADMIN
        ):
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 根据组织ID和文档ID查询元数据。
        document = (
            await self.document_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                document_id=document_id,
            )
        )

        if document is None:
            raise DocumentNotFoundError(
                organization_id=organization_id,
                document_id=document_id,
            )

        # 在删除数据库记录之前保存object_key。
        #
        # 后面需要根据它删除RustFS中的文件。
        object_key = document.object_key

        try:
            # 先把数据库记录标记为待删除并执行DELETE，
            # 但目前还没有commit，可以rollback。
            await self.document_repository.delete(
                document
            )

            # boto3是同步客户端，
            # 使用工作线程删除RustFS对象。
            await asyncio.to_thread(
                object_storage.delete_object,
                object_key=object_key,
            )

            # PostgreSQL和RustFS操作都成功后，
            # 永久提交数据库删除。
            await self.session.commit()

        except (
            BotoCoreError,
            ClientError,
            OSError,
        ) as error:
            # RustFS删除失败时，
            # 回滚尚未提交的数据库删除。
            #
            # 这样文档元数据仍然存在，
            # 不会出现数据库已删除但文件仍存在的情况。
            await self.session.rollback()

            logger.exception(
                "从对象存储删除文档失败"
            )

            raise ObjectStorageUnavailableError() from error

        except Exception:
            # 其他数据库错误也回滚事务。
            await self.session.rollback()
            raise

    async def download_document(
        self,
        organization_id: UUID,
        document_id: UUID,
        current_user_id: UUID,
    ) -> tuple[
        bytes,
        str,
        str,
    ]:
        """
        下载指定组织中的文档文件。

        接收：
            organization_id：当前组织ID；
            document_id：需要下载的文档ID；
            current_user_id：当前登录用户ID。

        返回：
            文件二进制内容；
            原始文件名；
            文件MIME类型。

        权限：
            当前用户只要属于该组织，就可以下载。
        """

        # 复用get_document()已有的业务逻辑：
        #
        # 1. 检查当前用户是否属于组织；
        # 2. 检查文档是否属于当前组织；
        # 3. 文档不存在时抛出明确异常。
        document = await self.get_document(
            organization_id=organization_id,
            document_id=document_id,
            current_user_id=current_user_id,
        )

        try:
            # boto3是同步客户端，
            # 把文件读取操作交给工作线程执行。
            file_content = await asyncio.to_thread(
                object_storage.download_bytes,
                object_key=document.object_key,
            )

        except (
            BotoCoreError,
            ClientError,
            OSError,
        ) as error:
            logger.exception(
                "从对象存储下载文档失败"
            )

            raise ObjectStorageUnavailableError() from error

        # Router需要文件内容、文件名和MIME类型，
        # 才能构造浏览器下载响应。
        return (
            file_content,
            document.original_filename,
            document.content_type,
        )