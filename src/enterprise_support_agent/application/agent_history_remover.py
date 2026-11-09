"""为已经生成摘要的旧消息，创建删除指令。"""

from langchain_core.messages import (
    BaseMessage,
    RemoveMessage,
)


def build_history_removals(
    old_messages: list[BaseMessage],
) -> list[RemoveMessage]:
    """
    根据旧消息的ID，创建对应的删除指令。

    这里只生成指令，不会直接修改状态或删除数据库记录。
    后续由节点把这些指令返回给LangGraph执行。
    """

    removals: list[RemoveMessage] = []

    for message in old_messages:
        # id是这条消息的唯一编号。
        # 消息进入LangGraph的messages状态后，
        # add_messages合并规则会为没有ID的消息补上ID。
        message_id = message.id

        # 没有ID就无法准确指定要删除哪条消息。
        if message_id is None:
            raise ValueError(
                "旧消息缺少ID，无法移除"
            )

        # RemoveMessage由LangChain提供。
        #
        # 它不是普通聊天消息，而是一条删除指令：
        # 请从messages中移除这个ID对应的消息。

        # removals里面的message全是RemoveMessage它只记录应该删除的Message的id
        removals.append(
            RemoveMessage(id=message_id)
        )

    return removals