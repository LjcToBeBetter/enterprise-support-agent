"""
企业知识库RAG问答接口的数据格式。

主要包括：

1. KnowledgeAnswerRequest：
   前端提交的知识库问题和检索参数。

2. KnowledgeAnswerSourceResponse：
   生成答案时使用的一条知识来源。

3. KnowledgeAnswerResponse：
   返回给前端的最终答案和引用来源。
"""

from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)


class KnowledgeAnswerRequest(BaseModel):
    """前端发起知识库问答时提交的数据。"""

    # 用户提出的问题。
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="需要回答的用户问题",
    )

    # 向量检索和BM25每一路召回多少条。
    candidate_top_k: int = Field(
        default=20,
        ge=1,
        le=50,
        description="每一路最多召回多少条候选",
    )

    # RRF融合后保留多少条交给Rerank。
    rrf_top_k: int = Field(
        default=20,
        ge=1,
        le=50,
        description="RRF后交给Rerank的候选数量",
    )

    # Rerank后最终有多少条资料交给大模型。
    final_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="最终交给大模型的资料数量",
    )

    @model_validator(
        mode="after"
    )
    def validate_top_k_relationship(
        self,
    ) -> Self:
        """检查最终数量不能超过RRF候选数量。"""

        if self.final_top_k > self.rrf_top_k:
            raise ValueError(
                "final_top_k不能大于rrf_top_k"
            )

        return self


class KnowledgeAnswerSourceResponse(BaseModel):
    """最终答案引用的一条知识库来源。"""

    # 对应答案中的[资料1]、[资料2]。
    source_number: int

    chunk_id: UUID
    document_id: UUID
    document_version: int
    page_number: int
    chunk_index: int

    # 被大模型用于生成答案的文本块正文。
    content: str

    # Rerank模型计算的相关性分数。
    rerank_score: float | None


class KnowledgeAnswerResponse(BaseModel):
    """返回给前端的一次完整RAG问答结果。"""

    # 用户原问题。
    query: str

    # 大模型根据知识库生成的最终答案。
    answer: str

    # 答案引用的知识库来源。
    sources: list[
        KnowledgeAnswerSourceResponse
    ]

    # 实际使用了多少条知识库资料。
    used_source_count: int

    # True表示没有检索到可用资料，
    # 因此没有调用大模型。
    no_answer: bool