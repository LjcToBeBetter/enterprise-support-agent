"""为MCP知识库工具检查调用者身份和组织访问权限。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# 从当前MCP请求中，取得SDK已经验证过的身份信息。
# 返回的是AccessToken对象，不是JWT字符串。
from mcp.server.auth.middleware.auth_context import (
    get_access_token,
)

# ToolError用于向MCP客户端返回明确的工具执行失败信息。
from mcp.server.mcpserver.exceptions import ToolError

from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)


async def require_mcp_organization_member(
    organization_id: UUID,
    session: AsyncSession,
) -> UUID:
    """
    检查调用者是否有权检索指定组织的知识库。

    成功：返回当前用户ID。
    失败：抛出ToolError，不继续执行检索。
    """

    # SDK在认证通过后，为当前请求保存了身份信息。
    # 这里直接读取，不需要让模型传入用户ID，
    # 也不需要再次解码JWT。
    access_info = get_access_token()

    if access_info is None:
        raise ToolError("缺少有效的MCP登录身份")

    # 在工具执行前确认具备知识库检索能力。
    if "knowledge:search" not in access_info.scopes:
        raise ToolError("当前令牌没有知识库检索权限")

    # subject是之前验证组件写入的当前用户ID。
    if access_info.subject is None:
        raise ToolError("登录身份中缺少用户ID")

    try:
        user_id = UUID(access_info.subject)
    except ValueError as error:
        raise ToolError("登录身份中的用户ID格式不正确") from error

    # 复用原来的组织成员查询方法。
    repository = MembershipRepository(
        session=session,
    )

    membership = await repository.get_by_organization_and_user(
        organization_id=organization_id,
        user_id=user_id,
    )

    if membership is None:
        raise ToolError("没有权限访问指定组织的知识库")

    return user_id