"""创建工单前，暂停流程并等待用户审批。"""

# interrupt由LangGraph提供。
# 第一次执行到这里会暂停流程；
# 收到恢复请求后，它会返回用户提交的决定。
from langgraph.types import interrupt

from enterprise_support_agent.application.agent.tools.agent_tool_schemas import (
    CreateTicketToolInput,
)
from enterprise_support_agent.application.common.exceptions import (
    AgentConversationConflictError,
)


def request_ticket_approval(
    tool_call_id: str,
    arguments: CreateTicketToolInput,
) -> bool:
    """
    暂停流程，等待用户确认这张工单。

    返回True：用户同意。
    返回False：用户拒绝。

    这个方法不创建工单。
    """

    # 传给interrupt的内容会保存在暂停信息中。
    # 后续由接口取出，返回给前端展示。
    decision = interrupt(
        {
            "tool_call_id": tool_call_id,
            "tool_name": "create_ticket",

            # 转成可以保存和传输的字典。
            # mode="json"会把优先级枚举等值转换为JSON兼容形式。
            "arguments": arguments.model_dump(
                mode="json",
            ),
        }
    )

    # 恢复流程时，后端会把审批决定传回来。
    # 预期格式：
    # {"tool_call_id": "...", "approved": true}
    if not isinstance(decision, dict):
        raise AgentConversationConflictError(
            "审批决定格式不正确"
        )

    # 确认用户审批的是当前这次操作。
    if decision.get("tool_call_id") != tool_call_id:
        raise AgentConversationConflictError(
            "审批编号与当前待审批操作不一致"
        )

    approved = decision.get("approved")

    # 必须是布尔值，不能把字符串"false"误当成同意。
    if not isinstance(approved, bool):
        raise AgentConversationConflictError(
            "审批决定必须是true或false"
        )

    return approved