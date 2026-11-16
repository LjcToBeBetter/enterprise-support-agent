"""校验MCP调用者的登录令牌，确认用户身份。"""

from uuid import UUID

from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.security.tokens import (
    decode_access_token,
)
from enterprise_support_agent.infrastructure.database.repositories.user_repository import (
    UserRepository,
)


async def get_verified_mcp_user_id(
    token: str,
    session: AsyncSession,
    *,
    audience: str,
) -> UUID | None:
    """
    验证登录令牌，并检查用户是否存在、是否启用。

    token：客户端携带的JWT字符串。
    session：本次身份检查使用的数据库会话。

    验证通过：返回用户ID。
    登录凭证无效或用户不可用：返回None。
    数据库故障等系统异常继续向上抛出。
    """

    try:
        # 复用之前的方法：
        # 校验JWT签名、有效期，并取出用户ID。
        user_id = decode_access_token(
            token,
            audience = audience,
        )

    except InvalidTokenError:
        # 令牌过期、被篡改或格式不正确。
        # 后续认证层看到None，会拒绝这次访问。
        return None

    repository = UserRepository(
        session=session,
    )

    # 令牌有效，不代表用户一定还存在。
    # 例如：用户拿到令牌后，账号又被删除。
    user = await repository.get_by_id(
        user_id
    )

    if user is None:
        return None

    # 用户被停用后，即使令牌没过期，也不允许访问。
    if not user.is_active:
        return None

    return user.id