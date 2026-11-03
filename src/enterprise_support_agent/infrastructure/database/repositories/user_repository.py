"""
user_repository.py

主要功能：
    集中处理User表的数据库操作。

主要部件：
    UserRepository：
        根据邮箱查询用户；
        创建新的用户记录。

Repository只负责数据库读写，
不负责密码哈希和业务规则。
"""

# func 用来调用数据库中的 SQL函数。例如func.count()
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from uuid import UUID

class UserRepository:
    """用户数据访问对象。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        """根据邮箱查询用户。"""

        statement = select(User).where(
            User.email == email
        )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> User:
        """创建用户记录，但暂时不提交事务。"""

        user = User(
            email=email,
            display_name=display_name,
            password_hash=password_hash,
        )

        # 将User对象加入当前Session的待保存区域。
        self.session.add(user)

        # 执行INSERT，但暂时不永久提交。
        await self.session.flush()

        # 重新读取数据库生成的id和时间字段。
        await self.session.refresh(
            user
        )

        return user

    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        """根据用户ID查询用户。"""

        statement = select(User).where(
            User.id == user_id
        )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def list_page(
            self,
            offset: int,
            limit: int,
    ) -> tuple[list[User], int]:
        """分页查询用户，并返回用户列表和总记录数。"""

        # 统计users表中一共有多少条用户记录。
        count_statement = (
            select(func.count())
            .select_from(User)
        )
        # 返回的是SQLALchemy结果查询对象，而不是纯粹的结果
        count_result = await self.session.execute(
            count_statement
        )

        # 提取出结果
        total = count_result.scalar_one()

        # 查询当前这一页的用户。
        statement = (
            select(User)
            .order_by(
                User.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(
            statement
        )

        users = list(
            result.scalars().all()
        )

        return users, total