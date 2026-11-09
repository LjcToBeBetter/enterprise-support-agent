"""签发用于访问MCP服务的JWT令牌。"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from enterprise_support_agent.config import settings


# 当前MCP服务的标识。
# 签发时写入aud，校验时作为audience传入。
# 两边必须使用一致的值。
MCP_TOKEN_AUDIENCE = "http://127.0.0.1:8003/mcp"


def create_mcp_access_token(
    user_id: UUID,
) -> str:
    """为已经通过登录验证的用户，生成MCP专用令牌。"""

    # 获取当前UTC时间，作为签发时间。
    issued_at = datetime.now(timezone.utc)

    # 暂时沿用项目已有的令牌有效期配置。
    expires_at = issued_at + timedelta(
        minutes=settings.jwt_access_token_expire_minutes,
    )

    payload = {
        # 令牌属于哪个用户。
        "sub": str(user_id),

        # 签发时间和过期时间。
        "iat": issued_at,
        "exp": expires_at,

        # 令牌用于哪个服务。
        "aud": MCP_TOKEN_AUDIENCE,

        # scope表示这张令牌允许申请哪些能力。
        # 当前只签发知识库检索能力。
        # 它不能代替后续的组织成员和数据访问检查。
        "scope": "knowledge:search",
    }

    # 使用项目已有密钥和算法签名，返回JWT字符串。
    # aud和scope也包含在签名保护范围内。
    return jwt.encode(
        payload=payload,
        key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )