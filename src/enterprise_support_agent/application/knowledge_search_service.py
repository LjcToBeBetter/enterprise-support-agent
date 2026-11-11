"""
企业知识库检索服务。

这个Service负责：

1. 调用Qdrant向量检索器；
2. 取得命中的文本块ID和相似度分数；
3. 根据文本块ID从PostgreSQL读取正文；
4. 按照Qdrant的相关性顺序返回完整结果。
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.repositories.document_chunk_repository import (
    DocumentChunkRepository,
)
from enterprise_support_agent.application.hybrid_retriever import (
    HybridRetriever,
)
from enterprise_support_agent.infrastructure.reranking.dashscope_reranker import (
    DashScopeReranker,
    RerankServiceError,
)
from enterprise_support_agent.infrastructure.cache.query_embedding_cache import (
    QueryEmbeddingCache,
)


logger = logging.getLogger(
    __name__
)



@dataclass(
    frozen=True,
    slots=True,
)
class KnowledgeSearchResult:
    """返回给上层的一条完整混合检索结果。"""

    chunk_id: UUID
    document_id: UUID
    document_version: int
    page_number: int
    chunk_index: int
    content: str

    # RRF计算出的最终融合分数。
    rrf_score: float

    # 向量检索排名和原始分数。
    # None表示向量检索没有召回该文本块。
    vector_rank: int | None
    vector_score: float | None

    # BM25检索排名和原始分数。
    # None表示BM25没有召回该文本块。
    bm25_rank: int | None
    bm25_score: float | None

    # Rerank模型重新排序后的名次。
    #
    # None表示Rerank调用失败，
    # 当前使用的是RRF降级结果。
    rerank_rank: int | None

    # Rerank模型计算的相关性分数。
    rerank_score: float | None

class KnowledgeSearchService:
    """负责组织并执行一次完整的知识库检索。"""

    def __init__(
        self,
        session: AsyncSession,
        query_cache: QueryEmbeddingCache | None = None,
    ) -> None:
        """创建检索服务，并将可选的缓存传给混合检索器。"""

        # 用数据库Session查询文本块正文。
        self.document_chunk_repository = DocumentChunkRepository(
            session=session,
        )

        # 收到缓存对象后，继续向下传递，
        # 最终由向量检索器读取和保存问题向量。
        self.hybrid_retriever = HybridRetriever(
            query_cache=query_cache,
        )

        # Rerank仍然正常执行，对本次检索结果重新排序。
        self.reranker = DashScopeReranker()

    async def search(
            self,
            organization_id: UUID,
            query: str,
            candidate_top_k: int = 20,
            rrf_top_k: int = 20,
            final_top_k: int = 5,
            vector_weight: float = 0.5,
            bm25_weight: float = 0.5,
            rrf_k: int = 60,
    ) -> list[KnowledgeSearchResult]:
        """
        执行混合检索、RRF融合和Rerank重排序。

        candidate_top_k：
            向量检索和BM25各自召回多少条。

        rrf_top_k：
            RRF融合后保留多少条交给Rerank。

        final_top_k：
            Rerank后最终返回多少条。
        """

        if final_top_k > rrf_top_k:
            raise ValueError(
                "final_top_k不能大于rrf_top_k"
            )

        # 第一步：
        # 向量检索和BM25分别召回候选，
        # 然后通过加权RRF融合并保留rrf_top_k条。
        hybrid_hits = await self.hybrid_retriever.search(
            organization_id=organization_id,
            query=query,
            candidate_top_k=candidate_top_k,
            final_top_k=rrf_top_k,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            rrf_k=rrf_k,
        )

        if not hybrid_hits:
            return []

        chunk_ids = []

        for hit in hybrid_hits:
            chunk_ids.append(
                hit.chunk_id
            )

        # 第二步：
        # 根据文本块ID从PostgreSQL读取完整正文。
        chunks = (
            await self.document_chunk_repository
            .list_by_ids_and_organization(
                organization_id=organization_id,
                chunk_ids=chunk_ids,
            )
        )

        chunks_by_id = {}

        for chunk in chunks:
            chunks_by_id[chunk.id] = chunk

        # 这里保存等待交给Rerank的RRF候选。
        rrf_results: list[
            KnowledgeSearchResult
        ] = []

        for hit in hybrid_hits:
            chunk = chunks_by_id.get(
                hit.chunk_id
            )

            if chunk is None:
                logger.warning(
                    "混合检索命中的文本块"
                    "在PostgreSQL中不存在："
                    "chunk_id=%s organization_id=%s",
                    hit.chunk_id,
                    organization_id,
                )
                continue

            rrf_results.append(
                KnowledgeSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_version=(
                        chunk.document_version
                    ),
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    rrf_score=hit.rrf_score,
                    vector_rank=hit.vector_rank,
                    vector_score=hit.vector_score,
                    bm25_rank=hit.bm25_rank,
                    bm25_score=hit.bm25_score,

                    # 当前还没有执行Rerank，
                    # 所以先设置为None。
                    rerank_rank=None,
                    rerank_score=None,
                )
            )

        if not rrf_results:
            return []

        # 第三步：
        # 只把候选文本正文交给Rerank模型。
        candidate_documents = []

        for result in rrf_results:
            candidate_documents.append(
                result.content
            )

        try:
            rerank_results = await self.reranker.rerank(
                query=query,
                documents=candidate_documents,
                top_n=final_top_k,
            )

        except RerankServiceError:
            # Rerank属于外部模型服务。
            #
            # 如果它暂时不可用，不能让整个知识库检索失败，
            # 因此降级为直接返回RRF排名结果。
            logger.exception(
                "Rerank服务调用失败，"
                "本次检索降级为RRF结果："
                "organization_id=%s",
                organization_id,
            )

            return rrf_results[
                :final_top_k
            ]

        # 第四步：
        # 根据Rerank返回的document_index，
        # 找回对应的完整文本块和原始检索信息。
        final_results: list[
            KnowledgeSearchResult
        ] = []

        for rerank_rank, rerank_result in enumerate(
                rerank_results,
                start=1,
        ):
            # document_index对应candidate_documents的下标。
            #
            # candidate_documents和rrf_results顺序一致，
            # 所以可以使用同一个下标找到完整结果。
            original_result = rrf_results[
                rerank_result.document_index
            ]

            final_results.append(
                KnowledgeSearchResult(
                    chunk_id=original_result.chunk_id,
                    document_id=(
                        original_result.document_id
                    ),
                    document_version=(
                        original_result.document_version
                    ),
                    page_number=(
                        original_result.page_number
                    ),
                    chunk_index=(
                        original_result.chunk_index
                    ),
                    content=original_result.content,
                    rrf_score=(
                        original_result.rrf_score
                    ),
                    vector_rank=(
                        original_result.vector_rank
                    ),
                    vector_score=(
                        original_result.vector_score
                    ),
                    bm25_rank=(
                        original_result.bm25_rank
                    ),
                    bm25_score=(
                        original_result.bm25_score
                    ),
                    rerank_rank=rerank_rank,
                    rerank_score=(
                        rerank_result.relevance_score
                    ),
                )
            )

        return final_results