"""验证同会话失败恢复；使用真实LangGraph存档机制，不调用外部模型。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.exc import IntegrityError

from enterprise_support_agent.application.agent.agent_context import AgentContext
from enterprise_support_agent.application.agent.agent_state import AgentState
from enterprise_support_agent.application.agent.nodes.agent_tool_node import AgentToolNode
from enterprise_support_agent.application.agent.tools.agent_tools import create_create_ticket_tool
from enterprise_support_agent.application.common.exceptions import AgentConversationConflictError
from enterprise_support_agent.application.agent.langgraph_agent_service import LangGraphAgentService
from enterprise_support_agent.application.tickets.ticket_enums import TicketPriority
from enterprise_support_agent.application.tickets.ticket_service import TicketService


@asynccontextmanager
async def unlocked(_conversation_id):
    """仅替换数据库锁；图的失败存档、审批暂停与恢复使用真实实现。"""
    yield


class AgentRecoveryTests(unittest.IsolatedAsyncioTestCase):
    """覆盖失败、审批、过时重试和旧会话兼容的状态变化。"""

    async def asyncSetUp(self):
        self.conversation_id = uuid4()
        self.context = AgentContext(
            organization_id=uuid4(), current_user_id=uuid4(), allow_ticket_creation=True,
        )
        self.checkpointer = InMemorySaver()
        self.read_calls = 0
        self.create_calls = 0
        self.fail_read = True
        self.fail_after_create = False
        self.fail_create = False
        self.test_creation = False
        self.authorizations = []

        @tool("search_knowledge")
        async def read_tool(query: str) -> dict:
            """读取测试知识，不连接实际MCP。"""
            self.read_calls += 1
            if self.fail_read:
                raise RuntimeError("MCP temporarily unavailable")
            return {"content": "知识库资料"}

        @tool("create_ticket")
        async def create_tool(title: str, description: str, priority: str) -> dict:
            """模拟只有审批后才能执行的创建操作。"""
            self.create_calls += 1
            if self.fail_create:
                raise RuntimeError("Create outcome unknown")
            return {"ticket_id": "saved-ticket", "title": title}

        self.read_tool = read_tool
        self.create_tool = create_tool
        self.service = LangGraphAgentService(
            session=AsyncMock(), context=self.context, checkpointer=self.checkpointer,
        )
        self.owner = AsyncMock(return_value=SimpleNamespace(id=self.conversation_id))
        module = "enterprise_support_agent.application.agent.langgraph_agent_service"
        self.patches = [
            patch(f"{module}.AgentConversationService.get_conversation", self.owner),
            patch(f"{module}.lock_agent_conversation", unlocked),
            patch(f"{module}.create_agent_tools", side_effect=self.make_tools),
            patch(f"{module}.create_agent_graph", side_effect=self.make_graph),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def make_tools(self, *, session, context):
        """记录实际恢复的授权，防止重试改变原任务权限。"""
        self.authorizations.append(context.allow_ticket_creation)
        return [self.read_tool, self.create_tool] if context.allow_ticket_creation else [self.read_tool]

    def make_graph(self, *, tools, checkpointer):
        """用确定性模型节点替代收费模型；工具节点保留项目实际实现。"""
        async def model(state):
            messages = state["messages"]
            count = state.get("model_call_count", 0) + 1
            if isinstance(messages[-1], ToolMessage):
                if self.fail_after_create:
                    raise RuntimeError("Model unavailable after tool commit")
                return {"final_answer": "任务已完成", "model_call_count": count}
            name = "create_ticket" if self.test_creation else "search_knowledge"
            arguments = {"title": "数据库排查工单", "description": "测试描述，需要技术支持排查数据库问题。", "priority": "high"} if self.test_creation else {"query": "E1007"}
            return {
                "messages": [AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": "call-original"}])],
                "model_call_count": count,
            }

        builder = StateGraph(AgentState)
        builder.add_node("model", model)
        builder.add_node("tools", AgentToolNode(tools).execute_tools)
        builder.add_edge(START, "model")
        builder.add_conditional_edges("model", lambda state: "end" if state.get("final_answer") else "tools", {"end": END, "tools": "tools"})
        builder.add_edge("tools", "model")
        return builder.compile(checkpointer=checkpointer)

    async def fail_once(self):
        """留下一个真实失败存档，模拟本次用户遇到的MCP异常。"""
        with self.assertRaisesRegex(RuntimeError, "MCP temporarily unavailable"):
            await self.service.run("请查询E1007", self.conversation_id)
        return await self.service.get_execution_state(self.conversation_id)

    async def test_failed_task_resumes_without_duplicate_question(self):
        state = await self.fail_once()
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["can_retry"])
        self.fail_read = False
        result = await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual(result.status, "completed")
        graph = self.service._create_graph(True)
        snapshot = await graph.aget_state({"configurable": {"thread_id": str(self.conversation_id)}})
        self.assertEqual(len([message for message in snapshot.values["messages"] if isinstance(message, HumanMessage)]), 1)
        self.assertEqual(self.read_calls, 2)
        # 再次收到相同重试请求时，返回已完成结果，不重新调用工具。
        await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual(self.read_calls, 2)

    async def test_retry_cannot_approve_a_pending_ticket(self):
        self.test_creation = True
        result = await self.service.run("创建测试工单", self.conversation_id)
        self.assertEqual(result.status, "awaiting_approval")
        state = await self.service.get_execution_state(self.conversation_id)
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertFalse(state["can_retry"])
        retried = await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual(retried.status, "awaiting_approval")
        self.assertEqual(self.create_calls, 0)
        rejected = await self.service.resume(self.conversation_id, "call-original", False)
        self.assertEqual(rejected.status, "completed")
        self.assertEqual(self.create_calls, 0)

    async def test_model_failure_after_create_does_not_repeat_tool(self):
        self.test_creation = True
        await self.service.run("创建测试工单", self.conversation_id)
        self.fail_after_create = True
        with self.assertRaisesRegex(RuntimeError, "Model unavailable"):
            await self.service.resume(self.conversation_id, "call-original", True)
        state = await self.service.get_execution_state(self.conversation_id)
        self.assertEqual(state["status"], "failed")
        self.fail_after_create = False
        await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual(self.create_calls, 1)

    async def test_old_retry_cannot_resume_a_different_task(self):
        state = await self.fail_once()
        self.fail_read = False
        await self.service.retry(self.conversation_id, state["execution_id"])
        await self.service.run("这是另一个问题", self.conversation_id)
        with self.assertRaisesRegex(AgentConversationConflictError, "任务已经变化"):
            await self.service.retry(self.conversation_id, state["execution_id"])

    async def test_stored_authorization_cannot_be_elevated_by_retry(self):
        self.service.context = AgentContext(organization_id=self.context.organization_id, current_user_id=self.context.current_user_id, allow_ticket_creation=False)
        state = await self.fail_once()
        self.service.context = self.context  # 新请求即使开启开关，也不扩大原任务授权。
        self.fail_read = False
        await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertFalse(self.authorizations[-1])

    async def test_stored_authorization_survives_browser_refresh(self):
        state = await self.fail_once()
        self.service.context = AgentContext(organization_id=self.context.organization_id, current_user_id=self.context.current_user_id)
        self.fail_read = False
        await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertTrue(self.authorizations[-1])

    async def test_legacy_checkpoint_without_execution_id_can_retry(self):
        graph = self.service._create_graph(True)
        config = {"configurable": {"thread_id": str(self.conversation_id)}}
        with self.assertRaises(RuntimeError):
            await graph.ainvoke({"messages": [HumanMessage(content="旧会话问题")], "tool_call_count": 0, "model_call_count": 0, "created_ticket_result": None, "final_answer": None}, config=config)
        state = await self.service.get_execution_state(self.conversation_id)
        self.assertTrue(state["execution_id"].startswith("legacy:"))
        self.fail_read = False
        with self.assertRaisesRegex(AgentConversationConflictError, "明确选择"):
            await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual((await self.service.retry(self.conversation_id, state["execution_id"], allow_ticket_creation=True)).status, "completed")
        updated = await graph.aget_state(config)
        self.assertEqual(updated.values["execution_id"], state["execution_id"])
        self.assertIs(updated.values["allow_ticket_creation"], True)
        self.assertEqual(len([message for message in updated.values["messages"] if isinstance(message, HumanMessage)]), 1)

    async def test_legacy_authorization_persists_if_retry_fails_again(self):
        graph = self.service._create_graph(True)
        config = {"configurable": {"thread_id": str(self.conversation_id)}}
        with self.assertRaises(RuntimeError):
            await graph.ainvoke({"messages": [HumanMessage(content="旧任务仍在等待MCP恢复")], "tool_call_count": 0, "model_call_count": 0, "created_ticket_result": None, "final_answer": None}, config=config)
        state = await self.service.get_execution_state(self.conversation_id)
        with self.assertRaises(RuntimeError):
            await self.service.retry(self.conversation_id, state["execution_id"], allow_ticket_creation=True)
        after = await self.service.get_execution_state(self.conversation_id)
        self.assertIs(after["allow_ticket_creation"], True)
        self.assertEqual(after["execution_id"], state["execution_id"])
        self.fail_read = False
        await self.service.retry(self.conversation_id, after["execution_id"])
        self.assertTrue(self.authorizations[-1])

    async def test_state_and_retry_check_ownership_first(self):
        self.owner.side_effect = AgentConversationConflictError("test denied")
        with self.assertRaises(AgentConversationConflictError):
            await self.service.retry(self.conversation_id, "anything")
        with self.assertRaises(AgentConversationConflictError):
            await self.service.get_execution_state(self.conversation_id)
        self.assertEqual(self.authorizations, [])

    async def test_another_request_holding_lock_is_running_not_failed(self):
        @asynccontextmanager
        async def locked(_conversation_id):
            raise AgentConversationConflictError("另一个请求正在执行")
            yield
        module = "enterprise_support_agent.application.agent.langgraph_agent_service"
        with patch(f"{module}.lock_agent_conversation", locked):
            state = await self.service.get_execution_state(self.conversation_id)
            self.assertEqual(state["status"], "running")
            self.assertFalse(state["can_retry"])
            with self.assertRaises(AgentConversationConflictError):
                await self.service.retry(self.conversation_id, "not-relevant")

    async def test_legacy_write_with_unknown_commit_is_not_blindly_repeated(self):
        self.test_creation = True
        self.fail_create = True
        graph = self.service._create_graph(True)
        config = {"configurable": {"thread_id": str(self.conversation_id)}}
        await graph.ainvoke({"messages": [HumanMessage(content="旧版创建操作")], "tool_call_count": 0, "model_call_count": 0, "created_ticket_result": None, "final_answer": None}, config=config)
        with self.assertRaisesRegex(RuntimeError, "Create outcome unknown"):
            await self.service.resume(self.conversation_id, "call-original", True)
        state = await self.service.get_execution_state(self.conversation_id)
        self.assertEqual(state["status"], "failed")
        self.assertFalse(state["can_retry"])
        with self.assertRaisesRegex(AgentConversationConflictError, "结果需要先核对"):
            await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual(self.create_calls, 1)

    async def test_approved_tool_failure_retries_without_a_second_approval(self):
        self.test_creation = True
        self.fail_create = True
        await self.service.run("新版创建操作", self.conversation_id)
        with self.assertRaisesRegex(RuntimeError, "Create outcome unknown"):
            await self.service.resume(self.conversation_id, "call-original", True)
        state = await self.service.get_execution_state(self.conversation_id)
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["can_retry"])
        with self.assertRaisesRegex(AgentConversationConflictError, "不要重复审批"):
            await self.service.resume(self.conversation_id, "call-original", True)
        self.fail_create = False
        result = await self.service.retry(self.conversation_id, state["execution_id"])
        self.assertEqual(result.status, "completed")


class TicketRetryTests(unittest.IsolatedAsyncioTestCase):
    """覆盖固定工单编号、重复请求与并发主键冲突后的处理。"""

    async def test_graph_tool_uses_stable_ticket_id_hidden_from_model(self):
        context = AgentContext(organization_id=uuid4(), current_user_id=uuid4(), allow_ticket_creation=True)
        factory = "enterprise_support_agent.application.agent.tools.agent_tools.TicketService"
        saved = SimpleNamespace(id=uuid4(), organization_id=context.organization_id, creator_user_id=context.current_user_id, title="数据库排查工单", description="测试描述，需要技术支持排查数据库问题。", status="open", priority="high")
        with patch(factory) as service_type:
            create = service_type.return_value.create_ticket = AsyncMock(return_value=saved)
            tool_object = create_create_ticket_tool(AsyncMock(), context)
            self.assertNotIn("config", tool_object.args)
            self.assertNotIn("ticket_id", tool_object.args)
            args = {"title": saved.title, "description": saved.description, "priority": "high"}
            config = {"configurable": {"thread_id": str(uuid4()), "agent_execution_id": "task-one", "agent_tool_call_id": "call-one"}}
            await tool_object.ainvoke(args, config=config)
            first = create.call_args.kwargs["ticket_id"]
            await tool_object.ainvoke(args, config=config)
            self.assertEqual(first, create.call_args.kwargs["ticket_id"])
            config["configurable"]["agent_tool_call_id"] = "call-two"
            await tool_object.ainvoke(args, config=config)
            self.assertNotEqual(first, create.call_args.kwargs["ticket_id"])
            config["configurable"]["agent_tool_call_id"] = "call-one"
            config["configurable"]["agent_execution_id"] = "task-two"
            await tool_object.ainvoke(args, config=config)
            self.assertNotEqual(first, create.call_args.kwargs["ticket_id"])

    async def test_duplicate_operation_returns_existing_ticket(self):
        session = AsyncMock()
        service = TicketService(session)
        saved = SimpleNamespace(id=uuid4(), creator_user_id=uuid4(), title="数据库排查工单", description="数据库连接超时，需要技术支持排查。", priority="high")
        service.membership_repository.get_by_organization_and_user = AsyncMock(return_value=object())
        service.ticket_repository.get_by_id_and_organization = AsyncMock(return_value=saved)
        service.ticket_repository.create = AsyncMock()
        result = await service.create_ticket(uuid4(), saved.creator_user_id, saved.title, saved.description, TicketPriority.HIGH, ticket_id=saved.id)
        self.assertIs(result, saved)
        service.ticket_repository.create.assert_not_called()

    async def test_primary_key_race_recovers_committed_ticket(self):
        session = AsyncMock()
        service = TicketService(session)
        saved = SimpleNamespace(id=uuid4(), creator_user_id=uuid4(), title="数据库排查工单", description="数据库连接超时，需要技术支持排查。", priority="high")
        service.membership_repository.get_by_organization_and_user = AsyncMock(return_value=object())
        service.ticket_repository.get_by_id_and_organization = AsyncMock(side_effect=[None, saved])
        service.ticket_repository.create = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("duplicate")))
        result = await service.create_ticket(uuid4(), saved.creator_user_id, saved.title, saved.description, TicketPriority.HIGH, ticket_id=saved.id)
        self.assertIs(result, saved)
        session.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
