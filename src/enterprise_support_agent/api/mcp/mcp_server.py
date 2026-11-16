"""企业支持平台的MCP服务端入口。"""

# MCPServer由MCP官方Python SDK提供。
# 它负责处理MCP协议请求：
# 例如列出工具、接收调用请求、返回执行结果。
from mcp.server import MCPServer
from pydantic import AnyHttpUrl
from mcp.server.auth.settings import AuthSettings,Field

from enterprise_support_agent.api.mcp.mcp_token_verifier import (
    PlatformMCPTokenVerifier,
)
from enterprise_support_agent.security.mcp_tokens import (
    MCP_TOKEN_AUDIENCE,
)
from typing import Annotated
from uuid import UUID

from mcp.server.mcpserver.exceptions import ToolError

from enterprise_support_agent.api.mcp.mcp_dependencies import (
    require_mcp_organization_member,
)
from enterprise_support_agent.application.knowledge.knowledge_search_service import (
    KnowledgeSearchService,
)
from enterprise_support_agent.infrastructure.database.session import (
    async_session_factory,
)


# 创建MCP服务端对象。
# 这个名字用于向客户端介绍服务，不是数据库名。
mcp_server = MCPServer(
    name="enterprise-support-tools",
    instructions=(
        "企业支持平台的工具服务，"
        "提供当前用户有权访问的知识库检索能力。"
    ),


    # 无论是token_verifier还是auth,不满足条件的时候正常创建server
    # 但是拒绝这次请求，不会执行这次工具调用

    # 注册我们写的校验组件。
    # SDK读取请求中的Bearer令牌后，
    # 会调用它的verify_token()方法。
    # token_verifier：检查令牌真不真、过没过期、用户是否有效，
    # 然后交出用户、scope、resource等信息
    token_verifier=PlatformMCPTokenVerifier(),

    # AuthSettings是SDK提供的认证配置类。
    # 它和token_verifier需要一起设置。
    # auth：规定这些信息必须满足什么条件，才允许访问
    # auth=AuthSettings(...) 是告诉 MCP SDK 按什么认证规则放行请求。
    auth=AuthSettings(
        # 当前负责签发令牌的平台服务地址。
        issuer_url=AnyHttpUrl(
            "http://127.0.0.1:8002"
        ),

        # 受保护的MCP服务地址。
        resource_server_url=AnyHttpUrl(
            MCP_TOKEN_AUDIENCE
        ),

        # 请求必须具有知识库检索能力。
        # SDK检查验证结果中scopes是否包含这一项。
        required_scopes=[
            "knowledge:search",
        ],

        # 再检查验证结果中的resource，
        # 是否对应上面配置的MCP服务地址。
        validate_token_resource=True,
    ),
)


# tool()是MCP SDK提供的装饰器。
# 它把下面的方法注册为MCP工具，
# 客户端可以发现并调用它。
#
# 注意：这里使用的是MCP的装饰器，
# 不是之前LangChain提供的@tool。
@mcp_server.tool()
async def get_service_info() -> dict[str, str]:
    """
    查询企业支持平台MCP服务的基本信息。

    用于确认客户端连接到了哪个服务。
    不查询业务数据，不检查数据库等依赖的健康状态。
    """

    # 调用工具时，将这个字典作为结果返回给客户端。
    return {
        "service": "enterprise-support-tools",
        "status": "running",
        "description": "企业支持平台MCP工具服务",
    }


@mcp_server.tool()
async def search_knowledge(
    organization_id: UUID,
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=2000,
            description="需要检索的问题，保留错误码等关键信息",
        ),
    ],
    top_k: Annotated[
        int,
        Field(
            ge=1,
            le=5,
            description="最终最多返回几条文本块",
        ),
    ] = 3,
) -> dict[str, object]:
    """
    检索指定组织知识库中的相关资料。

    必须提供真实组织ID，调用者必须属于该组织。
    返回相关文本块、文档ID和页码，不直接生成问答答案。
    """

    # 去掉首尾空白，禁止只输入空格。
    normalized_query = query.strip()

    if not normalized_query:
        raise ToolError("检索问题不能为空")

    # 每次工具调用使用独立的数据库会话。
    async with async_session_factory() as session:

        # 先检查身份、检索能力和组织成员关系。
        # 不通过会抛出异常，后面的检索不会执行。
        await require_mcp_organization_member(
            organization_id=organization_id,
            session=session,
        )

        # 复用已有检索服务，不重新实现检索算法。
        service = KnowledgeSearchService(
            session=session,
        )

        results = await service.search(
            organization_id=organization_id,
            query=normalized_query,
            candidate_top_k=20,
            rrf_top_k=20,
            final_top_k=top_k,
        )

        items: list[dict[str, object]] = []

        for result in results:
            # UUID转成字符串，便于通过协议传输。
            items.append(
                {
                    "chunk_id": str(result.chunk_id),
                    "document_id": str(result.document_id),
                    "document_version": result.document_version,
                    "page_number": result.page_number,
                    "chunk_index": result.chunk_index,
                    "content": result.content,
                    "rerank_score": result.rerank_score,
                }
            )

        return {
            "query": normalized_query,
            "items": items,
            "returned_count": len(items),
        }
def main() -> None:
    """启动MCP服务，等待客户端连接。"""

    # run负责启动服务并持续接收请求。
    # 运行期间，当前进程会保持运行。
    mcp_server.run(
        # Streamable HTTP是MCP支持的一种通信方式。
        # 客户端通过HTTP连接这个服务。
        transport="streamable-http",

        # 先仅允许本机访问。
        host="127.0.0.1",

        # MCP使用8003，原来的FastAPI继续使用8002。
        port=8003,

        # 客户端连接的路径。
        streamable_http_path="/mcp",
    )



# 直接运行本文件时，启动服务。
# 被其他文件导入时，不会自动启动。
if __name__ == "__main__":
    main()