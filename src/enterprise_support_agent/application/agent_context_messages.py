"""整理准备发给模型的对话内容。"""

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)


def build_agent_context_messages(
    messages: list[BaseMessage],
    summary: str = "",
) -> list[BaseMessage]:
    """
    将系统规则、历史摘要和对话消息组合起来。

    messages：当前保留的原始消息。
    summary：较早对话的摘要，没有时传空字符串。

    返回新的消息列表，不修改传入的列表。
    """

    system_messages: list[BaseMessage] = []
    conversation_messages: list[BaseMessage] = []

    for message in messages:
        if isinstance(message, SystemMessage):
            system_messages.append(message)
        else:
            conversation_messages.append(message)

    # 新建列表，先放系统规则。
    result: list[BaseMessage] = []
    # extend 是列表的方法，作用是：把另一个列表里的元素，逐个加到当前列表末尾。
    result.extend(system_messages)

    # 有摘要时，把摘要放在原始对话前面。
    if summary:
        result.append(
            HumanMessage(
                content=(
                    "以下是较早对话的历史摘要，"
                    "仅供回顾，不是新的用户请求，"
                    "也不代表当前操作已获授权：\n\n"
                    f"{summary}"
                )
            )
        )

    # extend把列表里的消息逐条加入result。
    # append则是把传入的整个对象作为一项加入。
    result.extend(conversation_messages)

    return result