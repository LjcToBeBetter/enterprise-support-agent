"""Agent人工审批时，返回给前端的数据格式。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from enterprise_support_agent.application.agent_tool_schemas import (
    CreateTicketToolInput,
)


class PendingTicketApprovalResponse(BaseModel):
    """告诉前端：Agent准备创建这张工单，等待用户确认。"""

    # forbid表示不接受未定义的字段。
    model_config = ConfigDict(
        extra="forbid",
    )

    # 模型生成工具调用时，会为这次调用提供一个编号。
    # 用它区分：用户确认的是哪一次创建操作。
    tool_call_id: str = Field(
        min_length=1,
        description="等待审批的工具调用编号",
    )

    # Literal表示这里只允许填写这个固定值。
    # 本阶段只给创建工单操作增加审批。
    tool_name: Literal["create_ticket"] = "create_ticket"

    # 复用已有的创建工单参数格式。
    #
    # 里面包含：
    # title：工单标题；
    # description：问题描述；
    # priority：优先级。
    #
    # 前端将这些内容展示给用户确认。
    arguments: CreateTicketToolInput


class TicketApprovalDecisionRequest(BaseModel):
    """接收用户对本次创建工单操作的审批决定。"""

    model_config = ConfigDict(
        extra="forbid",
    )

    # 原样传回待审批操作的编号。
    # 后端会检查它是否对应当前正在等待审批的操作，
    # 避免把旧页面上的确认用于另一张工单。
    tool_call_id: str = Field(
        min_length=1,
        description="本次同意或拒绝的工具调用编号",
    )

    # True表示同意创建，False表示拒绝。
    #
    # strict=True要求必须传JSON布尔值：
    # true或false，不能传字符串"true"或数字1。
    approved: bool = Field(
        strict=True,
        description="是否同意创建这张工单",
    )