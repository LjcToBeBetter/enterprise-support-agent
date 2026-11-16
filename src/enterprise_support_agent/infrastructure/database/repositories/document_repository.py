"""
document_repository.py

主要功能：
    集中处理KnowledgeDocument表的数据库操作。

主要部件：
    DocumentRepository：
        创建文档元数据；
        后续还会加入查询、分页和删除方法。

Repository只负责PostgreSQL中的文档元数据，
不负责上传或删除RustFS中的文件。
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.models.knowledge_document import (
    KnowledgeDocument,
)

from sqlalchemy import select,func

from enterprise_support_agent.application.documents.document_enums import (
    DocumentStatus,
)


class DocumentRepository:
    """知识库文档数据访问对象。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        保存当前请求使用的数据库Session。

        Service和Repository共享同一个Session，
        因此数据库操作属于同一个事务。
        """

        self.session = session

    async def create(
        self,
        document_id: UUID,
        organization_id: UUID,
        uploaded_by_user_id: UUID,
        original_filename: str,
        content_type: str,
        file_size_bytes: int,
        object_key: str,
        checksum_sha256: str,
    ) -> KnowledgeDocument:
        """
        创建文档元数据，但暂时不提交事务。

        接收：
            document_id：
                Service提前生成的文档ID。

            organization_id：
                文档所属组织。

            uploaded_by_user_id：
                上传文档的用户。

            original_filename：
                用户上传时的原文件名。

            content_type：
                文件MIME类型。

            file_size_bytes：
                文件大小，单位为字节。

            object_key：
                文件在对象存储中的位置。

            checksum_sha256：
                文件内容的SHA-256摘要。

        返回：
            创建后的KnowledgeDocument ORM对象。
        """

        # 创建对应knowledge_documents表的ORM对象。
        document = KnowledgeDocument(
            # 使用Service提前生成的UUID。
            #
            # 因为文件上传前就需要这个ID
            # 来构造唯一object_key。
            id=document_id,
            organization_id=organization_id,
            uploaded_by_user_id=(
                uploaded_by_user_id
            ),
            original_filename=original_filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            object_key=object_key,
            checksum_sha256=checksum_sha256,

            # status、version和error_message没有传入。
            #
            # status使用模型默认值pending；
            # version使用模型默认值1；
            # error_message默认为None。
        )

        # 把ORM对象加入当前Session。
        self.session.add(
            document
        )

        # 将INSERT发送给PostgreSQL，
        # 但事务还没有永久提交。
        await self.session.flush()

        # 重新读取数据库生成的默认字段，
        # 例如status、version和时间字段。
        await self.session.refresh(
            document
        )

        return document
    async def get_by_id_and_organization(
        self,
        document_id: UUID,
        organization_id: UUID,
    ) -> KnowledgeDocument | None:
        """
        根据文档ID和组织ID查询文档元数据。

        接收：
            document_id：需要查询的文档ID；
            organization_id：当前组织ID。

        返回：
            找到时返回KnowledgeDocument ORM对象；
            找不到时返回None。
        """

        # 同时限制文档ID和组织ID。
        #
        # 即使用户知道其他组织的document_id，
        # 也不能通过当前组织的接口查询出来。
        statement = select(
            KnowledgeDocument
        ).where(
            KnowledgeDocument.id
            == document_id,

            KnowledgeDocument.organization_id
            == organization_id,
        )

        # 将SELECT发送给PostgreSQL执行。
        result = await self.session.execute(
            statement
        )

        # 找到一条记录时返回ORM对象；
        # 没有符合两个条件的记录时返回None。
        return result.scalar_one_or_none()

    async def list_page_by_organization(
        self,
        organization_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[
        list[KnowledgeDocument],
        int,
    ]:
        """
        分页查询指定组织的知识库文档。

        接收：
            organization_id：当前组织ID；
            offset：跳过前面多少条记录；
            limit：本次最多返回多少条记录。

        返回：
            当前页的文档ORM对象列表；
            当前组织的文档总数。
        """

        # 第一条查询只统计当前组织有多少份文档。
        count_statement = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.organization_id
                == organization_id
            )
        )

        # scalar()执行查询并直接取得COUNT数字。
        total = await self.session.scalar(
            count_statement
        )

        # 第二条查询取得当前页的具体文档。
        statement = (
            select(KnowledgeDocument)

            # 只查询当前组织的文档。
            .where(
                KnowledgeDocument.organization_id
                == organization_id
            )

            # 最新上传的文档排在前面。
            .order_by(
                KnowledgeDocument.created_at.desc()
            )

            # 跳过前面指定数量的记录。
            .offset(offset)

            # 限制本次最多返回多少条记录。
            .limit(limit)
        )

        # 执行查询并取得KnowledgeDocument对象序列。
        result = await self.session.scalars(
            statement
        )

        documents = list(
            result.all()
        )

        return documents, int(total or 0)

    async def delete(
        self,
        document: KnowledgeDocument,
    ) -> None:
        """
        删除一条文档元数据，但暂时不提交事务。

        接收：
            document：
                从数据库查询到的KnowledgeDocument
                ORM对象。

        返回：
            没有返回值。

        注意：
            这里只删除PostgreSQL中的元数据；
            RustFS中的文件由Service负责删除。
        """

        # 告诉Session准备删除这条文档记录。
        await self.session.delete(
            document
        )

        # 将DELETE语句发送给PostgreSQL，
        # 但事务还没有commit，仍然可以rollback。
        await self.session.flush()

    async def get_by_checksum_and_organization(
        self,
        organization_id: UUID,
        checksum_sha256: str,
    ) -> KnowledgeDocument | None:
        """
        根据组织ID和SHA-256摘要查询文档。

        接收：
            organization_id：
                当前组织ID。

            checksum_sha256：
                上传文件内容的SHA-256摘要。

        返回：
            找到相同内容时返回已有文档ORM对象；
            没有相同内容时返回None。

        主要用于：
            防止同一组织重复上传内容完全相同的文件。
        """

        statement = select(
            KnowledgeDocument
        ).where(
            # 只在当前组织范围内检查重复。
            KnowledgeDocument.organization_id
            == organization_id,

            # SHA-256相同，说明文件内容相同。
            KnowledgeDocument.checksum_sha256
            == checksum_sha256,
        )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def update_processing_status(
            self,
            document: KnowledgeDocument,
            status: DocumentStatus,
            error_message: str | None = None,
    ) -> KnowledgeDocument:
        """
        修改文档的处理状态。

        接收：
            document：
                需要修改的KnowledgeDocument ORM记录。

            status：
                需要修改成的文档状态。

            error_message：
                处理失败时需要保存的错误信息。
                正常处理时传入None。

        返回：
            更新后的KnowledgeDocument ORM对象。

        注意：
            这个方法只执行flush，不执行commit。
            是否提交事务由Service决定。
        """

        # document是从数据库查询出来的ORM对象。
        #
        # 修改它的属性后，SQLAlchemy会记录这个变化。
        document.status = status.value

        # 正常处理时error_message是None；
        # 处理失败时保存简短的错误原因。
        document.error_message = error_message

        # flush()让SQLAlchemy把UPDATE语句发送给PostgreSQL。
        #
        # 但当前事务还没有永久提交，
        # 如果后面发生异常，仍然可以rollback。
        await self.session.flush()

        # refresh()从数据库重新读取这条记录，
        # 保证document中的状态和更新时间是最新值。
        await self.session.refresh(
            document
        )

        return document