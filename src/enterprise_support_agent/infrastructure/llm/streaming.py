"""
聊天模型流式调用工具。

负责逐段读取模型生成的文字，
再逐段交给调用者。

这里不处理检索、引用校验和SSE格式。
"""

from collections.abc import AsyncIterator

from enterprise_support_agent.infrastructure.llm.client import (
    chat_model,
)


async def stream_chat_text(
    messages: list[tuple[str, str]],
) -> AsyncIterator[str]:
    """
    调用聊天模型，并逐段提供答案文字。

    messages：
        system消息和user消息组成的列表。

    AsyncIterator[str]：
        表示调用者可以通过async for，
        持续取得一个个字符串。
    """

    # astream()由LangChain提供，
    # 用来调用模型的异步流式接口。
    #
    # async for会：
    # 1. 等待模型返回下一段；
    # 2. 取得这一段；
    # 3. 执行循环体；
    # 4. 再等待下一段，直到生成结束。
    #
    # message_chunk是AIMessageChunk对象，
    # 表示本次收到的一段模型消息。
    async for message_chunk in chat_model.astream(
        messages
    ):
        # content保存当前片段的文字，
        # 不是到目前为止的完整答案。
        text = message_chunk.content

        # 当前工具只处理纯文本答案。
        if not isinstance(text, str):
            raise RuntimeError(
                "模型返回了不支持的流式内容格式"
            )

        # 部分片段只有元数据，没有文字。
        # 空字符串不需要交给调用者。
        if not text:
            continue

        # yield把当前文字交给调用者。
        #
        # 它不像return那样直接结束函数，
        # 调用者继续读取时，
        # 本函数会继续等待并提供下一段文字。
        yield text