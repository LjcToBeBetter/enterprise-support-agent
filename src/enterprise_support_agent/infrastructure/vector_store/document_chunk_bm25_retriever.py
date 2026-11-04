"""
知识库文本块BM25检索器。

这个模块负责：

1. 接收用户的原始问题；
2. 使用Qdrant的content全文索引执行BM25检索；
3. 使用organization_id隔离不同组织的数据；
4. 返回命中的文本块ID和BM25分数。
"""

from dataclasses import dataclass
from uuid import UUID

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    TextQuery,
)

from enterprise_support_agent.config import (
    settings,
)
from enterprise_support_agent.infrastructure.vector_store.collection_manager import (
    QdrantCollectionManager,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


@dataclass(
    frozen=True,
    slots=True,
)
class Bm25SearchHit:
    """Qdrant BM25检索命中的一条文本块结果。"""

    # 命中的Qdrant Point ID。
    # 它和PostgreSQL文本块ID使用同一个UUID。
    chunk_id: UUID

    # Qdrant根据关键词计算出的BM25分数。
    # 分数越高，表示关键词相关性通常越强。
    score: float


class DocumentChunkBm25Retriever:
    """负责从Qdrant全文索引召回关键词相关文本块。"""

    def __init__(self) -> None:
        """创建文本块BM25检索器。"""

        self.collection_manager = (
            QdrantCollectionManager()
        )

    async def search(
        self,
        organization_id: UUID,
        query: str,
        top_k: int = 20,
    ) -> list[Bm25SearchHit]:
        """搜索当前组织中关键词最相关的文本块。"""

        # 删除问题前后的空格。
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "BM25检索问题不能为空"
            )

        if not 1 <= top_k <= 100:
            raise ValueError(
                "BM25检索top_k必须在1到100之间"
            )

        # 确保Collection和content全文索引存在。
        await (
            self.collection_manager
            .ensure_document_chunks_collection()
        )

        # TextQuery表示：
        # 不使用向量执行查询，
        # 而是使用全文索引对原始文本进行BM25排名。
        query_response = (
            await qdrant_client.query_points(
                collection_name=(
                    settings.qdrant_collection_name
                ),
                query=TextQuery(
                    text=normalized_query
                ),

                # using="content"表示查询的是
                # Payload中的content全文索引。
                using="content",

                # 只允许搜索当前组织的Point。
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="organization_id",
                            match=MatchValue(
                                value=str(
                                    organization_id
                                )
                            ),
                        )
                    ]
                ),
                limit=top_k,

                # 当前只需要Point ID和BM25分数。
                # 正文后面仍从PostgreSQL读取。
                with_payload=False,
                with_vectors=False,
            )
        )

        # Qdrant已经按照BM25分数从高到低排列。
        return [
            Bm25SearchHit(
                chunk_id=UUID(
                    str(point.id)
                ),
                score=float(
                    point.score
                ),
            )
            for point in query_response.points
        ]
