"""
user_service.py

主要功能：
    处理创建用户的业务流程。

主要部件：
    UserService：
        规范化邮箱和姓名；
        检查邮箱是否重复；
        把明文密码转换成哈希；
        调用Repository创建用户；
        提交数据库事务。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.exceptions import (
    UserEmailAlreadyExistsError,
    UserNotFoundError,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.repositories.user_repository import (
    UserRepository,
)
from enterprise_support_agent.security.passwords import (
    hash_password,
)
from uuid import UUID


class UserService:
    """用户业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session
        self.repository = UserRepository(
            session=session
        )

    async def create_user(
        self,
        email: str,
        display_name: str,
        plain_password: str,
    ) -> User:
        """检查业务规则并创建用户。"""

        # 邮箱统一去除空格并转为小写，
        # 避免Test@example.com和test@example.com被当成两个用户。
        normalized_email = email.strip().lower()

        normalized_display_name = (
            display_name.strip()
        )

        # 先检查邮箱是否已经存在。
        # 因为同一个邮箱只能对应一个用户，如果邮箱已经存在了那么这个用户就不应该被新建
        existing_user = (
            await self.repository.get_by_email(
                normalized_email
            )
        )

        if existing_user is not None:
            raise UserEmailAlreadyExistsError(
                normalized_email
            )

        # 将明文密码转换成Argon2哈希。
        # 明文密码不会传给Repository，也不会保存进数据库。
        password_hash = await hash_password(
            plain_password
        )

        try:
            user = await self.repository.create(
                email=normalized_email,
                display_name=normalized_display_name,
                password_hash=password_hash,
            )

            # 永久保存新用户。
            await self.session.commit()

            return user

        except IntegrityError as error:
            # 防止两个并发请求同时创建相同邮箱。
            await self.session.rollback()

            raise UserEmailAlreadyExistsError(
                normalized_email
            ) from error

    async def get_user_by_id(
            self,
            user_id: UUID,
    ) -> User:
        """根据用户ID查询用户。"""

        user = await self.repository.get_by_id(
            user_id
        )

        if user is None:
            raise UserNotFoundError(
                user_id
            )

        return user

    async def list_users(
            self,
            page: int,
            page_size: int,
    ) -> tuple[
        list[User],
        int,
        int,
    ]:
        """
        分页查询用户。

        返回：
            当前页用户列表；
            用户总数；
            总页数。
        """

        # 将页码转换成需要跳过的记录数量。
        #
        # 第1页：(1 - 1) * page_size = 0
        # 第2页：(2 - 1) * page_size = page_size
        offset = (
                         page - 1
                 ) * page_size

        users, total = (
            await self.repository.list_page(
                offset=offset,
                limit=page_size,
            )
        )

        # 向上取整计算总页数。
        total_pages = (
                              total + page_size - 1
                      ) // page_size

        return (
            users,
            total,
            total_pages,
        )