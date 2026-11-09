"""
tokens.py

主要功能：
    生成和验证JWT访问令牌。

当前部件：
    create_access_token：
        根据用户ID生成有签名、有过期时间的JWT。
"""

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import UUID

import jwt

from enterprise_support_agent.config import (
    settings,
)
from jwt.exceptions import InvalidTokenError

def create_access_token(
    user_id: UUID,
) -> str:
    """为指定用户生成JWT访问令牌。"""

    # datetime.now()获取当前时间。
    #
    # timezone.utc表示使用UTC标准时间(全球统一使用的标准时间)
    # 避免服务器位于不同地区时产生时区混乱。
    #
    # issued_at的类型是datetime。
    issued_at = datetime.now(
        timezone.utc
    )

    # timedelta表示一段时间长度。
    #
    # 例如配置值是30：
    # timedelta(minutes=30)就表示30分钟。
    token_lifetime = timedelta(
        minutes=(
            settings.jwt_access_token_expire_minutes
        )
    )

    # 当前时间 + 有效时长 = 过期时间。
    expires_at = (
        issued_at + token_lifetime
    )

    # payload是准备写入JWT的数据字典。
    payload = {
        # sub是JWT规定的“主体”字段。
        # UUID不能直接作为JWT中的JSON数据，
        # 所以使用str()转换成普通字符串。
        "sub": str(user_id),

        # iat是签发时间。
        "iat": issued_at,

        # exp是过期时间。
        "exp": expires_at,
    }

    # jwt.encode()由PyJWT提供，
    # 用于生成最终的JWT字符串。
    #
    # payload：
    #     需要写入JWT的数据。
    #
    # key：
    #     生成签名时使用的秘密密钥。
    #
    # algorithm：
    #     计算签名时使用的算法，这里是HS256。
    #
    # PyJWT会把datetime时间自动转换成时间戳。
    access_token = jwt.encode(
        payload=payload,
        key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    # 返回类型是str。
    return access_token

def decode_access_token(
    token: str,
    # 单独的 * 表示：后面的参数必须写参数名传入
    *,
    audience: str | None = None,
) -> UUID:
    """
    校验JWT，返回用户ID。

    audience：当前服务期望的令牌使用目标。就是希望当前令牌给谁使用
    星号表示这个参数必须写成audience=...的形式传入。
    """

    # jwt.decode()由PyJWT提供。
    #
    # 它会完成：
    # 1. 拆开JWT；
    # 2. 使用相同密钥重新计算签名；
    # 3. 检查签名是否一致；
    # 4. 检查exp是否已经过期；
    # 5. 返回Payload字典。
    # 如果decode检查之后发现令牌有问题他会直接抛出异常
    payload = jwt.decode(
        jwt=token,
        key=settings.jwt_secret_key,
        algorithms=[
            settings.jwt_algorithm,
        ],

        # 把本方法收到的audience交给PyJWT。
        # PyJWT负责检查令牌里的aud是否与它匹配。
        audience=audience,

        # 要求令牌必须包含用户ID和过期时间。
        options={
            "require": ["sub", "exp"],
        },
    )

    # dict.get("sub")读取Payload中的sub。
    # 如果不存在，get()会返回None。
    subject = payload.get(
        "sub"
    )

    if subject is None:
        # InvalidTokenError由PyJWT提供，
        # 表示令牌缺少必要内容或格式无效。
        raise InvalidTokenError(
            "JWT中缺少sub字段"
        )

    try:
        # JWT中的sub是字符串，
        # 转换回项目使用的UUID对象。
        user_id = UUID(
            subject
        )

    except ValueError as error:
        # 如果sub不是合法UUID，
        # 将普通ValueError转换成无效令牌异常。
        raise InvalidTokenError(
            "JWT中的sub不是合法UUID"
        ) from error

    return user_id