"""
auth_service.py

主要功能：
    处理用户登录的完整业务流程。

主要部件：
    AuthService：
        根据邮箱查询用户；
        验证用户密码；
        检查账号是否可用；
        生成JWT访问令牌。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
)
from enterprise_support_agent.config import (
    settings,
)
from enterprise_support_agent.infrastructure.database.repositories.user_repository import (
    UserRepository,
)
from enterprise_support_agent.security.passwords import (
    verify_password,
)
from enterprise_support_agent.security.tokens import (
    create_access_token,
)


class AuthService:
    """用户登录认证服务。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.repository = UserRepository(
            session=session
        )

    async def login(
        self,
        email: str,
        plain_password: str,
    ) -> tuple[str, int]:
        """
        验证用户并生成JWT。

        返回：
            JWT字符串；
            JWT有效秒数。
        """

        # 邮箱统一去除两端空格并转成小写。
        normalized_email = (
            email.strip().lower()
        )

        # 根据邮箱查询用户。
        user = await self.repository.get_by_email(
            normalized_email
        )

        # 邮箱不存在时，不告诉前端具体原因。
        if user is None:
            raise InvalidCredentialsError()

        # verify_password()会在线程池中执行Argon2校验。
        #
        # 它接收：
        # 用户本次输入的明文密码；
        # 数据库中保存的密码哈希。
        #
        # 返回True表示密码正确，False表示错误。
        password_is_valid = await verify_password(
            plain_password=plain_password,
            password_hash=user.password_hash,
        )

        if not password_is_valid:
            raise InvalidCredentialsError()

        # is_active=False表示账号已经被停用。
        if not user.is_active:
            raise InactiveUserError(
                user.id
            )

        # 根据用户ID生成JWT字符串。
        access_token = create_access_token(
            user.id
        )

        # 配置中的单位是分钟，
        # 响应中的expires_in使用秒。
        expires_in = (
            settings.jwt_access_token_expire_minutes
            * 60
        )

        return access_token, expires_in