"""
LangGraph的工具节点。

读取模型提出的工具调用，
按顺序执行，并返回工具结果消息。
"""

import json
from typing import Literal

from langchain_core.messages import (
    AIMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from enterprise_support_agent.application.agent_state import (
    AgentState,
)
from enterprise_support_agent.application.exceptions import (
    AgentLimitExceededError,
    TicketNotFoundError,
)
from enterprise_support_agent.application.agent_ticket_approval import (
    request_ticket_approval,
)
from enterprise_support_agent.application.agent_tool_schemas import (
    CreateTicketToolInput,
)

class AgentToolNode:
    """负责执行当前请求已经注册的工具。"""

    def __init__(
        self,
        tools: list[BaseTool],
        role: Literal["knowledge", "ticket"] | None = None,
    ) -> None:
        """保存可执行工具，以及当前节点属于哪个角色。"""

        # 角色用于解释调用失败的原因，不会给节点增加工具权限。
        # None兼容之前没有区分角色的调用方式。
        if role not in (None, "knowledge", "ticket"):
            raise ValueError("不支持的工具节点角色")
        self.role = role

        self.tools_by_name: dict[str, BaseTool] = {}

        for available_tool in tools:
            self.tools_by_name[
                available_tool.name
            ] = available_tool

    async def execute_tools(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        """
        执行模型最新消息中的工具调用。

        返回：
            新的工具结果消息；
            更新后的调用次数；
            本次任务已创建的工单结果。
        """

        if not state["messages"]:
            raise RuntimeError(
                "工具节点没有收到对话消息"
            )

        # [-1]表示取列表最后一个元素。
        # 正常情况下，它就是模型节点刚保存的AIMessage。
        model_message = state["messages"][-1]

        # 防止流程接错：
        # 工具节点必须接收包含工具调用的模型消息。
        if not isinstance(model_message, AIMessage):
            raise RuntimeError(
                "工具节点需要接收模型消息"
            )

        if not model_message.tool_calls:
            raise RuntimeError(
                "模型消息中没有工具调用"
            )

        tool_call_count = state["tool_call_count"]

        # 在执行本批工具之前检查总次数。
        if (
            tool_call_count
            + len(model_message.tool_calls)
            > 8
        ):
            raise AgentLimitExceededError(
                "Agent超过工具调用次数上限"
            )

        # 从状态中读取，而不是放在节点实例上。
        # 这样不同任务不会共用创建记录。
        created_ticket_result = state[
            "created_ticket_result"
        ]

        tool_messages: list[ToolMessage] = []

        # 按顺序执行，避免并发使用同一个数据库Session。
        for tool_call in model_message.tool_calls:
            tool_call_count += 1

            tool_name = tool_call["name"]

            selected_tool = self.tools_by_name.get(
                tool_name
            )

            if selected_tool is None:
                if self.role == "knowledge" and tool_name in {
                    "get_ticket", "create_ticket",
                }:
                    # 工具属于其他角色，不能误报为整个系统没有它。
                    # 仍通过下面的ToolMessage返回，保持调用编号配对。
                    tool_output = {
                        "ok": False,
                        "code": "TOOL_NOT_AVAILABLE_FOR_ROLE",
                        "message": (
                            "当前知识库角色不能执行工单工具，"
                            "这不表示整个系统没有工单功能。"
                            "请根据已取得的检索结果完成知识库回答；"
                            "资料不足时如实说明。"
                            "如果本次路线包含工单阶段，"
                            "程序会在你完成回答后交给工单Agent。"
                            "不要再次调用工单工具，也不要声称工单已创建。"
                        ),
                    }
                elif self.role == "ticket" and tool_name == "create_ticket":
                    tool_output = {
                        "ok": False,
                        "code": "TICKET_CREATION_NOT_ENABLED",
                        "message": (
                            "本次请求没有提供创建工单工具，"
                            "不能执行创建。请如实说明本次限制，"
                            "不要声称整个系统不支持创建工单，"
                            "也不要声称已经创建。"
                        ),
                    }
                else:
                    tool_output = {
                        "ok": False,
                        "code": "UNKNOWN_TOOL",
                        "message": (
                            "该工具不在当前节点可执行的工具列表中。"
                            "请只使用本次提供的工具；"
                            "不要根据一次调用失败推断整个系统的能力。"
                        ),
                    }

            elif (
                tool_name == "create_ticket"
                and created_ticket_result is not None
            ):
                # 沿用当前单任务最多创建一张工单的限制。
                tool_output = {
                    "ok": False,
                    "code": "TICKET_ALREADY_CREATED",
                    "message": (
                        "本次任务已创建一张工单，"
                        "没有执行第二次创建，"
                        "请向用户说明这一限制"
                    ),
                    "existing_ticket_id": (
                        created_ticket_result["ticket_id"]
                    ),
                }

            else:
                try:
                    tool_arguments = tool_call["args"]

                    # 查询工具不用审批，默认允许执行。
                    approved = True

                    if tool_name == "create_ticket":
                        # 先检查模型填写的标题、描述、优先级。
                        # 参数不合法时，交给下面已有的
                        # except ValidationError处理。
                        arguments = CreateTicketToolInput.model_validate(
                            tool_arguments
                        )

                        # 暂停，等待用户确认。
                        #
                        # 恢复时会从工具节点开头重新执行，
                        # 到这里取得用户提交的决定。
                        approved = request_ticket_approval(
                            tool_call_id=tool_call["id"],
                            arguments=arguments,
                        )

                        # 真正执行时，使用刚才展示给用户确认的参数。
                        tool_arguments = arguments.model_dump(
                            mode="json",
                        )

                    if approved:
                        # 查询工具直接执行；
                        # 创建工单工具必须先得到用户同意。
                        tool_result = await selected_tool.ainvoke(
                            tool_arguments
                        )

                        if tool_name == "create_ticket":
                            created_ticket_result = tool_result

                        tool_output = {
                            "ok": True,
                            "data": tool_result,
                        }

                    else:
                        # 用户拒绝：不调用创建工具。
                        # 把拒绝结果交回模型，让它说明操作已取消。
                        tool_output = {
                            "ok": False,
                            "code": "TICKET_CREATION_REJECTED",
                            "message": (
                                "用户拒绝了本次创建工单操作，"
                                "没有创建工单。"
                                "不要自行再次提出相同的创建操作。"
                            ),
                        }

                # 这里继续保留原来的：
                # except ValidationError:
                #     ...
                # except TicketNotFoundError:
                #     ...

                except ValidationError:
                    tool_output = {
                        "ok": False,
                        "code": "INVALID_TOOL_ARGUMENTS",
                        "message": (
                            "参数不符合要求，"
                            "请修正参数或向用户询问信息"
                        ),
                    }

                except TicketNotFoundError:
                    tool_output = {
                        "ok": False,
                        "code": "TICKET_NOT_FOUND",
                        "message": (
                            "当前组织中未找到这张工单，"
                            "请向用户核对ID，"
                            "不要猜测其他ID继续查询"
                        ),
                    }

                # 权限异常和其他系统异常继续向上抛出。

            # 每条结果必须对应一条工具调用。
            tool_messages.append(
                ToolMessage(
                    content=json.dumps(
                        tool_output,
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call["id"],
                )
            )

        # 返回状态更新。
        #
        # messages使用继承的合并规则，
        # 把工具结果加入原来的对话。
        #
        # 计数和工单结果则直接更新为这里的新值。
        return {
            "messages": tool_messages,
            "tool_call_count": tool_call_count,
            "created_ticket_result": (
                created_ticket_result
            ),
            "final_answer": None,
        }
