"""
供平台后端复用的MCP知识库客户端方法，不是需要手动输入的测试脚本。

调用过程：
Agent工具传入已验证的用户、组织和检索问题
→ 签发本次调用使用的MCP令牌
→ 携带令牌连接MCP服务
→ 发现工具并调用search_knowledge
→ 把检索结果字典返回给Agent工具。

这个文件没有启动入口，不需要直接运行。
"""

from uuid import UUID

# httpx2负责HTTP通信，以及请求头、网络超时和连接资源。
import httpx2

# Client负责MCP协议通信，例如发现工具、发送工具调用请求。
from mcp import Client

# 将HTTP客户端接入MCP协议，创建双方通信使用的通道。
from mcp.client.streamable_http import (
    streamable_http_client,
)

# settings从项目配置中提供MCP服务地址。
from enterprise_support_agent.config import settings

# 这是我们自己的令牌签发方法，不是MCP SDK自动生成令牌。
from enterprise_support_agent.security.mcp_tokens import (
    create_mcp_access_token,
)


async def search_knowledge_via_mcp(
    *,
    user_id: UUID,
    organization_id: UUID,
    query: str,
    top_k: int = 3,
) -> dict[str, object]:
    """
    通过MCP检索资料，将结果返回给调用本方法的Agent工具。

    星号*表示：下面所有参数必须使用参数名传入。
    user_id：当前登录用户ID，只能来自后端已经验证的身份。
    organization_id：本次请求指定且已经检查过访问权限的组织ID。
    query：模型填写的检索问题。
    top_k：最终最多返回几条文本块，工具参数和服务端会限制为1到5。

    签发令牌本身不会证明user_id的来源可靠；
    调用本方法的后端必须先验证身份，不能让模型任意填写这两个ID。
    MCP服务端还会再次检查账号状态和组织成员关系。

    成功返回包含query、items、returned_count的字典，不打印结果。
    连接、认证、协议或工具执行失败时抛出异常，不返回假成功结果。
    """

    # 本方法运行在自有平台后端，可以调用平台的签发方法。
    # token是JWT字符串，其中包含用户ID、MCP目标地址和检索scope。
    # 普通外部客户端仍需通过签发接口取得令牌，不能自行签发。
    # 不把这个字符串交给模型，也不打印或写入工具结果。
    token = create_mcp_access_token(
        user_id=user_id,
    )

    # 准备带认证头的HTTP客户端。
    # 创建HTTP客户端不等于已经执行检索；业务请求在下面call_tool处发出。
    # async with负责管理资源，离开代码块时关闭HTTP客户端。
    async with httpx2.AsyncClient(
        headers={
            # SDK按Bearer认证格式取出令牌，再调用服务端的验证组件。
            "Authorization": f"Bearer {token}",
        },
        # 一般连接、写入和连接池等待使用30秒超时；
        # 读取响应允许等待300秒，给后端检索和Rerank留出时间。
        timeout=httpx2.Timeout(
            30.0,
            read=300.0,
        ),
    ) as http_client:

        # transport是MCP通信通道的配置，不是工具执行结果。
        # 使用上面带认证头的HTTP客户端，避免另建一个不带令牌的连接。
        transport = streamable_http_client(
            settings.mcp_server_url,
            http_client=http_client,
        )

        # 进入这里时，SDK实际建立MCP通信并进行必要的协议协商。
        # client是MCP客户端，http_client是底层HTTP客户端，两者职责不同。
        # 离开内层代码块先清理MCP连接，再清理外层HTTP客户端。
        async with Client(
            transport,
            # 这是MCP请求层的读取等待时间，单位也是秒。
            read_timeout_seconds=300.0,
        ) as client:

            # 向服务端查询工具列表，SDK会记录工具说明和参数定义。
            # 这里不需要打印列表；下面已明确指定要调用search_knowledge。
            # 这次发现工具的请求，不会执行知识库检索。
            await client.list_tools()

            # 现在才发出真正的工具调用请求：工具名 + 参数字典。
            # 服务端先检查组织权限，再调用已有KnowledgeSearchService。
            # 不传user_id：服务端必须从已经验证的令牌取得用户身份。
            result = await client.call_tool(
                "search_knowledge",
                {
                    # UUID转换为协议能够传输的字符串。
                    "organization_id": str(organization_id),
                    "query": query,
                    "top_k": top_k,
                },
            )

            # result是SDK返回的CallToolResult对象，不直接等于业务结果字典。
            # 有些工具失败通过is_error标记返回，不一定直接抛出异常。
            # 网络错误、认证错误等也可能已经在前面的调用处直接抛出。
            if result.is_error:
                # 不在失败时偷偷改成本地检索，
                # 避免掩盖认证或权限检查失败。
                raise RuntimeError(
                    "MCP知识库检索失败，请检查MCP服务日志"
                )

            # structured_content才是服务端工具返回的结构化业务数据。
            # 当前约定其中包含检索问题、命中的文本块列表和返回数量。
            data = result.structured_content

            # 我们的MCP检索工具约定返回字典。
            if not isinstance(data, dict):
                raise RuntimeError(
                    "MCP知识库工具返回的数据格式不正确"
                )

            # 返回给调用本方法的Agent工具，不是直接发给前端或聊天模型。
            # 后续工具节点会把它转成ToolMessage保存进图状态，模型才能读到。
            # return前仍会依次执行两层async with的连接清理。
            return data
