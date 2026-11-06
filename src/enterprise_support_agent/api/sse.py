"""
把Python数据转换成SSE消息格式。

这里只负责整理消息格式，
不负责调用模型，也不负责发送网络请求。
"""

import json
from typing import Literal


def build_sse_event(
    event: Literal["delta", "done", "error"],
    data: dict[str, object],
) -> str:
    """
    创建一条SSE消息。

    event：
        消息类型，只允许delta、done、error。

    data：
        需要发送给前端的数据字典。

    返回：
        按SSE格式整理好的字符串。
    """

    # json.dumps()由Python标准库json提供。
    #
    # 它把Python字典转换成JSON字符串，
    # 方便通过网络发送。
    #
    # ensure_ascii=False表示中文直接保留，
    # 不转换成类似\\u6570的形式。
    json_text = json.dumps(
        data,
        ensure_ascii=False,
    )

    # event这一行告诉前端是什么消息。
    # data这一行保存具体内容。
    #
    # 最后的两个换行符表示：
    # 这一条消息结束了。
    return (
        f"event: {event}\n"
        f"data: {json_text}\n\n"
    )