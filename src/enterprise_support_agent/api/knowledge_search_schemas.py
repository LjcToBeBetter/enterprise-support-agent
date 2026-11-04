"""
企业知识库混合检索接口的数据格式。

主要包括：

1. KnowledgeSearchRequest：
   前端提交的检索条件。

2. KnowledgeSearchItemResponse：
   一条混合检索结果。

3. KnowledgeSearchResponse：
   一次检索的完整响应。
"""

from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
)


class KnowledgeSearchRequest(BaseModel):
    """前端发起混合检索时提交的数据。"""

    # 用户需要查询的问题。
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="需要检索的用户问题",
    )

    # 向量检索和BM25检索
    # 每一路最多召回多少条候选。
    candidate_top_k: int = Field(
        default=20,
        ge=1,
        le=50,
        description="每一路最多召回多少条候选",
    )

    # 两路候选经过RRF融合后，
    # 最终最多返回多少条。
    final_top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        description="融合后最终返回多少条结果",
    )


class KnowledgeSearchItemResponse(BaseModel):
    """混合检索命中的一条文本块。"""

    # PostgreSQL中的文本块ID。
    chunk_id: UUID

    # 文本块属于哪一份知识库文档。
    document_id: UUID

    # 命中的是文档的哪个版本。
    document_version: int

    # 文本块主要来自PDF的第几页。
    page_number: int

    # 文本块在当前文档中的编号。
    chunk_index: int

    # 从PostgreSQL读取的文本块正文。
    content: str

    # 加权RRF计算出的最终融合分数。
    rrf_score: float

    # 文本块在向量检索中的排名。
    #
    # None表示没有被向量检索召回。
    vector_rank: int | None

    # 向量检索返回的原始相似度分数。
    vector_score: float | None

    # 文本块在BM25检索中的排名。
    #
    # None表示没有被BM25检索召回。
    bm25_rank: int | None

    # BM25返回的原始关键词相关度分数。
    bm25_score: float | None


class KnowledgeSearchResponse(BaseModel):
    """一次知识库混合检索的完整响应。"""

    # 本次实际执行检索的问题。
    query: str

    # 最终检索结果。
    #
    # 已经按照RRF分数从高到低排列。
    items: list[
        KnowledgeSearchItemResponse
    ]

    # 本次实际返回了多少条结果。
    returned_count: int