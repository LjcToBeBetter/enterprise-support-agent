"""
知识库文档处理服务。

这个Service负责：

1. 从PostgreSQL查询文档元数据；
2. 根据object_key从RustFS读取原文件；
3. 根据文件类型调用对应解析器；
4. 将正文切块并保存到PostgreSQL；
5. 生成向量并写入Qdrant；
6. 记录完整处理状态。

当前先实现PDF解析，后面再加入Word、TXT和Markdown。
"""

import asyncio
import logging
from uuid import UUID

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.common.exceptions import (
    DocumentNotFoundError,
    ObjectStorageUnavailableError,
    UnsupportedDocumentTypeError,
)
from enterprise_support_agent.infrastructure.database.repositories.document_repository import (
    DocumentRepository,
)
from enterprise_support_agent.infrastructure.parsing.pdf_parser import (
    ParsedPdfDocument,
    PdfParser,
    PdfParsingError,
)
from enterprise_support_agent.infrastructure.storage.object_storage import (
    object_storage,
)
from enterprise_support_agent.application.documents.document_enums import (
    DocumentStatus,
)
from enterprise_support_agent.application.documents.document_chunker import (
    DocumentChunker,
)
from enterprise_support_agent.infrastructure.database.models.document_chunk import (
    DocumentChunk,
)
from enterprise_support_agent.infrastructure.database.repositories.document_chunk_repository import (
    DocumentChunkRepository,
)
from enterprise_support_agent.infrastructure.vector_store.document_chunk_store import (
    DocumentChunkVectorStore,
)

# 创建当前模块使用的日志对象。
#
# __name__表示当前模块名称：
# enterprise_support_agent.application.documents.document_processing_service
#
# 当RustFS下载失败时，可以通过logger记录底层错误。
logger = logging.getLogger(
    __name__
)


class DocumentProcessingService:
    """负责读取并解析知识库文档。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        创建文档处理服务。

        session：
            当前业务使用的异步数据库会话，
            用于查询knowledge_documents表。
        """

        # 保存数据库Session，
        # 后续更新处理状态时还会使用。
        self.session = session

        # Repository专门负责查询文档元数据。
        self.document_repository = DocumentRepository(
            session=session
        )

        # 创建PDF解析器。
        #
        # 它负责把PDF的bytes转换成正文文本。
        self.pdf_parser = PdfParser()

        # 负责把解析后的长正文切成多个小块。
        self.document_chunker = DocumentChunker(
            chunk_size=800,
            chunk_overlap=120,
        )

        # 负责把文本块保存到document_chunks表。
        self.document_chunk_repository = (
            DocumentChunkRepository(
                session=session
            )
        )

        # 负责为文本块生成向量，
        # 并把向量Point写入Qdrant。
        self.document_chunk_vector_store = (
            DocumentChunkVectorStore()
        )

    async def process_document(
        self,
        organization_id: UUID,
        document_id: UUID,
    ) -> ParsedPdfDocument:
        """
        从RustFS读取并解析指定PDF。

        处理状态：

            开始处理：
                pending → processing

            解析成功：
                processing → parsed

            切块成功：
                parsed → chunked

            向量入库成功：
                chunked → ready

            任一阶段失败：
                当前状态 → failed
        """

        # 根据组织ID和文档ID查询文档记录。
        document = (
            await self.document_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                document_id=document_id,
            )
        )

        # 数据库中不存在这份文档。
        if document is None:
            raise DocumentNotFoundError(
                document_id
            )

        # 当前阶段只支持解析PDF。
        if document.content_type != "application/pdf":
            raise UnsupportedDocumentTypeError(
                document.content_type
            )

        # 先把object_key保存到普通变量中。
        #
        # object_key表示文件在RustFS中的位置，
        # 后面需要用它下载原始PDF。
        object_key = document.object_key

        # 把文档状态修改成processing。
        await self.document_repository.update_processing_status(
            document=document,
            status=DocumentStatus.PROCESSING,

            # 开始重新处理时，
            # 清除之前可能保存的错误信息。
            error_message=None,
        )

        # commit()把processing状态永久提交到数据库。
        #
        # 这样即使后面的PDF下载或解析失败，
        # 数据库也已经知道这份文档开始处理过。
        await self.session.commit()

        try:
            # object_storage.download_bytes()是同步方法。
            #
            # asyncio.to_thread()把同步下载交给工作线程，
            # 避免阻塞FastAPI的异步事件循环。
            file_content = await asyncio.to_thread(
                object_storage.download_bytes,
                object_key=object_key,
            )

            # 把PDF的bytes交给PDF解析器。
            parsed_document = self.pdf_parser.parse(
                file_content
            )

            # PDF可能是纯扫描件。
            #
            # 这种PDF虽然格式正常，
            # 但是pypdf无法提取任何文字。
            if not parsed_document.full_text.strip():
                raise PdfParsingError(
                    "PDF中没有可提取的正文，可能是扫描件"
                )

        except (
                BotoCoreError,
                ClientError,
                OSError,
        ) as error:
            # 从RustFS下载文件失败时，
            # 把文档状态修改成failed。
            await self.document_repository.update_processing_status(
                document=document,
                status=DocumentStatus.FAILED,
                error_message="从对象存储读取文档失败",
            )

            # 提交failed状态。
            await self.session.commit()

            # 在服务器日志中记录完整底层异常。
            logger.exception(
                "从RustFS读取待解析文档失败"
            )

            # 向上层抛出项目统一的对象存储异常。
            raise ObjectStorageUnavailableError() from error

        except PdfParsingError as error:
            # PDF格式损坏、无法读取或者没有正文时，
            # 把文档状态修改成failed。
            await self.document_repository.update_processing_status(
                document=document,
                status=DocumentStatus.FAILED,

                # str(error)取得异常中的文字说明。
                error_message=str(error),
            )

            # 提交failed状态。
            await self.session.commit()

            logger.exception(
                "PDF文档解析失败"
            )

            # 继续把原来的PDF解析异常向上抛出。
            raise

        # PDF正文提取成功，
        # 先把状态修改成parsed。
        await self.document_repository.update_processing_status(
            document=document,
            status=DocumentStatus.PARSED,
            error_message=None,
        )

        await self.session.commit()

        try:
            # 把解析后的PDF正文切成多个小块。
            #
            # 返回的是PreparedDocumentChunk列表，
            # 还不是数据库ORM对象。
            prepared_chunks = (
                self.document_chunker.split_document(
                    parsed_document
                )
            )

            # 理论上有正文就应该能产生文本块。
            #
            # 如果没有产生任何文本块，
            # 说明切块过程存在异常。
            if not prepared_chunks:
                raise ValueError(
                    "文档切块后没有产生任何文本块"
                )

            # 把PreparedDocumentChunk普通数据对象
            # 转换成DocumentChunk ORM对象。
            #
            # ORM对象才能交给Session并写入数据库。
            chunk_models = [
                DocumentChunk(
                    organization_id=organization_id,
                    document_id=document.id,
                    document_version=document.version,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    character_count=(
                        chunk.character_count
                    ),
                    token_count=chunk.token_count,
                    content_hash=chunk.content_hash,
                )
                for chunk in prepared_chunks
            ]

            # 删除这个文档版本原来的文本块，
            # 然后批量加入这次新生成的文本块。
            await (
                self.document_chunk_repository
                .replace_document_version_chunks(
                    document_id=document.id,
                    document_version=document.version,
                    chunks=chunk_models,
                )
            )

            # 文本块已经写入当前数据库事务，
            # 把文档状态修改成chunked。
            await self.document_repository.update_processing_status(
                document=document,
                status=DocumentStatus.CHUNKED,
                error_message=None,
            )

            # 同时提交：
            # 1. 删除旧文本块；
            # 2. 插入新文本块；
            # 3. 状态修改为chunked。
            await self.session.commit()

        except Exception:
            # 如果切块或数据库写入失败，
            # 撤销当前事务中的删除、插入和状态修改。
            await self.session.rollback()

            # rollback以后重新查询文档，
            # 取得当前数据库中的最新ORM对象。
            failed_document = (
                await self.document_repository
                .get_by_id_and_organization(
                    organization_id=organization_id,
                    document_id=document_id,
                )
            )

            if failed_document is not None:
                # 记录处理失败状态。
                await (
                    self.document_repository
                    .update_processing_status(
                        document=failed_document,
                        status=DocumentStatus.FAILED,
                        error_message="文档文本切块失败",
                    )
                )

                await self.session.commit()

            logger.exception(
                "文档文本切块或保存失败"
            )

            # 继续把原来的异常向上抛出，
            # 让上层知道处理没有成功。
            raise

        # 向量化阶段必须放在切块try...except之外。
        #
        # 否则向量化异常向上抛出后，
        # 还会被切块异常处理再次捕获，
        # 最终把正确的失败原因覆盖成“切块失败”。
        try:
            # 重新从PostgreSQL查询刚刚提交的文本块。
            #
            # 这里使用数据库中的正式记录，
            # 确保每个文本块已经拥有可用的UUID主键。
            persisted_chunks = (
                await self.document_chunk_repository
                .list_by_document_version(
                    document_id=document.id,
                    document_version=document.version,
                )
            )

            if not persisted_chunks:
                raise RuntimeError(
                    "数据库中没有找到待向量化文本块"
                )

            # 完成：
            # 1. 批量调用Embedding模型；
            # 2. 得到1024维向量；
            # 3. 清理Qdrant中的旧Point；
            # 4. 写入新Point和Payload。
            indexed_point_count = (
                await self.document_chunk_vector_store
                .index_chunks(
                    persisted_chunks
                )
            )

            # 写入Qdrant的Point数量必须和
            # PostgreSQL文本块数量一致。
            if indexed_point_count != len(
                persisted_chunks
            ):
                raise RuntimeError(
                    "Qdrant写入数量与文本块数量不一致"
                )

            # 向量已经写入成功，
            # 文档现在可以参加知识库检索。
            await self.document_repository.update_processing_status(
                document=document,
                status=DocumentStatus.READY,
                error_message=None,
            )

            # 提交ready状态。
            await self.session.commit()

        except Exception:
            # 撤销当前尚未提交的数据库操作。
            await self.session.rollback()

            # rollback后重新查询文档ORM对象，
            # 避免继续使用可能已经失效的旧对象。
            failed_document = (
                await self.document_repository
                .get_by_id_and_organization(
                    organization_id=organization_id,
                    document_id=document_id,
                )
            )

            if failed_document is not None:
                # 向量化或Qdrant入库失败时，
                # 在PostgreSQL中记录失败状态。
                await (
                    self.document_repository
                    .update_processing_status(
                        document=failed_document,
                        status=DocumentStatus.FAILED,
                        error_message=(
                            "文本块向量化或Qdrant入库失败"
                        ),
                    )
                )

                await self.session.commit()

            logger.exception(
                "文本块向量化或Qdrant入库失败"
            )

            # 把原始异常继续抛给上层，
            # 让接口返回错误，而不是错误地返回204。
            raise

        return parsed_document
