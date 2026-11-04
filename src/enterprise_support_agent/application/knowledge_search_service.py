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

class KnowledgeSearchService:
    """负责组织并执行一次完整的知识库检索。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """创建知识库检索服务。"""

        # Repository负责从PostgreSQL读取文本块正文。
        self.document_chunk_repository = (
            DocumentChunkRepository(
                session=session
            )
        )

        # 负责执行向量检索、BM25检索和RRF融合。
        self.hybrid_retriever = HybridRetriever()

    async def search(
            self,
            organization_id: UUID,
            query: str,
            candidate_top_k: int = 20,
            final_top_k: int = 5,
            vector_weight: float = 0.5,
            bm25_weight: float = 0.5,
            rrf_k: int = 60,
    ) -> list[KnowledgeSearchResult]:
        """执行混合检索并读取命中文本块的正文。"""

        # 第一步：
        # 同时执行向量检索和BM25检索，
        # 再使用加权RRF融合排名。
        hybrid_hits = await self.hybrid_retriever.search(
            organization_id=organization_id,
            query=query,
            candidate_top_k=candidate_top_k,
            final_top_k=final_top_k,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight,
            rrf_k=rrf_k,
        )

        if not hybrid_hits:
            return []

        # 取出所有命中文本块ID。
        chunk_ids = [
            hit.chunk_id
            for hit in hybrid_hits
        ]

        # 第二步：
        # 根据文本块ID从PostgreSQL读取真正正文。
        chunks = (
            await self.document_chunk_repository
            .list_by_ids_and_organization(
                organization_id=organization_id,
                chunk_ids=chunk_ids,
            )
        )

        # 将文本块整理成：
        # chunk_id -> DocumentChunk对象
        chunks_by_id = {
            chunk.id: chunk
            for chunk in chunks
        }

        search_results: list[
            KnowledgeSearchResult
        ] = []

        # hybrid_hits已经按照RRF分数排好序，
        # 所以这里按照原顺序处理。
        for hit in hybrid_hits:
            chunk = chunks_by_id.get(
                hit.chunk_id
            )

            # Qdrant有Point，但PostgreSQL没有正文，
            # 表示这是需要清理的过期索引。
            if chunk is None:
                logger.warning(
                    "混合检索命中的文本块"
                    "在PostgreSQL中不存在："
                    "chunk_id=%s organization_id=%s",
                    hit.chunk_id,
                    organization_id,
                )
                continue

            # 合并PostgreSQL正文和两路检索信息。
            search_results.append(
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
                )
            )

        return search_results