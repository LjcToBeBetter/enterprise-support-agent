"""
带PostgreSQL会话记忆的Agent服务。

先验证会话归属，再读取和保存对应thread_id的状态。
"""

from uuid import UUID, uuid4

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.agent.agent_context import (
    AgentContext,
)
from enterprise_support_agent.application.agent.memory.agent_conversation_service import (
    AgentConversationService,
)
from enterprise_support_agent.application.agent.agent_graph import (
    create_agent_graph,
)
from enterprise_support_agent.application.agent.prompts.agent_prompt import (
    AGENT_SYSTEM_PROMPT,
)
# from enterprise_support_agent.application.agent.legacy.agent_service import (
#     AgentResult,
# )
from enterprise_support_agent.application.agent.agent_execution_result import (
    AgentExecutionResult,
    PendingTicketApproval,
)
from enterprise_support_agent.application.agent.tools.agent_tool_schemas import (
    CreateTicketToolInput,
)

from enterprise_support_agent.application.agent.agent_state import (
    AgentState,
)
from enterprise_support_agent.application.agent.tools.agent_tools import (
    create_agent_tools,
)
from enterprise_support_agent.application.common.exceptions import (
    AgentConversationConflictError,
)
from enterprise_support_agent.infrastructure.checkpoint.conversation_lock import (
    lock_agent_conversation,
)
# Command由LangGraph提供。
# resume参数用于把审批决定交给暂停的interrupt。
from langgraph.types import Command

class LangGraphAgentService:
    """通过LangGraph执行当前用户的指定会话任务。"""

    def __init__(
        self,
        session: AsyncSession,
        context: AgentContext,
        checkpointer: AsyncPostgresSaver,
    ) -> None:
        """保存本次请求的身份、业务会话和存档组件。"""

        self.session = session
        self.context = context
        self.checkpointer = checkpointer

    def _create_graph(self, allow_ticket_creation: bool):
        """按任务原有授权重建运行对象，真实历史仍从同一存档读取。"""
        context = AgentContext(
            organization_id=self.context.organization_id,
            current_user_id=self.context.current_user_id,
            allow_ticket_creation=allow_ticket_creation,
        )
        return create_agent_graph(
            tools=create_agent_tools(session=self.session, context=context),
            checkpointer=self.checkpointer,
        )

    @staticmethod
    def _execution_id(snapshot) -> str | None:
        """取任务编号；兼容修复前已失败的旧会话，不要求删除旧存档。"""
        execution_id = snapshot.values.get("execution_id")
        if execution_id:
            return str(execution_id)
        # 旧版本没保存execution_id，但LangGraph已给用户消息分配ID。
        # 重试不新增用户消息，因此这个编号在恢复过程中保持不变。
        for message in reversed(snapshot.values.get("messages", [])):
            if isinstance(message, HumanMessage) and message.id:
                return f"legacy:{message.id}"
        return None

    @staticmethod
    def _legacy_write_needs_review(snapshot) -> bool:
        """旧版本若恰好在创建工单途中断开，不能猜测数据库是否已经提交。"""
        if snapshot.values.get("execution_id") or snapshot.values.get("created_ticket_result"):
            return False
        messages = snapshot.values.get("messages", [])
        return bool(
            {"ticket_tools", "tools"}.intersection(snapshot.next)
            and messages and isinstance(messages[-1], AIMessage)
            and any(call["name"] == "create_ticket" for call in messages[-1].tool_calls)
        )

    @staticmethod
    def _has_failed_task(snapshot) -> bool:
        """审批恢复后节点仍可能失败，旧interrupt此时不能再当成待审批。"""
        return any(task.error is not None for task in snapshot.tasks)

    def _describe_snapshot(self, conversation_id: UUID, snapshot) -> dict[str, object]:
        """把存档整理成页面状态，不把内部异常、令牌等细节返回给前端。"""
        values = snapshot.values
        state: dict[str, object] = {
            "conversation_id": conversation_id,
            "execution_id": self._execution_id(snapshot),
            "status": "idle",
            "can_retry": False,
            "allow_ticket_creation": values.get("allow_ticket_creation"),
            "answer": None,
            "pending_approval": None,
            "tool_call_count": values.get("tool_call_count", 0),
            "message": None,
        }
        if snapshot.interrupts and not self._has_failed_task(snapshot):
            result = self._build_execution_result({
                **values, "__interrupt__": snapshot.interrupts,
            })
            pending = result.pending_approval
            state.update(
                status="awaiting_approval",
                pending_approval={
                    "tool_call_id": pending.tool_call_id,
                    "arguments": pending.arguments.model_dump(mode="json"),
                },
            )
        elif snapshot.next:
            # 调用方持有会话锁，所以这里不会把仍在执行的请求误判为失败。
            # 还存在待执行节点且没有审批暂停，表示上次执行异常中断。
            state.update(
                status="failed",
                can_retry=state["execution_id"] is not None,
                message="上次任务执行中断。确认相关服务恢复后，可重试本次任务。",
            )
            if self._legacy_write_needs_review(snapshot):
                state.update(
                    can_retry=False,
                    message="旧版本任务在创建工单时中断，缺少可靠的防重记录。请先核对工单是否已创建，避免重复提交。",
                )
        elif values.get("final_answer"):
            state.update(status="completed", answer=values["final_answer"])
        return state

    async def get_execution_state(self, conversation_id: UUID) -> dict[str, object]:
        """检查会话归属后，只读查询运行、失败或待审批状态。"""
        await AgentConversationService(
            session=self.session, context=self.context,
        ).get_conversation(conversation_id=conversation_id)
        graph = self._create_graph(False)
        config: RunnableConfig = {"configurable": {"thread_id": str(conversation_id)}}
        try:
            async with lock_agent_conversation(conversation_id):
                return self._describe_snapshot(
                    conversation_id, await graph.aget_state(config),
                )
        except AgentConversationConflictError:
            # 另一个请求持有这把锁，说明此会话此刻正在执行。
            return {
                "conversation_id": conversation_id, "execution_id": None,
                "status": "running", "can_retry": False,
                "message": "任务正在执行，请等待完成后再检查状态。",
            }

    async def retry(
        self,
        conversation_id: UUID,
        execution_id: str,
        *,
        allow_ticket_creation: bool | None = None,
    ) -> AgentExecutionResult:
        """继续原任务，不添加重复问题、不自动批准工单，也不清空历史。"""
        await AgentConversationService(
            session=self.session, context=self.context,
        ).get_conversation(conversation_id=conversation_id)
        config: RunnableConfig = {
            "configurable": {"thread_id": str(conversation_id)},
            "recursion_limit": 20,
        }
        async with lock_agent_conversation(conversation_id):
            graph = self._create_graph(False)
            snapshot = await graph.aget_state(config)
            if self._execution_id(snapshot) != execution_id:
                raise AgentConversationConflictError("任务已经变化，请刷新状态后再操作")
            if snapshot.interrupts and not self._has_failed_task(snapshot):
                # 待审批必须交给用户决定，重试接口不能绕过interrupt。
                return self._build_execution_result({
                    **snapshot.values, "__interrupt__": snapshot.interrupts,
                })
            if not snapshot.next:
                # 上次请求可能已成功，只是响应丢失；直接返回已有结果，不重新执行。
                return self._build_execution_result(snapshot.values)
            if self._legacy_write_needs_review(snapshot):
                raise AgentConversationConflictError(
                    "旧版本创建操作的结果需要先核对，不能直接重跑；查询和检索失败仍可重试"
                )

            # 新任务始终使用存档中原有授权。旧任务没记录授权时，必须
            # 让用户明确选True或False，不能依赖页面刷新后的默认开关。
            allowed = snapshot.values.get("allow_ticket_creation")
            if allowed is None:
                if allow_ticket_creation is None:
                    raise AgentConversationConflictError(
                        "旧任务未记录创建授权，请明确选择只恢复查询，或允许发起工单审批"
                    )
                allowed = allow_ticket_creation
            graph = self._create_graph(allowed is True)

            if snapshot.values.get("allow_ticket_creation") is None:
                # 只补任务编号和用户选择，不追加问题、不清空历史。
                # 本项目的图逐节点执行；update_state按最后完成节点重新
                # 计算下一步，仍会进入原失败节点，不能跳过审批。
                updated_config = await graph.aupdate_state(config, {
                    "execution_id": execution_id,
                    "allow_ticket_creation": allowed,
                })
                config = {**config, **updated_config}

            # None表示继续存档中的未完成任务，而不是再发一条新问题。
            # 已完成的节点不必从头跑，失败的节点会重新执行。
            final_state = await graph.ainvoke(None, config=config)
            return self._build_execution_result(final_state)

    async def run(
        self,
        query: str,
        conversation_id: UUID,
    ) -> AgentExecutionResult:
        """读取已有会话状态，追加问题并执行。"""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Agent问题不能为空")

        conversation_service = AgentConversationService(
            session=self.session,
            context=self.context,
        )

        # 必须先验证归属，才能读取Checkpoint。
        conversation = (
            await conversation_service.get_conversation(
                conversation_id=conversation_id
            )
        )

        tools = create_agent_tools(
            session=self.session,
            context=self.context,
        )

        graph = create_agent_graph(
            tools=tools,
            checkpointer=self.checkpointer,
        )

        # RunnableConfig是调用配置的类型声明。
        # 它与AgentState不同，不是对话消息本身。
        config: RunnableConfig = {
            "configurable": {
                # 用已验证的会话ID定位存档。
                "thread_id": str(conversation.id),
            },

            # 执行图最多推进20步，防止无限循环。
            "recursion_limit": 20,
        }

        # 同一会话的读取、执行和保存放在同一把锁内。
        async with lock_agent_conversation(
            conversation.id
        ):
            # aget_state读取最新存档快照，
            # 不会执行模型或工具。
            # 按会话ID读取最新存档。
            snapshot = await graph.aget_state(config)

            # next记录还有哪些节点等待执行。
            #snapshot.next 指的是“上一次保存的任务还没执行完”，不是本次新问题的下一步。
            # 新问题不能覆盖未完成任务；失败走retry，审批走resume。
            if snapshot.next:
                raise AgentConversationConflictError(
                    "当前会话有未完成的任务，请先重试原任务或处理待审批操作"
                )

            # 本次只提交新的用户消息。
            # 已保存的历史消息由Checkpointer加载，
            # 再按照MessagesState规则合并。
            new_messages = [
                HumanMessage(content=normalized_query)
            ]

            # 新会话没有历史消息，
            # 才添加一次系统提示词。
            if not snapshot.values.get("messages"):
                new_messages.insert(
                    0,
                    SystemMessage(
                        content=AGENT_SYSTEM_PROMPT
                    ),
                )

            input_state: AgentState = {
                "messages": new_messages,
                "execution_id": str(uuid4()),
                "allow_ticket_creation": self.context.allow_ticket_creation,

                # 以下限制按“本次提问”重新计数，
                # 不能让历史对话耗尽下一次提问的额度。
                "model_call_count": 0,
                "tool_call_count": 0,
                "empty_response_retry_count": 0,

                # 新提问开始新的任务。
                "created_ticket_result": None,
                "final_answer": None,

                # 新问题需要重新判断路线，
                # 不能直接沿用上一次任务的选择。
                "routing_decision": None,

                # 新任务不沿用上一轮的知识库回答。
                "knowledge_answer": None,
            }

            # 使用同一个thread_id执行，
            # LangGraph会加载旧状态、合并新输入，
            # 并通过Checkpointer保存执行进度。
            final_state = await graph.ainvoke(
                input_state,
                config=config,
            )

            # 统一整理正常完成或暂停等待审批的结果。
            return self._build_execution_result(
                final_state
            )



    def _build_execution_result(
        self,
        final_state: dict[str, object],
    ) -> AgentExecutionResult:
        """run执行图之后，此方法负责把图的执行结果整理成最终回答或待审批信息。"""

        # 图可能正常结束，也可能被interrupt暂停。
        #
        # 暂停时，默认的ainvoke结果会通过
        # __interrupt__提供暂停信息。
        interrupts = final_state.get(
            "__interrupt__",
            (),
        )

        if interrupts:
            # 当前设计一次只处理一个待审批操作。
            if len(interrupts) != 1:
                raise RuntimeError(
                    "当前流程出现多个待审批操作"
                )

            # value就是之前传给interrupt的那个字典。
            # application\agent_ticket_approval.py
            payload = interrupts[0].value

            if not isinstance(payload, dict):
                raise RuntimeError(
                    "待审批信息格式不正确"
                )

            if payload.get("tool_name") != "create_ticket":
                raise RuntimeError(
                    "当前不支持这个操作的审批"
                )

            tool_call_id = payload.get("tool_call_id")

            if (
                    not isinstance(tool_call_id, str)
                    or not tool_call_id
            ):
                raise RuntimeError(
                    "待审批操作缺少工具调用编号"
                )

            # 再次检查准备展示给用户的工单内容。
            arguments = CreateTicketToolInput.model_validate(
                payload.get("arguments")
            )

            # 已暂停，不需要继续检查最终回答。
            return AgentExecutionResult(
                status="awaiting_approval",
                tool_call_count=final_state["tool_call_count"],
                pending_approval=PendingTicketApproval(
                    tool_call_id=tool_call_id,
                    arguments=arguments,
                ),
            )

        answer = final_state["final_answer"]

        if (
                not isinstance(answer, str)
                or not answer.strip()
        ):
            raise RuntimeError(
                "Agent图结束，但没有有效的最终回答"
            )

        return AgentExecutionResult(
            status="completed",
            answer=answer.strip(),
            tool_call_count=final_state["tool_call_count"],
        )

    async def resume(
        self,
        conversation_id: UUID,
        tool_call_id: str,
        approved: bool,
    ) -> AgentExecutionResult:
        """检查会话和待审批操作，再恢复暂停的流程。"""

        conversation_service = AgentConversationService(
            session=self.session,
            context=self.context,
        )

        # 先检查会话是否属于当前组织和当前用户。
        # 知道会话ID，不代表有权审批这个会话的操作。
        conversation = await conversation_service.get_conversation(
            conversation_id=conversation_id,
        )

        # 恢复时需要重新创建运行用的工具对象。
        #
        # 暂停前已经进入创建工单的审批流程，
        # 因此这里重新提供创建工具。
        # 是否真正执行，仍由approved和工具内部的权限检查决定。
        resume_context = AgentContext(
            organization_id=self.context.organization_id,
            current_user_id=self.context.current_user_id,
            allow_ticket_creation=True,
        )

        tools = create_agent_tools(
            session=self.session,
            context=resume_context,
        )

        graph = create_agent_graph(
            tools=tools,
            checkpointer=self.checkpointer,
        )

        config: RunnableConfig = {
            "configurable": {
                # 必须使用原会话ID，才能找到暂停的存档。
                "thread_id": str(conversation.id),
            },
            "recursion_limit": 20,
        }

        # 检查暂停信息和执行恢复，必须在同一把锁内。
        # 避免同一会话同时收到两次审批请求。
        async with lock_agent_conversation(
            conversation.id
        ):
            snapshot = await graph.aget_state(config)

            # interrupts保存当前仍在等待恢复的暂停信息。
            # 本阶段只支持一次审批一个操作。
            if self._has_failed_task(snapshot):
                raise AgentConversationConflictError(
                    "上次执行失败，请检查任务状态并使用重试入口，不要重复审批"
                )
            if len(snapshot.interrupts) != 1:
                raise AgentConversationConflictError(
                    "当前会话没有唯一的待审批操作"
                )

            payload = snapshot.interrupts[0].value

            if not isinstance(payload, dict):
                raise AgentConversationConflictError(
                    "待审批信息格式不正确"
                )

            # 必须与存档中的操作名称和编号一致。
            if (
                payload.get("tool_name") != "create_ticket"
                or payload.get("tool_call_id") != tool_call_id
            ):
                raise AgentConversationConflictError(
                    "审批操作与当前等待的操作不一致"
                )

            if not isinstance(approved, bool):
                raise AgentConversationConflictError(
                    "审批决定必须是true或false"
                )

            # 不添加新的HumanMessage，也不重置计数。
            # 将决定交回原来暂停的任务，继续执行。
            # LangGraph 会加载该会话的暂停状态，
            # 从被暂停的工具节点开头重新执行。之前已经完成的模型节点不会因此重新执行。
            final_state = await graph.ainvoke(
                Command(
                    resume={
                        "tool_call_id": tool_call_id,
                        "approved": approved,
                    }
                ),
                config=config,
            )

            # 恢复后可能完成，也可能再次暂停。
            # 复用之前提取出来的方法整理结果。
            return self._build_execution_result(
                final_state
            )
