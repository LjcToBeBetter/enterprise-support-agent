"""
企业支持Agent执行服务。

负责：
1. 创建当前用户可使用的工具；
2. 调用模型，让模型选择工具；
3. 执行工具，把结果交回模型；
4. 重复上述过程，直到模型给出最终回答；
5. 限制调用次数，防止无限循环。
"""

import json
from dataclasses import dataclass

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.agent_context import (
    AgentContext,
)
from enterprise_support_agent.application.agent_prompt import (
    AGENT_SYSTEM_PROMPT,
)
from enterprise_support_agent.application.agent_tools import (
    create_agent_tools,
)
from enterprise_support_agent.application.exceptions import (
    OrganizationAccessDeniedError,
    TicketNotFoundError,
    AgentEmptyResponseError,
    AgentLimitExceededError,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)
from enterprise_support_agent.infrastructure.llm.client import (
    chat_model,
)


@dataclass(
    frozen=True,
    slots=True,
)
class AgentResult:
    """Agent执行完成后交给上层的结果。"""

    answer: str

    # 本次提出并处理了多少次工具调用。
    # 包含工具名错误、参数不合格的尝试。
    tool_call_count: int

class AgentService:
    """执行当前组织内的一次Agent任务。"""

    def __init__(
        self,
        session: AsyncSession,
        context: AgentContext,
    ) -> None:
        """保存本次请求的数据库会话和身份。"""

        self.session = session
        self.context = context

    async def run(
        self,
        query: str,
    ) -> AgentResult:
        """执行一次任务，直到模型回答或达到次数上限。"""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "Agent问题不能为空"
            )

        # 先检查组织身份。
        # 即使模型没有调用工具，也不能跳过这一步。
        membership_repository = MembershipRepository(
            session=self.session
        )

        membership = (
            await membership_repository
            .get_by_organization_and_user(
                organization_id=(
                    self.context.organization_id
                ),
                user_id=self.context.current_user_id,
            )
        )

        if membership is None:
            raise OrganizationAccessDeniedError(
                self.context.organization_id
            )

        tools = create_agent_tools(
            session=self.session,
            context=self.context,
        )

        # 建立工具名称与真实工具对象的对应关系。
        tools_by_name = {}

        for available_tool in tools:
            tools_by_name[
                available_tool.name
            ] = available_tool

        model_with_tools = chat_model.bind_tools(
            tools,
            parallel_tool_calls=False,
        )

        # BaseMessage是LangChain各种消息的基础类型。
        # 这个列表可以同时保存系统、用户、模型和工具消息。
        messages: list[BaseMessage] = [
            SystemMessage(
                content=AGENT_SYSTEM_PROMPT
            ),
            HumanMessage(
                content=normalized_query
            ),
        ]

        # 由后端设置限制，不交给模型决定。
        max_model_rounds = 5
        max_tool_calls = 8
        tool_call_count = 0

        # 仅记录本次run中已经成功创建的工单。
        # 每次调用run都会重新初始化，不会沿用其他任务的结果。
        created_ticket_result: dict[str, object] | None = None

        # 整个任务最多允许一次空回答重试。
        empty_response_retry_count = 0

        # 最多调用模型5轮。
        for _ in range(max_model_rounds):
            response = await model_with_tools.ainvoke(
                messages
            )

            # 保存模型本轮的回答或工具调用。
            messages.append(response)

            # 没有工具调用，说明模型正在直接回答，
            # 或向用户询问缺少的信息。
            if not response.tool_calls:
                if not isinstance(
                    response.content,
                    str,
                ):
                    raise RuntimeError(
                        "Agent返回了不支持的回答格式"
                    )

                answer = response.content.strip()

                if not answer:
                    # 前面已经把response加入messages。
                    #
                    # pop()删除列表最后一条消息，
                    # 这里删掉的是模型刚返回的空消息。
                    # 用户问题和之前的工具结果仍然保留。
                    messages.pop()

                    if empty_response_retry_count < 1:
                        empty_response_retry_count += 1

                        # continue跳过当前这一轮剩余代码，
                        # 回到外层for循环，再调用一次模型。
                        #
                        # 不会重新执行之前已经完成的工具。
                        continue

                    # 已经用过一次重试机会，
                    # 再次返回空内容，就明确报告失败。
                    raise AgentEmptyResponseError(
                        "模型重试后仍返回空回答"
                    )

                return AgentResult(
                    answer=answer,
                    tool_call_count=tool_call_count,
                )

            # 在执行这一批工具前，先检查次数上限。
            if (
                tool_call_count
                + len(response.tool_calls)
                > max_tool_calls
            ):
                raise AgentLimitExceededError(
                    "Agent超过工具调用次数上限"
                )

            # 即使模型一次提出多个调用，
            # 后端也按顺序执行，避免并发使用同一Session。
            for tool_call in response.tool_calls:
                tool_call_count += 1

                tool_name = tool_call["name"]
                selected_tool = tools_by_name.get(
                    tool_name
                )

                if selected_tool is None:
                    # 不执行未知工具。
                    # 把错误交给模型，让它重新选择。
                    tool_output = {
                        "ok": False,
                        "code": "UNKNOWN_TOOL",
                        "message": "请求的工具不存在",
                    }

                else:
                    try:
                        if (
                            tool_name == "create_ticket"
                            and created_ticket_result is not None
                        ):
                            # 当前阶段每次任务最多创建一张工单。
                            # 再次请求创建时明确拒绝，不能把旧工单
                            # 当作新参数对应的创建成功结果。
                            tool_output = {
                                "ok": False,
                                "code": "TICKET_ALREADY_CREATED",
                                "message": (
                                    "本次任务已经创建了一张工单，"
                                    "没有执行第二次创建。"
                                    "请向用户说明这一限制。"
                                ),
                                "existing_ticket_id": (
                                    created_ticket_result["ticket_id"]
                                ),
                            }

                        else:
                            # 尚未创建，或者正在执行查询工具，
                            # 才真正调用工具。
                            tool_result = (
                                await selected_tool.ainvoke(
                                    tool_call["args"]
                                )
                            )

                            if tool_name == "create_ticket":
                                # 只有工具成功返回后才保存。
                                created_ticket_result = tool_result

                            tool_output = {
                                "ok": True,
                                "data": tool_result,
                            }

                    except ValidationError:
                        # 例如top_k超出范围，
                        # 或ticket_id不是合法UUID。
                        #
                        # 告诉模型重新填写参数，
                        # 不把完整异常堆栈发给模型。
                        tool_output = {
                            "ok": False,
                            "code": "INVALID_TOOL_ARGUMENTS",
                            "message": (
                                "工具参数不符合要求，"
                                "请按参数格式修正；"
                                "缺少信息时向用户询问"
                            ),
                        }
                    except TicketNotFoundError:
                        # 工单ID格式正确，但在当前组织中没找到记录。
                        #
                        # 将这个结果交回模型，
                        # 让模型告诉用户核对ID，
                        # 而不是编造工单信息。
                        tool_output = {
                            "ok": False,
                            "code": "TICKET_NOT_FOUND",
                            "message": (
                                "在当前组织中未找到这张工单，"
                                "请告知用户核对工单ID。"
                                "不得猜测其他工单ID继续查询。"
                            ),
                        }

                    # 权限异常和未预期的系统异常继续向上抛出。
                    # 不允许模型通过重试绕过权限，
                    # 也不把数据库故障伪装成“没有找到工单”。

                # 每次工具调用都对应一条结果消息。
                # tool_call_id必须与模型提出的调用编号一致。
                messages.append(
                    ToolMessage(
                        content=json.dumps(
                            tool_output,
                            ensure_ascii=False,
                        ),
                        tool_call_id=tool_call["id"],
                    )
                )

            # 本轮工具执行完成，
            # for循环进入下一轮，再次调用模型。
            # 新一轮模型可以读取刚加入的工具结果。

        # 5轮模型调用用完，仍没有得到最终回答。
        raise AgentLimitExceededError(
            "Agent超过模型调用轮数上限"
        )
