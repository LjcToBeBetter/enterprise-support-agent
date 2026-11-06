"""
企业支持Agent接口的数据格式。

AgentRequest：
    前端提交的问题。

AgentResponse：
    后端返回的最终回答和工具调用次数。
"""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class AgentRequest(BaseModel):
    """前端向Agent提交的任务。"""

    # 禁止传入未声明的字段。
    #
    # 当前用户身份由JWT确定，
    # 不允许在请求体里额外指定current_user_id。
    model_config = ConfigDict(
        extra="forbid",
    )

    query: str = Field(
        min_length=1,
        max_length=2000,
        description="希望Agent回答的问题或执行的任务",
    )

    # 用户对本次请求的创建操作授权。
    # 不是管理员权限，也不能绕过组织身份检查。
    allow_ticket_creation: bool = Field(
        default=False,

        # 只接受JSON中的true或false，
        # 不接受字符串"true"、数字1等替代值。
        strict=True,
        description="是否允许本次Agent任务创建工单",
    )

    @field_validator("query")
    @classmethod
    def validate_query(
        cls,
        value: str,
    ) -> str:
        """去除首尾空白，禁止提交纯空格。"""

        normalized_query = value.strip()

        if not normalized_query:
            raise ValueError(
                "Agent问题不能只包含空白字符"
            )

        return normalized_query


class AgentResponse(BaseModel):
    """一次Agent任务执行完成后的响应格式。"""

    answer: str = Field(
        description="Agent生成的最终回答",
    )

    # 当前记录的是工具调用尝试次数。
    # 包含工具名错误或参数校验失败的尝试，
    # 不等同于成功执行次数。
    tool_call_count: int = Field(
        ge=0,
        description="本次任务的工具调用尝试次数",
    )