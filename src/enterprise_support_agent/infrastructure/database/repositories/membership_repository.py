"""
membership_repository.py

主要功能：
    处理OrganizationMembership表的数据库操作。

主要部件：
    MembershipRepository：
        查询用户是否已经属于某个组织；
        创建组织成员关系。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)


class MembershipRepository:
    """组织成员关系数据访问对象。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def get_by_organization_and_user(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> OrganizationMembership | None:
        """查询用户是否已经属于指定组织。"""

        statement = select(
            OrganizationMembership
        ).where(
            # where()可以同时接收多个条件，
            # 多个条件之间默认使用AND连接。
            OrganizationMembership.organization_id
            == organization_id,

            OrganizationMembership.user_id
            == user_id,
        )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def create(
        self,
        organization_id: UUID,
        user_id: UUID,
        role: str,
    ) -> OrganizationMembership:
        """创建成员关系，但暂时不提交事务。"""

        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )

        self.session.add(
            membership
        )

        # 执行INSERT，但仍然可以rollback。
        await self.session.flush()

        # 重新读取数据库生成的ID和时间字段。
        await self.session.refresh(
            membership
        )

        return membership

    async def list_by_organization(
            self,
            organization_id: UUID,
    ) -> list[OrganizationMembership]:
        """查询指定组织的全部成员关系。"""

        statement = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id
                == organization_id
            )
            .order_by(
                OrganizationMembership.created_at.asc()
            )
        )

        # 执行查询语句。
        result = await self.session.execute(
            statement
        )

        # scalars()只取OrganizationMembership对象，
        # all()取出全部查询结果，
        # list()将结果转换成普通Python列表。
        return list(
            result.scalars().all()
        )

    async def update_role(
            self,
            membership: OrganizationMembership,
            role: str,
    ) -> OrganizationMembership:
        """修改成员关系中的角色，但暂时不提交事务。"""

        # membership是从数据库查询出来的ORM对象。
        # 修改它的role属性后，SQLAlchemy会记录这个变化。
        membership.role = role

        # 把UPDATE语句发送给数据库，
        # 但事务还没有commit，仍然可以回滚。
        await self.session.flush()

        # 从数据库重新读取更新后的字段，
        # 例如updated_at。
        await self.session.refresh(
            membership
        )

        return membership

    async def delete(
            self,
            membership: OrganizationMembership,
    ) -> None:
        """删除一条组织成员关系，但暂时不提交事务。"""

        # 告诉Session准备删除这条成员关系记录。
        await self.session.delete(
            membership
        )

        # 执行DELETE语句，
        # 但还没有commit，出现错误仍然可以回滚。
        await self.session.flush()