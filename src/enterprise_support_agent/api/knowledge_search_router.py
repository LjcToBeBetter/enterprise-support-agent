"""
企业知识库检索接口。

当前提供：

POST /organizations/{organization_id}/knowledge/search

组织成员提交问题后，接口返回相关的知识库文本块。
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.knowledge_search_schemas import (
    KnowledgeSearchItemResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from enterprise_support_agent.api.organization_dependencies import (
    require_organization_member,
)
from enterprise_support_agent.application.knowledge_search_service import (
    KnowledgeSearchService,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)


# 当前文件中所有接口的公共路径和Swagger分组。
router = APIRouter(
    prefix=(
        "/organizations/"
        "{organization_id}/knowledge"
    ),
    tags=["knowledge-search"],
)

# 根据用户问题，从当前组织的知识库中找出最相关的文本内容。
@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
)
async def search_knowledge(
    # FastAPI从URL路径中读取组织ID。
    organization_id: UUID,

    # FastAPI从JSON请求体中读取检索条件，
    # 并使用KnowledgeSearchRequest进行校验。
    request_data: KnowledgeSearchRequest,

    # 当前请求使用的异步数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 在接口执行前检查：
    # 1. 请求是否携带有效JWT；
    # 2. 当前用户是否属于URL指定的组织。
    #
    # 验证不通过时会直接返回401或403，
    # 不会继续执行下面的检索代码。
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> KnowledgeSearchResponse:
    """检索当前组织知识库中的相关文本块。"""

    service = KnowledgeSearchService(
        session=session
    )


    # 完整检索流程：
    #
    # 1. 向量检索和BM25分别召回候选；
    # 2. 使用加权RRF进行融合；
    # 3. 使用Rerank模型进行精确重排序；
    # 4. 返回最终文本块。
    search_results = await service.search(
        organization_id=organization_id,
        query=request_data.query,

        # 每一路最多召回多少条。
        candidate_top_k=(
            request_data.candidate_top_k
        ),

        # RRF融合后保留多少条交给Rerank。
        rrf_top_k=(
            request_data.rrf_top_k
        ),

        # Rerank后最终返回多少条。
        final_top_k=(
            request_data.final_top_k
        ),
    )

    # 把Service返回的普通数据对象，
    # 转换成接口规定的响应格式。
    response_items = [
        KnowledgeSearchItemResponse(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            document_version=(
                result.document_version
            ),
            page_number=result.page_number,
            chunk_index=result.chunk_index,
            content=result.content,
            rrf_score=result.rrf_score,
            vector_rank=result.vector_rank,
            vector_score=result.vector_score,
            bm25_rank=result.bm25_rank,
            bm25_score=result.bm25_score,
            rerank_rank=result.rerank_rank,
            rerank_score=result.rerank_score,
        )
        for result in search_results
    ]

    return KnowledgeSearchResponse(
        query=request_data.query.strip(),
        items=response_items,
        returned_count=len(
            response_items
        ),
    )
