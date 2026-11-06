"""
测试RAG流式问答接口。

接收三种SSE消息：

delta：立即显示新文字。
done：确认回答完成。
error：报告本次回答失败。
"""

import json

import httpx


def main() -> None:
    """向后端提问，并逐段读取SSE消息。"""

    organization_id = input(
        "请输入组织ID："
    ).strip()

    # 这里只填写登录接口返回的access_token，
    # 不需要在前面添加Bearer。
    token = input(
        "请输入JWT令牌："
    ).strip()

    url = (
        "http://127.0.0.1:8002"
        f"/organizations/{organization_id}"
        "/knowledge/answer/stream"
    )

    request_body = {
        "query": "E1007数据库连接超时应该检查哪些地方？",
        "candidate_top_k": 20,
        "rrf_top_k": 10,
        "final_top_k": 2,
    }

    print()
    print("正在等待检索和模型回答……")

    # 测试脚本使用同步HTTP客户端即可。
    #
    # stream()不会先把整个响应读完，
    # 而是允许我们逐行读取后端发来的内容。
    #
    # with结束时会自动关闭响应连接。
    with httpx.stream(
        method="POST",
        url=url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
        },
        json=request_body,

        # 等待网络数据的超时时间，单位为秒。
        timeout=120.0,
    ) as response:
        # 登录失败、无组织权限等错误，
        # 会在开始发送流之前返回401或403。
        response.raise_for_status()

        event_name = ""
        data_lines: list[str] = []
        received_text = False

        # iter_lines()逐行读取响应，
        # 不需要等待整个答案生成完。
        for line in response.iter_lines():
            if line.startswith("event:"):
                # 取出冒号后面的消息类型。
                event_name = line.split(
                    ":",
                    1,
                )[1].strip()

            elif line.startswith("data:"):
                data_lines.append(
                    line.split(":", 1)[1].lstrip(" ")
                )

            elif line == "":
                # 空行表示当前这条SSE消息结束。
                if not data_lines:
                    continue

                # SSE允许一条消息包含多行data。
                # 先拼接，再把JSON字符串转换成字典。
                payload = json.loads(
                    "\n".join(data_lines)
                )

                if event_name == "delta":
                    print(
                        payload["text"],
                        end="",
                        flush=True,
                    )
                    received_text = True

                elif event_name == "done":
                    # 没有资料时，后端可能直接发送done，
                    # 不经过delta，仍需要显示拒答内容。
                    if not received_text:
                        print(
                            payload["answer"],
                            end="",
                        )

                    print()
                    print()
                    print("收到done，回答已完成。")
                    print(
                        "引用资料数量：",
                        payload["used_source_count"],
                    )
                    print(
                        "是否拒答：",
                        payload["no_answer"],
                    )

                    return

                elif event_name == "error":
                    # 前面即使已经打印过部分文字，
                    # 本次答案也必须视为失败。
                    raise RuntimeError(
                        "本次临时答案已作废："
                        f"{payload['message']}；"
                        "请求编号："
                        f"{payload['request_id']}"
                    )

                # 准备接收下一条SSE消息。
                event_name = ""
                data_lines = []

    # 网络断开不等于回答成功。
    # 必须收到done，才能确认正常完成。
    raise RuntimeError(
        "连接已经结束，但没有收到done消息"
    )


if __name__ == "__main__":
    main()