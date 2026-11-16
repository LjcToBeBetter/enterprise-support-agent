"""
测试聊天模型的流式输出。

模型每返回一段文字，
控制台就立即显示这一段。
"""

import asyncio

from enterprise_support_agent.infrastructure.llm.streaming import (
    stream_chat_text,
)


async def main() -> None:
    """调用模型，逐段打印答案。"""

    messages = [
        (
            "system",
            "请使用通俗易懂的中文回答。",
        ),
        (
            "user",
            "用三句话解释什么是数据库连接池。",
        ),
    ]

    print("模型正在回答：")
    print()

    # 保存收到的所有文字片段，
    # 最后可以拼成完整答案。
    text_parts: list[str] = []

    async for text in stream_chat_text(messages):
        # end=""：
        # 打印后不换行，让片段接在一起。
        #
        # flush=True：
        # 立即刷新输出，避免文字被缓存在程序里，
        # 迟迟不显示到控制台。
        print(
            text,
            end="",
            flush=True,
        )

        text_parts.append(text)

    # 执行到这里，说明模型已经生成结束，
    # stream_chat_text也已经正常结束。
    print()
    print()
    print("流式输出结束")

    # join()把所有片段连接成一个完整字符串。
    full_answer = "".join(text_parts)

    if not full_answer.strip():
        raise RuntimeError(
            "模型没有返回任何答案文字"
        )

    print(
        f"共收到{len(text_parts)}个文字片段"
    )


if __name__ == "__main__":
    # 启动并执行异步main函数。
    asyncio.run(main())