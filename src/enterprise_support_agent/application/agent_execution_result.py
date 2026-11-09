"""定义Agent执行完成或暂停等待审批时的返回结果。"""

from dataclasses import dataclass
from typing import Literal

from enterprise_support_agent.application.agent_tool_schemas import (
    CreateTicketToolInput,
)


@dataclass(frozen=True, slots=True)
class PendingTicketApproval:
    """记录Agent准备创建、但还没得到用户同意的工单信息。"""

    # 等待审批的那次工具调用编号。
    tool_call_id: str

    # 准备创建的工单内容。
    arguments: CreateTicketToolInput


@dataclass(frozen=True, slots=True)
class AgentExecutionResult:
    """Service交给Router的结果，不是数据库ORM模型。"""

    # completed：执行完成。
    # awaiting_approval：已经暂停，等待用户审批。
    #
    # Literal用于类型提示；
    # dataclass本身不会像Pydantic那样自动校验这些值。
    status: Literal[
        "completed",
        "awaiting_approval",
    ]

    # 已记录的工具调用尝试次数。
    tool_call_count: int

    # 完成时保存最终回答。
    # 等待审批时还没有最终回答，使用None。
    answer: str | None = None

    # 等待审批时保存待确认的工单。
    # 正常完成时不需要，默认None。
    pending_approval: PendingTicketApproval | None = None