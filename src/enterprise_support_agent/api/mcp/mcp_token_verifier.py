"""将项目的JWT和用户身份校验，接入MCP SDK。"""

import jwt
from jwt.exceptions import InvalidTokenError

# TokenVerifier规定校验方法的名称和返回格式。
# AccessToken用于把校验结果交给SDK，不是重新签发令牌。
from mcp.server.auth.provider import (
    AccessToken,
    TokenVerifier,
)

from enterprise_support_agent.config import settings
from enterprise_support_agent.security.mcp_tokens import (
    MCP_TOKEN_AUDIENCE,
)
from enterprise_support_agent.application.identity.mcp_identity_service import (
    get_verified_mcp_user_id,
)
from enterprise_support_agent.infrastructure.database.session import (
    async_session_factory,
)


class PlatformMCPTokenVerifier(TokenVerifier):
    """校验平台签发的MCP令牌，并向SDK提供调用者信息。"""

    async def verify_token(
        self,
        token: str,
    ) -> AccessToken | None:
        """接收JWT字符串，返回已验证的身份信息或None。"""

        try:
            # SDK还需要令牌的有效期和能力范围，
            # 所以这里校验并读取完整payload。
            payload = jwt.decode(
                jwt=token,
                key=settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                audience=MCP_TOKEN_AUDIENCE,
                options={
                    "require": ["sub", "exp", "aud", "scope"],
                },
            )

            # exp是过期时间戳，SDK需要整数形式。
            expires_at = int(payload["exp"])

        except (InvalidTokenError, ValueError, TypeError):
            return None

        scope = payload["scope"]

        if not isinstance(scope, str):
            return None

        # split()默认按空白拆分字符串。
        # 例如knowledge:search other:read变成两个元素的列表。
        scopes = scope.split()

        # 每次身份检查使用独立的数据库会话。
        # 离开async with时自动关闭会话。
        async with async_session_factory() as session:
            # 复用之前的身份方法。
            # 它会再次校验JWT，并检查用户存在且未被停用。
            user_id = await get_verified_mcp_user_id(
                token=token,
                session=session,
                audience=MCP_TOKEN_AUDIENCE,
            )

        if user_id is None:
            return None

        # 将验证结果交给SDK。
        # 数据库等系统异常不在上面捕获，仍会向外抛出。
        return AccessToken(
            token=token,

            # 当前平台内部客户端的标识，不是用户ID。
            client_id="enterprise-support-platform",

            # 真正的调用者用户ID。
            subject=str(user_id),

            # 令牌允许申请的能力。
            scopes=scopes,

            # 过期时间，以及令牌对应的服务。
            expires_at=expires_at,
            resource=MCP_TOKEN_AUDIENCE,
        )