"""提供不使用Rerank的检索方案，用于效果对照。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.knowledge.hybrid_retriever import (
    HybridRetriever,
)
from enterprise_support_agent.infrastructure.vector_store.document_chunk_retriever import (
    DocumentChunkRetriever,
)
from enterprise_support_agent.infrastructure.database.repositories.document_chunk_repository import (
    DocumentChunkRepository,
)


async def retrieve_baseline_sources(
    session: AsyncSession,
    organization_id: UUID,
    query: str,
    strategy: str,
    top_k: int = 5,
) -> list[tuple[str, int]]:
    """
    执行指定对照方案，返回按排名排列的资料位置。

    strategy：
        vector：只做向量检索。
        hybrid：向量和BM25检索，再用RRF合并排名。

    top_k：
        最终保留多少条，最多20条。

    返回：
        [("文档ID", 页码), ...]
    """

    if not 1 <= top_k <= 20:
        raise ValueError("top_k必须在1到20之间")

    if strategy == "vector":
        # 不传缓存对象，让本方案正常调用Embedding。
        retriever = DocumentChunkRetriever()

        # 与完整方案一样，先召回20条候选。
        hits = await retriever.search(
            organization_id=organization_id,
            query=query,
            top_k=20,
            score_threshold=None,
        )

        # 按原来的向量排名，取最前面的top_k条。
        hits = hits[:top_k]

    elif strategy == "hybrid":
        retriever = HybridRetriever()

        # 两路各召回20条，经过RRF合并后取前top_k条。
        # 这里直接使用HybridRetriever，因此不会调用Rerank。
        hits = await retriever.search(
            organization_id=organization_id,
            query=query,
            candidate_top_k=20,
            final_top_k=top_k,
        )

    else:
        raise ValueError(f"不支持的对照方案：{strategy}")

    # 这两种检索结果只有文本块ID，
    # 需要查询PostgreSQL，才能知道文档ID和页码。
    repository = DocumentChunkRepository(session=session)

    chunks = await repository.list_by_ids_and_organization(
        organization_id=organization_id,
        chunk_ids=[hit.chunk_id for hit in hits],
    )

    # 数据库返回顺序不一定等于检索排名，
    # 先建立“文本块ID → 文本块对象”的字典，方便按ID找回。
    chunks_by_id = {
        chunk.id: chunk
        for chunk in chunks
    }

    sources: list[tuple[str, int]] = []

    # 按hits的原始顺序整理，保留方案实际给出的排名。
    for hit in hits:
        chunk = chunks_by_id.get(hit.chunk_id)

        # 文本块如果已经不存在，就不作为有效资料返回。
        if chunk is None:
            continue

        sources.append(
            (str(chunk.document_id), chunk.page_number)
        )

    return sources