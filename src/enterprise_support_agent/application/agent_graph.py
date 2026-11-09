"""
组装LangGraph Agent执行流程。

开始 → 上下文检查 → 调度节点
                      ├─ 知识库Agent：检索、回答，必要时交给工单Agent
                      ├─ 工单Agent：查询或申请创建工单
                      └─ 普通交流：直接回答

各角色内部保留工具调用、空回答重试和结束路线。
"""

from typing import Literal

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.graph import (
    END,
    START,
    StateGraph,
)
from langgraph.graph.state import CompiledStateGraph

from enterprise_support_agent.application.agent_model_node import (
    AgentModelNode,
)
from enterprise_support_agent.application.agent_state import (
    AgentState,
)
from enterprise_support_agent.application.agent_tool_agent import (
    AgentToolNode,
)
from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)
from enterprise_support_agent.application.agent_context_node import (
    AgentContextNode,
)
from enterprise_support_agent.application.agent_tool_groups import (
    select_agent_tools,
)
from enterprise_support_agent.application.knowledge_agent_prompt import (
    KNOWLEDGE_AGENT_SYSTEM_PROMPT,
)
from enterprise_support_agent.application.ticket_agent_prompt import (
    TICKET_AGENT_SYSTEM_PROMPT,
)
from enterprise_support_agent.application.agent_prompt import (
    AGENT_SYSTEM_PROMPT,
)
from enterprise_support_agent.application.agent_routing_node import (
    AgentRoutingNode,
)

def choose_next_step(
    state: AgentState,
) -> Literal["tools", "retry", "finish"]:
    """
    模型节点执行后，决定下一步走哪里。

    返回的是路线名称，不执行模型或工具。
    """

    if state["final_answer"] is not None:
        return "finish"

    if not state["messages"]:
        raise RuntimeError(
            "Agent状态中缺少对话消息"
        )

    last_message = state["messages"][-1]

    # 最后一条消息是模型提出的工具调用，
    # 则安排工具节点执行。
    if (
        isinstance(last_message, AIMessage)
        and last_message.tool_calls
    ):
        return "tools"

    # 模型节点遇到第一次空回答时，
    # 不保存空消息，只更新重试计数。
    #
    # 此时没有最终答案，也没有新的工具调用，
    # 所以回到模型节点重试。
    return "retry"


def create_agent_graph(
    tools: list[BaseTool],
    checkpointer: AsyncPostgresSaver | None = None,
) -> CompiledStateGraph:
    """创建并编译当前请求使用的Agent流程图。"""

    # 上下文检查会估算本次已授权工具的说明长度。
    context_node = AgentContextNode(tools=tools)

    routing_node = AgentRoutingNode()

    # StateGraph由LangGraph提供。
    # AgentState规定这个流程有哪些状态字段，
    # 以及messages字段怎样合并更新。
    builder = StateGraph(AgentState)


    # 从本次已经授权的工具中，分别筛出两个角色的工具。
    knowledge_tools = select_agent_tools(
        available_tools=tools,
        role="knowledge",
    )

    ticket_tools = select_agent_tools(
        available_tools=tools,
        role="ticket",
    )

    # 知识库Agent：使用知识库规则，只能使用检索工具。
    knowledge_model_node = AgentModelNode(
        tools=knowledge_tools,
        system_prompt=KNOWLEDGE_AGENT_SYSTEM_PROMPT,
        role="knowledge",
    )

    # 工单Agent：使用工单规则，只能使用本次允许的工单工具。
    ticket_model_node = AgentModelNode(
        tools=ticket_tools,
        system_prompt=TICKET_AGENT_SYSTEM_PROMPT,
        role="ticket",
    )

    # 普通交流：暂时沿用通用规则，不提供业务工具。
    general_model_node = AgentModelNode(
        tools=[],
        system_prompt=AGENT_SYSTEM_PROMPT,
        role="general",
    )

    # 工具执行节点也分别限制工具范围。
    # 不只限制模型看见什么，也限制对应节点实际能执行什么。
    knowledge_tool_node = AgentToolNode(
        tools=knowledge_tools,
        role="knowledge",
    )

    ticket_tool_node = AgentToolNode(
        tools=ticket_tools,
        role="ticket",
    )

    # 调度节点：判断任务应该交给谁。
    builder.add_node(
        "routing",
        routing_node.route_task,
    )

    # 知识库模型节点：决定如何检索、如何回答。
    builder.add_node(
        "knowledge_model",
        knowledge_model_node.call_knowledge_model,
    )

    # 知识库工具节点：真正执行检索。
    builder.add_node(
        "knowledge_tools",
        knowledge_tool_node.execute_tools,
    )

    # 工单模型节点：决定查询或申请创建工单。
    builder.add_node(
        "ticket_model",
        ticket_model_node.call_model,
    )

    # 工单工具节点：执行查询，创建前仍然等待审批。
    builder.add_node(
        "ticket_tools",
        ticket_tool_node.execute_tools,
    )

    # 普通交流节点：不执行业务工具。
    builder.add_node(
        "general_model",
        general_model_node.call_model,
    )


    # context是我们给这个节点起的名字。
    # 执行到它时，调用prepare_context检查并压缩历史。
    builder.add_node(
        "context",
        context_node.prepare_context,
    )


    # 整个图只有一个入口，先整理历史，再分配任务。
    builder.add_edge(
        START,
        "context",
    )

    # 历史整理完成后，交给调度Agent。
    builder.add_edge(
        "context",
        "routing",
    )

    # 调度结果决定进入哪个角色；混合任务先进入知识库。
    builder.add_conditional_edges(
        "routing",
        choose_agent_entry,
        {
            "knowledge": "knowledge_context",
            "ticket": "ticket_context",
            "general": "general_model",
        },
    )

    # 普通交流没有业务工具，空回答时只重试模型。
    # 重试次数仍由模型节点中的计数限制保护。
    builder.add_conditional_edges(
        "general_model",
        choose_after_general,
        {
            "retry": "general_model",
            "finish": END,
        },
    )

    # 为知识库Agent配置调用模型前的上下文检查。
    # 复用已有的context_node，不需要再写一套摘要逻辑。
    builder.add_node(
        "knowledge_context",
        context_node.prepare_context,
    )

    # 上下文检查完成后，调用知识库模型。
    builder.add_edge(
        "knowledge_context",
        "knowledge_model",
    )

    # 知识库模型执行完，调用choose_after_knowledge判断路线。
    builder.add_conditional_edges(
        "knowledge_model",
        choose_after_knowledge,
        {
            # 请求检索：执行知识库工具。
            "tools": "knowledge_tools",

            # 空回答：经过上下文检查后重试。
            "retry": "knowledge_context",

            # 知识库阶段完成：先检查上下文，再交给工单模型。
            "ticket": "ticket_context",

            # 只有知识库任务，已经回答完：结束。
            "finish": END,
        },
    )

    # 检索工具返回结果后，
    # 先检查上下文，再让知识库模型读取结果。
    builder.add_edge(
        "knowledge_tools",
        "knowledge_context",
    )

    # 工单模型调用前，也先检查是否需要压缩历史。
    builder.add_node(
        "ticket_context",
        context_node.prepare_context,
    )

    # 上下文检查后，调用工单模型。
    builder.add_edge(
        "ticket_context",
        "ticket_model",
    )

    # 工单模型执行后，复用已有的路线判断方法。
    builder.add_conditional_edges(
        "ticket_model",
        choose_next_step,
        {
            # 模型要求查询或创建工单，交给工单工具节点。
            "tools": "ticket_tools",

            # 空回答：经过上下文检查后重试。
            "retry": "ticket_context",

            # 已经生成最终回答：结束。
            "finish": END,
        },
    )

    # 工具返回结果后，再交给工单模型生成回答。
    # 创建工具中的interrupt仍然有效，暂停时不会走到这里。
    builder.add_edge(
        "ticket_tools",
        "ticket_context",
    )

    # compile()检查图结构并生成可执行图。
    # 它不会立即调用模型或执行工具。
    return builder.compile(checkpointer=checkpointer)


def choose_after_knowledge(
    state: AgentState,
) -> Literal["tools", "retry", "ticket", "finish"]:
    """知识库模型执行后，决定调用工具、重试、交接或结束。"""

    # final_answer 有值
    # 说明用户只要求查知识库，现在已经回答完了 → 结束。
    if state["final_answer"] is not None:
        return "finish"

    # 混合任务中，call_knowledge_model已经把回答
    # 保存到knowledge_answer，并清空final_answer。
    # 这说明知识库阶段已完成，可以交给工单Agent。
    if state.get("knowledge_answer") is not None:
        return "ticket"

    if not state["messages"]:
        raise RuntimeError(
            "知识库节点缺少对话消息"
        )

    last_message = state["messages"][-1]

    # 模型提出了检索请求，交给知识库工具节点。
    if (
        isinstance(last_message, AIMessage)
        and last_message.tool_calls
    ):
        return "tools"

    # 没有回答，也没有工具调用，
    # 沿用之前的空回答重试流程。
    return "retry"



def choose_agent_entry(
    state: AgentState,
) -> Literal["knowledge", "ticket", "general"]:
    """根据调度结果，选择先进入哪个Agent。"""

    decision = state.get("routing_decision")

    if decision is None:
        raise RuntimeError("缺少任务调度结果")

    if decision.route in {
        "knowledge",
        "knowledge_then_ticket",
    }:
        # 混合任务也先进入知识库，
        # 知识库完成后，再通过已有路线交给工单Agent。
        return "knowledge"

    if decision.route == "ticket":
        return "ticket"

    if decision.route == "general":
        return "general"

    raise RuntimeError("无法识别任务路线")


def choose_after_general(
    state: AgentState,
) -> Literal["retry", "finish"]:
    """普通交流有回答就结束，空回答则重试。"""

    if state["final_answer"] is not None:
        return "finish"

    return "retry"
