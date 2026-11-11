"""
知识库文本块向量检索器。

这个模块负责：

1. 把用户问题转换成1024维向量；
2. 在Qdrant中搜索相似文本块；
3. 使用organization_id隔离不同组织的数据；
4. 返回命中的文本块ID和相似度分数。

这里只负责向量检索，暂时不查询PostgreSQL中的正文。
"""

from dataclasses import dataclass
from uuid import UUID

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from enterprise_support_agent.config import (
    settings,
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
from enterprise_support_agent.infrastructure.cache.query_embedding_cache import (
    QueryEmbeddingCache,
)
import logging


# 取得本模块的日志记录器，用来观察缓存是否被复用。
logger = logging.getLogger(__name__)

@dataclass(
    frozen=True,
    slots=True,
)
class VectorSearchHit:
    """Qdrant命中的一条文本块结果。"""

    # Qdrant Point ID和PostgreSQL文本块ID使用同一个UUID。
    chunk_id: UUID

    # Qdrant计算出的向量相似度分数。
    # 使用余弦相似度时，分数越大通常表示内容越相关。
    score: float


class DocumentChunkRetriever:
    """负责从Qdrant召回相似文本块。"""

    def __init__(
            self,
            query_cache: QueryEmbeddingCache | None = None,
    ) -> None:
        """创建检索器，可以选择传入问题向量缓存。"""

        # 传入缓存对象：先查缓存，再决定是否调用Embedding。
        # 没有传入：保持原来的流程，直接调用Embedding。
        self.query_cache = query_cache

        self.collection_manager = (
            QdrantCollectionManager()
        )
    async def search(
        self,
        organization_id: UUID,
        query: str,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> list[VectorSearchHit]:
        """
        搜索当前组织中与问题最相似的文本块。

        organization_id：
            当前正在查询哪个组织的知识库。

        query：
            用户输入的原始问题。

        top_k：
            最多返回多少条结果。

        score_threshold：
            最低相似度要求。
            传入None表示暂时不限制最低分数。
        """

        # strip()去掉问题前后的空格。
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "检索问题不能为空"
            )

        # 防止调用方一次取出过多数据。
        if not 1 <= top_k <= 50:
            raise ValueError(
                "top_k必须在1到50之间"
            )

        if (
            score_threshold is not None
            and not 0.0 <= score_threshold <= 1.0
        ):
            raise ValueError(
                "score_threshold必须在0到1之间"
            )

        # 确保Qdrant Collection存在且配置正确。
        await (
            self.collection_manager
            .ensure_document_chunks_collection()
        )

        # 先假定还没有取得问题向量。
        query_vector = None
        cache_key = None

        if self.query_cache is not None:
            # 根据组织、模型和问题，找到本次应该使用的缓存键。
            cache_key = self.query_cache.build_key(
                organization_id=organization_id,
                query=normalized_query,
            )

            # 尝试读取之前保存的问题向量。
            # 缓存不存在、损坏或Redis不可用时，返回None。
            query_vector = await self.query_cache.get_vector(
                key=cache_key,
            )

        if query_vector is None:
            # 没有取得可用缓存，这次需要调用Embedding。
            logger.info("未取得缓存向量，调用Embedding生成")

            query_vector = await embedding_model.aembed_query(
                normalized_query,
            )

            # 先确认新向量的维度正确，
            # 再缓存，避免保存错误的模型结果。
            if len(query_vector) != settings.qdrant_vector_size:
                raise RuntimeError(
                    "问题向量维度不匹配："
                    f"实际为{len(query_vector)}，"
                    f"配置为{settings.qdrant_vector_size}"
                )

            if (
                    self.query_cache is not None
                    and cache_key is not None
            ):
                # 保存新生成的向量，
                # 下次同一组织问相同问题时可以复用。
                await self.query_cache.set_vector(
                    key=cache_key,
                    vector=query_vector,
                )

        else:
            # 已经从Redis取到了问题向量，
            # 这次可以直接复用，不需要再调用Embedding。
            logger.info("问题向量缓存命中，复用已有向量")

        # query_points()向Qdrant发送问题向量，
        # 查找距离最近的Point。
        query_response = (
            await qdrant_client.query_points(
                collection_name=(
                    settings.qdrant_collection_name
                ),
                query=query_vector,

                # 只允许搜索当前组织的数据。
                # 这是知识库多租户隔离的关键条件。
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
                score_threshold=score_threshold,

                # 当前只需要Point ID和分数。
                # 正文下一步根据ID从PostgreSQL读取。
                with_payload=False,
                with_vectors=False,
            )
        )

        # Qdrant返回的points已经按照相似度排序。
        # 把它们转换成项目内部更简单的结果对象。
        return [
            VectorSearchHit(
                chunk_id=UUID(
                    str(point.id)
                ),
                score=float(
                    point.score
                ),
            )
            for point in query_response.points
        ]
