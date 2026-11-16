"""规定调度Agent返回的任务分配格式。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRoutingDecision(BaseModel):
    """记录本次任务应该交给哪个Agent处理。"""

    model_config = ConfigDict(
        # 禁止返回没有定义的字段。
        extra="forbid",
    )

    # Literal限制route只能使用下面四个值。
    # 程序后面根据这个值选择执行路线。
    route: Literal[
        "knowledge",
        "ticket",
        "knowledge_then_ticket",
        "general",
    ] = Field(
        description=(
            "knowledge：只需要检索知识库、回答知识问题；"
            "ticket：只需要查询或申请创建工单；"
            "knowledge_then_ticket：先查知识库，再处理工单；"
            "general：打招呼、介绍能力，或询问用户以澄清需求"
        ),
    )