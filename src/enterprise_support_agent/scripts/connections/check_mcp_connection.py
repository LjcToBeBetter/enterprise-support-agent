"""
连接MCP服务，查询工具列表，
并调用服务信息工具。携带MCP令牌，连接服务并调用工具。
"""


import asyncio

# getpass用于读取令牌，终端支持时会隐藏输入内容。
from getpass import getpass

# 当前MCP SDK配套使用的HTTP客户端库。
import httpx2

from mcp import Client
from mcp.client.streamable_http import (
    streamable_http_client,
)
import json

async def main() -> None:
    """携带令牌，验证MCP工具发现和调用。"""

    # 只粘贴JWT字符串，不要包含Bearer前缀和引号。
    # getpass执行到这里，程序会等待你输入并按回车，然后把输入内容作为字符串保存到 token。
    token = input(
        "请粘贴MCP专用令牌："
    ).strip()

    if not token:
        raise ValueError("令牌不能为空")

    # 创建发送HTTP请求的客户端。
    # headers中的内容会随请求发送给服务端。
    # 这里是创建了一个http请求的客户端，请求头为"Authorization": f"Bearer {token}"
    # 这个请求是客户端发送给服务端的
    async with httpx2.AsyncClient(
        headers={
            "Authorization": f"Bearer {token}",
        },

        # 连接等操作最多等待30秒；
        # 读取响应最多等待300秒，允许工具处理较长时间。
        timeout=httpx2.Timeout(
            30.0,
            read=300.0,
        ),
    ) as http_client:

        # 创建MCP通信通道，使用上面带令牌的HTTP客户端。
        transport = streamable_http_client(
            "http://127.0.0.1:8003/mcp",
            http_client=http_client,
        )

        # MCP客户端通过这个通道连接服务端。
        # 离开时先关闭MCP连接，再关闭外层HTTP客户端。
        async with Client(transport) as client:
            tool_list = await client.list_tools()

            print("========== 工具列表 ==========")

            for tool in tool_list.tools:
                print("工具名称：", tool.name)
                print("工具说明：", tool.description)

            result = await client.call_tool(
                "get_service_info",
                {},
            )

            if result.is_error:
                raise RuntimeError(
                    f"工具执行失败：{result.content}"
                )

            print("========== 调用结果 ==========")
            print(result.structured_content)

            print("========== 知识库检索 ==========")

            # 沿用你之前使用的真实组织ID。
            # 服务端仍会检查当前用户是否属于这个组织。
            search_result = await client.call_tool(
                "search_knowledge",
                {
                    "organization_id": (
                        "00000000-0000-0000-0000-000000000000"
                    ),
                    "query": "E1007数据库连接超时应该检查哪些地方？",
                    "top_k": 3,
                },
            )

            if search_result.is_error:
                raise RuntimeError(
                    f"知识库检索失败：{search_result.content}"
                )

            # 把返回数据排版成容易阅读的JSON。
            # ensure_ascii=False：直接显示中文。
            # indent=2：每层缩进两个空格。
            print(
                json.dumps(
                    search_result.structured_content,
                    ensure_ascii=False,
                    indent=2,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())