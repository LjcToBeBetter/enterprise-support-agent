"""
按用户对话轮次拆分Agent历史。

系统规则：单独保留。
较早对话：准备交给模型生成摘要。
最近对话：保留原文。
"""

from dataclasses import dataclass

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)


@dataclass(
    frozen=True,
    slots=True,
)
class AgentHistoryParts:
    """保存拆分后的三组消息，不是数据库ORM模型。"""

    system_messages: list[SystemMessage]
    old_messages: list[BaseMessage]
    recent_messages: list[BaseMessage]


def split_agent_history(
    messages: list[BaseMessage],
    recent_turns: int,
) -> AgentHistoryParts:
    """
    以HumanMessage作为一轮对话的开始。

    保留最近recent_turns轮，
    包括当前可能还在执行中的一轮。

    这里只分组，不修改原消息列表。
    """

    if recent_turns < 1:
        raise ValueError(
            "至少需要保留最近一轮对话"
        )

    system_messages: list[SystemMessage] = []
    conversation_messages: list[BaseMessage] = []

    for message in messages:
        if isinstance(message, SystemMessage):
            # 系统规则单独保留，不参与历史摘要。
            system_messages.append(message)
        else:
            conversation_messages.append(message)

    # 记录每条用户消息在列表中的位置。
    # 这些位置就是对话轮次的分界点。
    human_indexes: list[int] = []

    for index, message in enumerate(
        conversation_messages
    ):
        if isinstance(message, HumanMessage):
            human_indexes.append(index)

    if len(human_indexes) <= recent_turns:
        # 对话轮数还不多，没有需要压缩的旧对话。
        return AgentHistoryParts(
            system_messages=system_messages,
            old_messages=[],
            recent_messages=conversation_messages,
        )

    # 例如一共6轮，需要保留最近4轮：
    # human_indexes[-4]取得第3轮用户消息的位置。
    cut_index = human_indexes[-recent_turns]

    return AgentHistoryParts(
        system_messages=system_messages,

        # 分界点之前：较早对话，准备生成摘要。
        old_messages=conversation_messages[:cut_index],

        # 从分界点开始：最近对话，保留完整原文。
        recent_messages=conversation_messages[cut_index:],
    )