"""根据本次用户需求，选择后续处理路线。"""

from enterprise_support_agent.application.agent.agent_state import (
    AgentState,
)
from enterprise_support_agent.application.agent.memory.agent_context_messages import (
    build_agent_context_messages,
)
from enterprise_support_agent.application.agent.routing.agent_router_model import (
    choose_agent_route,
)
import logging

# 使用项目已有的日志配置。
logger = logging.getLogger(__name__)

class AgentRoutingNode:
    """负责分配任务，不执行知识库检索或工单操作。"""

    async def route_task(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        """
        读取对话和摘要，调用调度模型。

        返回需要更新的routing_decision字段。
        """

        # 本次任务已经选过路线，就不重复调度。
        # run开始新任务时，会把这个字段重置为None。
        if state.get("routing_decision") is not None:
            return {}

        # 将摘要和保留的消息组合起来。
        # 调度模型需要历史信息，才能理解“刚才那个问题”等表达。
        messages = build_agent_context_messages(
            messages=state["messages"],
            summary=state.get(
                "conversation_summary",
                "",
            ),
        )

        # 请求模型，得到AgentRoutingDecision对象。
        decision = await choose_agent_route(
            messages=messages,
        )


        # 只记录选择的路线，不记录用户的问题内容。
        # %s的位置会被decision.route替换。
        logger.info(
            "Agent任务调度：route=%s",
            decision.route,
        )

        # 把选择结果交给LangGraph保存到状态中。
        # 这里只更新路线，不把调度结果作为聊天消息加入messages。
        return {
            "routing_decision": decision,
        }