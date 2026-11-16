"""检查对话长度，需要时生成摘要并移除较早的消息。"""

from langchain_core.tools import BaseTool

from enterprise_support_agent.config import settings
from enterprise_support_agent.application.agent.agent_state import (
    AgentState,
)
from enterprise_support_agent.application.agent.memory.agent_context_messages import (
    build_agent_context_messages,
)
from enterprise_support_agent.application.agent.memory.agent_token_counter import (
    estimate_context_tokens,
)
from enterprise_support_agent.application.agent.memory.agent_history_splitter import (
    split_agent_history,
)
from enterprise_support_agent.application.agent.memory.agent_history_summarizer import (
    summarize_agent_history,
)
from enterprise_support_agent.application.agent.memory.agent_history_remover import (
    build_history_removals,
)


class AgentContextNode:
    """在调用模型之前，检查是否需要压缩历史。"""

    def __init__(
        self,
        tools: list[BaseTool],
    ) -> None:
        """保存本次允许使用的工具，用于估算输入Token。"""

        self.tools = tools

    async def prepare_context(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        """需要压缩时返回新摘要和删除指令，否则返回空字典。"""

        # 读取已有摘要。
        # 旧会话可能还没有这个字段，默认使用空字符串。
        previous_summary = state.get(
            "conversation_summary",
            "",
        )

        # 先拼出当前准备发给模型的内容：
        # 系统规则 + 已有摘要 + 原始消息。
        context_messages = build_agent_context_messages(
            messages=state["messages"],
            summary=previous_summary,
        )

        token_count = estimate_context_tokens(
            messages=context_messages,
            tools=self.tools,
        )

        # 未达到触发线，不修改任何状态。
        if token_count < settings.agent_summary_trigger_tokens:
            return {}

        # 将历史分成：系统规则、较早对话、最近对话。
        parts = split_agent_history(
            messages=state["messages"],
            recent_turns=settings.agent_recent_turns,
        )

        # 没有较早对话可以压缩，先保留现状。
        # 单轮消息过长等情况，后续在模型调用前另做上限检查。
        if not parts.old_messages:
            return {}

        # 先确认这些旧消息都有ID，并准备删除指令。
        # 此时还没有真正删除。
        removals = build_history_removals(
            parts.old_messages
        )

        # 调用模型，把旧摘要和这次的较早对话
        # 合并成一份新摘要。
        new_summary = await summarize_agent_history(
            old_messages=parts.old_messages,
            previous_summary=previous_summary,
        )

        # 只有摘要生成成功，才会执行到这里。
        #
        # LangGraph收到返回值后：
        # 1. 更新摘要字段；
        # 2. 根据删除指令移除旧消息。
        #
        # 最近对话和系统规则没有被删除，会继续保留。
        return {
            "conversation_summary": new_summary,
            "messages": removals,
        }