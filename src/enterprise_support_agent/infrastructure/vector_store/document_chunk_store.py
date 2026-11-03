"""
文档文本块向量存储。

主要负责：

1. 接收PostgreSQL中的DocumentChunk；
2. 调用Embedding模型批量生成向量；
3. 清理Qdrant中的旧版本向量；
4. 把新向量和Payload写入Qdrant。
"""

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from enterprise_support_agent.config import (
    settings,
)
from enterprise_support_agent.infrastructure.database.models.document_chunk import (
    DocumentChunk,
)
from enterprise_support_agent.infrastructure.embeddings.client import (
    embedding_model,
)
from enterprise_support_agent.infrastructure.vector_store.collection_manager import (
    QdrantCollectionManager,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


class DocumentChunkVectorStore:
    """负责DocumentChunk的向量生成和Qdrant入库。"""

    def __init__(self) -> None:
        """创建文本块向量存储。"""

        # 用于确保Collection和Payload索引已经存在。
        self.collection_manager = (
            QdrantCollectionManager()
        )

    async def index_chunks(
        self,
        chunks: list[DocumentChunk],
    ) -> int:
        """
        批量向量化并保存文本块。

        返回：
            成功写入Qdrant的Point数量。
        """

        if not chunks:
            raise ValueError(
                "不能向量化空文本块列表"
            )

        # 所有文本块都应该属于同一文档版本。
        first_chunk = chunks[0]

        document_id = first_chunk.document_id
        document_version = (
            first_chunk.document_version
        )
        organization_id = (
            first_chunk.organization_id
        )

        # 检查传入的数据有没有混入其他文档。
        for chunk in chunks:
            if (
                chunk.document_id != document_id
                or chunk.document_version
                != document_version
                or chunk.organization_id
                != organization_id
            ):
                raise ValueError(
                    "一次只能向量化同一组织、"
                    "同一文档、同一版本的文本块"
                )

        # 确保Collection已经存在且配置正确。
        await (
            self.collection_manager
            .ensure_document_chunks_collection()
        )

        # 取出所有文本块正文。
        texts = [
            chunk.content
            for chunk in chunks
        ]

        # aembed_documents()批量生成文本向量。
        #
        # 返回结构类似：
        # [
        #     [第一个文本块的1024维向量],
        #     [第二个文本块的1024维向量],
        # ]
        vectors = (
            await embedding_model.aembed_documents(
                texts
            )
        )

        # 每个文本块都必须对应一个向量。
        if len(vectors) != len(chunks):
            raise RuntimeError(
                "Embedding返回的向量数量"
                "与文本块数量不一致"
            )

        # 在删除旧向量之前，
        # 先检查所有新向量维度。
        #
        # 这样维度错误时不会先把旧数据删除。
        for vector in vectors:
            if (
                len(vector)
                != settings.qdrant_vector_size
            ):
                raise RuntimeError(
                    "Embedding向量维度不匹配："
                    f"实际为{len(vector)}，"
                    f"配置为"
                    f"{settings.qdrant_vector_size}"
                )

        # 删除同一文档、同一版本的旧Point。
        #
        # 第一次入库时没有旧Point，
        # 删除0条不会报错。
        await qdrant_client.delete(
            collection_name=(
                settings.qdrant_collection_name
            ),
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(
                            value=str(document_id)
                        ),
                    ),
                    FieldCondition(
                        key="document_version",
                        match=MatchValue(
                            value=document_version
                        ),
                    ),
                ]
            ),

            # 等待删除完成后再继续写入。
            wait=True,
        )

        # 把每个文本块和对应向量
        # 转换成Qdrant Point。
        points: list[PointStruct] = []

        for chunk, vector in zip(
            chunks,
            vectors,
            strict=True,
        ):
            point = PointStruct(
                # 使用PostgreSQL文本块ID作为Point ID。
                #
                # 这样Qdrant检索返回Point ID后，
                # 可以回到PostgreSQL查询原始文本块。
                id=str(chunk.id),

                # Embedding模型生成的1024维向量。
                vector=vector,

                # Payload保存过滤和定位需要的业务信息。
                payload={
                    "organization_id": str(
                        chunk.organization_id
                    ),
                    "document_id": str(
                        chunk.document_id
                    ),
                    "document_version": (
                        chunk.document_version
                    ),
                    "page_number": (
                        chunk.page_number
                    ),
                    "chunk_index": (
                        chunk.chunk_index
                    ),
                    "content_hash": (
                        chunk.content_hash
                    ),
                },
            )

            points.append(
                point
            )

        # upsert表示：
        #
        # Point ID不存在：
        #     新增Point。
        #
        # Point ID已经存在：
        #     更新该Point的向量和Payload。
        await qdrant_client.upsert(
            collection_name=(
                settings.qdrant_collection_name
            ),
            points=points,

            # 等待Qdrant写入完成后再返回。
            wait=True,
        )

        return len(points)