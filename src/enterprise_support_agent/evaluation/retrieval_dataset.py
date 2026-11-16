"""读取检索评估题集，并检查每道题的数据格式。"""

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class RelevantSource(BaseModel):
    """记录一道题的正确资料在哪份文档、哪一页。"""

    # 使用UUID类型，检查文档ID是否符合UUID格式。
    document_id: UUID

    # 页码必须从1开始。
    page_number: int = Field(ge=1)


class RetrievalCase(BaseModel):
    """保存一道评估题的问题和正确资料位置。"""

    # 题目编号，例如KB001，不能是空字符串。
    id: str = Field(min_length=1)

    # 实际交给检索系统的问题。
    query: str = Field(min_length=1)

    # 本阶段每道题至少需要标注一处正确资料，
    # 后面才能计算召回比例和排名得分。
    relevant_sources: list[RelevantSource] = Field(
        min_length=1,
    )


def load_retrieval_cases(
    path: Path,
) -> list[RetrievalCase]:
    """读取指定JSON文件，返回经过格式检查的评估题列表。"""

    # 读取文件中的文本。
    # utf-8-sig同时兼容普通UTF-8和带BOM的UTF-8文件。
    content = path.read_text(encoding="utf-8-sig")

    # 把JSON文本转换成Python列表、字典等对象。
    raw_cases = json.loads(content)

    # 整个题集应是非空列表，不能是一个字典或空列表。
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("评估题集必须是非空列表")

    cases: list[RetrievalCase] = []

    # 记录已经出现的题号，防止两道题使用同一个编号。
    seen_ids: set[str] = set()

    for raw_case in raw_cases:
        # 检查字段和类型，并转换成RetrievalCase对象。
        # 例如文档ID格式错误、页码为0时，会直接报错。
        case = RetrievalCase.model_validate(raw_case)

        if case.id in seen_ids:
            raise ValueError(f"评估题编号重复：{case.id}")

        seen_ids.add(case.id)
        cases.append(case)

    return cases