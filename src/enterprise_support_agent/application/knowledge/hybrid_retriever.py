"""
知识库混合检索器。

这个模块负责：

1. 同时执行向量检索和BM25检索；
2. 根据文本块ID合并并去重；
3. 使用加权RRF计算融合分数；
4. 返回最终候选文本块排名。
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from enterprise_support_agent.infrastructure.vector_store.document_chunk_bm25_retriever import (
    DocumentChunkBm25Retriever,
)
from enterprise_support_agent.infrastructure.vector_store.document_chunk_retriever import (
    DocumentChunkRetriever,
)
from enterprise_support_agent.infrastructure.cache.query_embedding_cache import (
    QueryEmbeddingCache,
)

@dataclass(
    frozen=True,
    slots=True,
)
class HybridSearchHit:
    """混合检索最终得到的一条候选结果。"""

    chunk_id: UUID

    # 加权RRF计算出的最终融合分数。
    rrf_score: float

    # 在向量检索中的排名和原始分数。
    # None表示没有被向量检索召回。
    vector_rank: int | None
    vector_score: float | None

    # 在BM25检索中的排名和原始分数。
    # None表示没有被BM25检索召回。
    bm25_rank: int | None
    bm25_score: float | None


@dataclass(
    slots=True,
)
class _FusionCandidate:
    """RRF计算过程中使用的可修改候选记录。"""

    chunk_id: UUID
    rrf_score: float = 0.0
    vector_rank: int | None = None
    vector_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None


class HybridRetriever:
    """并发执行两路召回并使用加权RRF融合结果。"""

    def __init__(
            self,
            query_cache: QueryEmbeddingCache | None = None,
    ) -> None:
        """创建混合检索器，把可选的缓存交给向量检索器。"""

        # 向量检索需要把问题转换成向量，
        # 所以把缓存对象交给它，用于复用问题向量。
        self.vector_retriever = DocumentChunkRetriever(
            query_cache=query_cache,
        )

        # BM25按关键词检索，不需要问题向量缓存。
        self.bm25_retriever = DocumentChunkBm25Retriever()

    async def search(
        self,
        organization_id: UUID,
        query: str,
        candidate_top_k: int = 20,
        final_top_k: int = 5,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
        rrf_k: int = 60,
    ) -> list[HybridSearchHit]:
        """执行向量加BM25的混合检索。"""

        if not query.strip():
            raise ValueError(
                "混合检索问题不能为空"
            )

        # 当前向量检索器最多允许每路召回50条。
        if not 1 <= candidate_top_k <= 50:
            raise ValueError(
                "candidate_top_k必须在1到50之间"
            )

        # 两路结果合并后最多可能有
        # candidate_top_k乘以2条不同结果。
        if not 1 <= final_top_k <= 100:
            raise ValueError(
                "final_top_k必须在1到100之间"
            )

        if not 0.0 <= vector_weight <= 1.0:
            raise ValueError(
                "vector_weight必须在0到1之间"
            )

        if not 0.0 <= bm25_weight <= 1.0:
            raise ValueError(
                "bm25_weight必须在0到1之间"
            )

        if vector_weight + bm25_weight <= 0.0:
            raise ValueError(
                "两路检索权重不能同时为0"
            )

        if rrf_k <= 0:
            raise ValueError(
                "rrf_k必须大于0"
            )

        # asyncio.gather()会并发等待两个异步检索。
        #
        # 如果依次await，需要先等向量检索完成，
        # 再开始BM25检索；并发执行可以减少总等待时间。
        vector_hits, bm25_hits = await asyncio.gather(
            self.vector_retriever.search(
                organization_id=organization_id,
                query=query,
                top_k=candidate_top_k,
                score_threshold=None,
            ),
            self.bm25_retriever.search(
                organization_id=organization_id,
                query=query,
                top_k=candidate_top_k,
            ),
        )

        # 使用文本块ID作为字典的key。
        # 同一个文本块被两路命中时只保留一份记录。
        candidates: dict[
            UUID,
            _FusionCandidate,
        ] = {}

        # 处理向量检索排名。
        for rank, hit in enumerate(
            vector_hits,
            start=1,
        ):
            candidate = candidates.setdefault(
                hit.chunk_id,
                _FusionCandidate(
                    chunk_id=hit.chunk_id
                ),
            )

            candidate.vector_rank = rank
            candidate.vector_score = hit.score

            # 加权RRF公式：
            # weight / (rrf_k + rank)
            candidate.rrf_score += (
                vector_weight
                / (rrf_k + rank)
            )

        # 处理BM25检索排名。
        for rank, hit in enumerate(
            bm25_hits,
            start=1,
        ):
            candidate = candidates.setdefault(
                hit.chunk_id,
                _FusionCandidate(
                    chunk_id=hit.chunk_id
                ),
            )

            candidate.bm25_rank = rank
            candidate.bm25_score = hit.score
            candidate.rrf_score += (
                bm25_weight
                / (rrf_k + rank)
            )

        # 按照RRF分数从高到低排序。
        ranked_candidates = sorted(
            candidates.values(),
            key=lambda candidate: (
                -candidate.rrf_score,
                str(candidate.chunk_id),
            ),
        )

        # 只保留最终需要的Top-K候选，
        # 并转换成不可修改的对外结果对象。
        return [
            HybridSearchHit(
                chunk_id=candidate.chunk_id,
                rrf_score=candidate.rrf_score,
                vector_rank=candidate.vector_rank,
                vector_score=candidate.vector_score,
                bm25_rank=candidate.bm25_rank,
                bm25_score=candidate.bm25_score,
            )
            for candidate in ranked_candidates[
                :final_top_k
            ]
        ]
