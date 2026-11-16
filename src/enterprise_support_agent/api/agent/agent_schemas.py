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
from uuid import UUID
from typing import Literal

from enterprise_support_agent.api.agent.agent_approval_schemas import (
    PendingTicketApprovalResponse,
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

    # 前端先创建会话，
    # 再把返回的真实会话ID放到这里。
    #
    # 这个ID只是定位会话，
    # 后端仍然必须检查归属。
    conversation_id: UUID = Field(
        description="本次提问所属的会话ID",
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
    """返回Agent的执行状态、回答或待审批的工单信息。"""

    # 前端根据status决定展示什么。
    # completed：展示回答。
    # awaiting_approval：展示工单内容及同意、拒绝按钮。
    status: Literal[
        "completed",
        "awaiting_approval",
    ] = Field(
        description="Agent已完成，或者正在等待审批",
    )

    # 等待审批时还没有最终回答，因此允许为None。
    answer: str | None = Field(
        default=None,
        description="Agent完成任务后的最终回答",
    )

    tool_call_count: int = Field(
        ge=0,
        description="本次任务已记录的工具调用尝试次数",
    )

    # 标识本次结果属于哪个会话。
    conversation_id: UUID

    # 等待审批时有值，正常完成时为None。
    pending_approval: PendingTicketApprovalResponse | None = Field(
        default=None,
        description="需要用户确认的工单信息",
    )


class AgentRetryRequest(BaseModel):
    """重试已有任务的请求；不接收新问题，防止重复追加消息。"""

    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(min_length=1, max_length=200)
    # 仅用于兼容没有记录原授权的旧会话；新会话以存档中的授权为准。
    # None表示尚未明确选择，不能把“未知授权”偷偷当成False。
    allow_ticket_creation: bool | None = Field(default=None, strict=True)


class AgentExecutionStateResponse(BaseModel):
    """让前端区分任务失败、等待审批、正在执行和已经完成。"""

    conversation_id: UUID
    execution_id: str | None = None
    status: Literal["idle", "running", "failed", "awaiting_approval", "completed"]
    can_retry: bool = False
    allow_ticket_creation: bool | None = None
    answer: str | None = None
    tool_call_count: int = Field(default=0, ge=0)
    pending_approval: PendingTicketApprovalResponse | None = None
    message: str | None = None
