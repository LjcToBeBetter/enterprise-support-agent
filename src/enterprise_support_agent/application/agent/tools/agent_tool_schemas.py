"""
定义Agent工具允许接收的参数。

这些参数由模型填写，
后端使用Pydantic进行校验。

这里只规定输入格式，不执行工具。
"""

from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from enterprise_support_agent.application.tickets.ticket_enums import (
    TicketPriority,
)

class KnowledgeSearchToolInput(BaseModel):
    """知识库检索工具的输入格式。"""

    # extra="forbid"表示禁止传入未声明的字段。
    #
    # 例如模型额外传入organization_id，
    # 会直接校验失败，而不是接受它。
    model_config = ConfigDict(
        extra="forbid",
    )

    # description既说明字段含义，
    # 后面也会作为工具说明的一部分提供给模型。
    query: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "需要在企业知识库中检索的问题，"
            "保留错误码、产品名等关键信息"
        ),
    )

    top_k: int = Field(
        default=3,
        ge=1,
        le=5,
        description="最多返回多少条知识库文本块",
    )

    # field_validator由Pydantic提供。
    #
    # 校验query字段时自动执行下面的方法，
    # 我们不需要手动调用。
    @field_validator("query")
    @classmethod
    def validate_query(
        cls,
        value: str,
    ) -> str:
        """去除首尾空白，禁止只包含空格的问题。"""

        # @classmethod表示这是类方法，
        # 第一个参数cls代表当前模型类。
        #
        # value是Pydantic已经校验为字符串的query。
        normalized_query = value.strip()

        if not normalized_query:
            raise ValueError(
                "检索问题不能只包含空白字符"
            )

        # 返回值会成为校验后的query。
        return normalized_query


class GetTicketToolInput(BaseModel):
    """查询单张工单工具的输入格式。"""

    model_config = ConfigDict(
        extra="forbid",
    )

    # Pydantic会将合法的UUID字符串转换成UUID对象。
    # 格式不正确时，抛出ValidationError。
    ticket_id: UUID = Field(
        description="需要查询的工单UUID",
    )

class CreateTicketToolInput(BaseModel):
    """创建工单工具允许接收的参数。"""

    model_config = ConfigDict(
        # 禁止额外指定用户ID、组织ID等字段。
        extra="forbid",

        # Pydantic自动去除字符串首尾空白，
        # 再检查标题、描述的长度。
        str_strip_whitespace=True,
    )

    # 与现有创建工单接口保持相同长度限制。
    title: str = Field(
        min_length=3,
        max_length=200,
        description="根据用户提供的问题概括工单标题",
    )

    description: str = Field(
        min_length=10,
        max_length=10000,
        description=(
            "根据用户提供的信息填写问题描述，"
            "不得编造故障时间、影响范围或排查结果"
        ),
    )

    # 使用已有的优先级枚举，
    # 只允许low、medium、high、urgent。
    #
    # 没有明确优先级时默认medium。
    priority: TicketPriority = Field(
        default=TicketPriority.MEDIUM,
        description=(
            "工单优先级：low低、medium中、"
            "high高、urgent紧急；"
            "用户未明确时使用medium"
        ),
    )