"""
auth_schemas.py

主要功能：
    定义用户登录时的请求格式，
    以及登录成功后的JWT响应格式。

主要部件：
    LoginRequest：
        接收邮箱和明文密码。

    TokenResponse：
        返回访问令牌、令牌类型和有效时间。
"""

from typing import Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
)


class LoginRequest(BaseModel):
    """用户登录时提交的数据。"""

    # EmailStr会校验邮箱格式。
    email: EmailStr

    # SecretStr会在打印对象和日志时隐藏密码。
    # 它不会加密密码，真正校验时仍需取出明文。
    password: SecretStr = Field(
        min_length=8,
        max_length=128,
    )


class TokenResponse(BaseModel):
    """登录成功后返回的JWT信息。"""

    # 后端生成的JWT字符串。
    access_token: str

    # Literal表示这个字段只能是固定字符串bearer。
    # bearer 是 HTTP认证标准中的一种令牌使用方式，意思是“持有者令牌”
    # 含义是：谁拿到这个令牌，谁就能用它访问接口。因此JWT必须通过 HTTPS传输，不能泄露。
    token_type: Literal["bearer"] = "bearer"

    # JWT还有多少秒过期。
    expires_in: int