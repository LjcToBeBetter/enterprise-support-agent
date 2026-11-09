"""调用调度模型，判断用户任务应该走哪条路线。"""

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
)

from enterprise_support_agent.application.agent_routing_prompt import (
    AGENT_ROUTING_SYSTEM_PROMPT,
)
from enterprise_support_agent.application.agent_routing_schemas import (
    AgentRoutingDecision,
)
from enterprise_support_agent.infrastructure.llm.client import (
    chat_model,
)

# 把提示词和输出格式接起来，然后给模型，让模型真正做出路线选择。
async def choose_agent_route(
    messages: list[BaseMessage],
) -> AgentRoutingDecision:
    """
    根据对话内容选择处理路线。

    messages：已经整理好的对话，包含当前用户的问题。
    返回值：通过格式校验的AgentRoutingDecision对象。

    这里只判断路线，不执行知识库或工单工具。
    """

    # 给调度模型使用它自己的系统规则。
    routing_messages: list[BaseMessage] = [
        SystemMessage(
            content=AGENT_ROUTING_SYSTEM_PROMPT,
        )
    ]

    for message in messages:
        # 不把原业务Agent的系统提示词带进来，
        # 避免与调度规则混在一起。
        # 原始messages列表不会被修改。
        if isinstance(message, SystemMessage):
            continue

        routing_messages.append(message)

    # with_structured_output约束模型输出格式。
    #
    # method="function_calling"：
    # 要求模型按 AgentRoutingDecision 定义的格式返回结果。
    # 借助模型的工具调用格式返回route。
    # 这里不会调用真实业务工具。
    #
    # 传入Pydantic类后，LangChain会解析返回参数，
    # 并使用AgentRoutingDecision校验。
    routing_model = chat_model.with_structured_output(
        AgentRoutingDecision,
        method="function_calling",
    )

    # 这里才真正请求模型。
    decision = await routing_model.ainvoke(
        routing_messages
    )

    # 正常情况下返回的是AgentRoutingDecision对象。
    # 如果模型服务没有正确提供结构化结果，就明确报错。
    if not isinstance(decision, AgentRoutingDecision):
        raise RuntimeError(
            "调度模型没有返回有效的路线选择"
        )

    return decision