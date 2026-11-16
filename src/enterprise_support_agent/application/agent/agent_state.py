"""
LangGraph Agent执行状态。
整个流程共用的数据格式。

各节点从状态中读取数据，
执行后返回需要更新的字段。

只保存可以记录和恢复的数据，
不保存数据库Session、工具对象或模型客户端。
"""

from langgraph.graph import MessagesState
from enterprise_support_agent.application.agent.routing.agent_routing_schemas import (
    AgentRoutingDecision,
)

# MessagesState由LangGraph提供，
# 已经定义了messages字段及其消息合并规则。
# AgentState在此基础上增加本项目需要的字段。

# MessagesState 是 LangGraph 提供的一个现成状态格式，专门帮我们保存和合并对话消息。
class AgentState(MessagesState):
    """保存Agent流程的对话、计数和最终结果。"""

    # 一次提问对应一个执行编号。失败重试沿用它；下一次新提问才换编号。
    # 前端据此确认重试的是原任务，避免旧按钮误操作到新任务。
    execution_id: str

    # 保存原任务的创建授权。重试时恢复原授权，不能趁重试擅自扩大权限。
    # 是否真正创建，仍需通过人工审批和实时组织权限检查。
    allow_ticket_creation: bool

    # 继承得到的messages字段：
    #
    # 保存系统消息、用户问题、模型回答和工具结果。
    # 不需要在这里重复声明。

    # 已调用模型多少轮。
    model_call_count: int

    # 已处理多少次工具调用尝试。
    # 包括工具名错误、参数错误的尝试。
    tool_call_count: int

    # 已经使用了多少次空回答重试机会。
    empty_response_retry_count: int

    # 本次任务成功创建的工单结果。
    # None表示还没有成功创建。
    #
    # 先保留现有的单张工单创建保护，
    # 后续再结合审批和幂等机制调整。
    created_ticket_result: dict[str, object] | None

    # 模型最终交给用户的回答。
    # None表示还没有得到最终回答。
    final_answer: str | None

    # 保存较早对话的摘要。
    #
    # messages保存对话消息；
    # conversation_summary保存压缩后的历史摘要。
    #
    # 后续生成新摘要时，会用新摘要替换这个字段的旧值。
    conversation_summary: str

    # 保存调度模型对本次任务的路线选择。
    #
    # 例如：
    # routing_decision.route == "knowledge"
    # 表示交给知识库Agent处理。
    #
    # None表示本次任务还没有完成调度。
    routing_decision: AgentRoutingDecision | None

    # 保存本次知识库Agent完成后的回答。
    # 混合任务中，后面还需要工单Agent继续处理。
    knowledge_answer: str | None
