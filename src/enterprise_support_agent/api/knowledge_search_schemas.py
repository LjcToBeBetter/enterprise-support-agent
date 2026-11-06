"""
企业知识库检索接口的数据格式。

检索流程：

向量检索和BM25召回
    ↓
RRF融合
    ↓
Rerank重排序
    ↓
返回最终结果
"""

from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)


class KnowledgeSearchRequest(BaseModel):
    """前端发起知识库检索时提交的数据。"""

    # 用户需要查询的问题。
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="需要检索的用户问题",
    )

    # 向量检索和BM25检索每一路
    # 最多召回多少条候选。
    candidate_top_k: int = Field(
        default=20,
        ge=1,
        le=50,
        description="每一路最多召回多少条候选",
    )

    # 两路结果合并去重并经过RRF排序后，
    # 保留多少条交给Rerank模型。
    rrf_top_k: int = Field(
        default=20,
        ge=1,
        le=50,
        description="RRF后交给Rerank的候选数量",
    )

    # Rerank重新排序后，
    # 最终返回给前端多少条。
    final_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Rerank后最终返回多少条结果",
    )

    @model_validator(
        mode="after"
    )
    def validate_top_k_relationship(
        self,
    ) -> Self:
        """
        检查两个Top-K之间的关系。

        mode="after"表示：
        等query、rrf_top_k、final_top_k等字段
        全部读取和校验完成后，再执行这个方法。
        """

        if self.final_top_k > self.rrf_top_k:
            raise ValueError(
                "final_top_k不能大于rrf_top_k"
            )

        # 校验成功后必须返回当前请求对象。
        return self


class KnowledgeSearchItemResponse(BaseModel):
    """知识库检索命中的一条文本块。"""

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

    # 从PostgreSQL读取的完整文本块正文。
    content: str

    # 加权RRF计算出的融合分数。
    rrf_score: float

    # 文本块在向量检索中的排名。
    vector_rank: int | None

    # 向量检索返回的原始相似度分数。
    vector_score: float | None

    # 文本块在BM25检索中的排名。
    bm25_rank: int | None

    # BM25返回的关键词相关度分数。
    bm25_score: float | None

    # Rerank模型重新排序后的排名。
    #
    # 如果Rerank服务失败并降级为RRF结果，
    # 这里返回None。
    rerank_rank: int | None

    # Rerank模型计算的相关性分数。
    #
    # 如果Rerank服务失败并降级为RRF结果，
    # 这里返回None。
    rerank_score: float | None


class KnowledgeSearchResponse(BaseModel):
    """一次知识库检索的完整响应。"""

    # 本次实际执行检索的问题。
    query: str

    # 正常情况下按照Rerank结果排序。
    #
    # 如果Rerank服务不可用，
    # 则按照RRF结果降级排序。
    items: list[
        KnowledgeSearchItemResponse
    ]

    # 本次实际返回多少条结果。
    returned_count: int