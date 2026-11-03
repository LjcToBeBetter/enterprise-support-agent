"""
organization_repository.py

主要功能：
    集中处理Organization表的数据库操作。

主要部件：
    OrganizationRepository：
        根据组织编码查询组织；
        创建新的组织记录。

Repository只负责数据库读写，
不负责HTTP响应和业务规则。
"""

from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.models.organization import (
    Organization,
)
from uuid import UUID
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)

class OrganizationRepository:
    """组织数据访问对象。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        # 保存本次请求使用的数据库会话。
        self.session = session

    async def get_by_code(
        self,
        code: str,
    ) -> Organization | None:
        """根据组织编码查询组织。"""

        # select()创建一条SQLAlchemy查询语句。
        # 它大致对应：SELECT * FROM organizations
        statement = select(Organization).where(
            # where()增加查询条件。
            # 大致对应：WHERE code = 指定值
            Organization.code == code
        )

        # execute()把查询发送给PostgreSQL执行。
        result = await self.session.execute(
            statement
        )

        # scalar_one_or_none()从查询结果中取出：
        # 一条Organization对象，或者在没有结果时返回None。
        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        """根据组织ID查询组织。"""

        # 创建查询语句：
        # SELECT * FROM organizations
        # WHERE id = organization_id
        statement = select(Organization).where(
            Organization.id == organization_id
        )

        # 将查询发送给PostgreSQL并等待结果。
        result = await self.session.execute(
            statement
        )

        # 找到时返回Organization对象；
        # 没找到时返回None。
        return result.scalar_one_or_none()



    async def create(
        self,
        name: str,
        code: str,
    ) -> Organization:
        """创建组织记录，但暂时不提交事务。"""

        # 创建一个对应organizations表的Python对象。
        organization = Organization(
            name=name,
            code=code,
        )

        # add()把对象加入当前Session。
        # 这里只是告诉Session准备保存，还没有执行INSERT。
        self.session.add(organization)

        # flush()把INSERT发送给PostgreSQL，
        # 让数据库生成默认字段并检查约束。
        #
        # flush不会永久提交事务，
        # 后面仍然可以commit或rollback。
        await self.session.flush()

        # refresh()重新从数据库读取当前记录，
        # 把created_at等数据库生成的字段更新到Python对象。
        await self.session.refresh(
            organization
        )

        return organization

    async def list_page_by_user(
            self,
            user_id: UUID,
            offset: int,
            limit: int,
    ) -> tuple[list[Organization], int]:
        """
        分页查询指定用户所属的组织。

        user_id：
            当前登录用户的ID。

        返回：
            当前页的组织列表；
            该用户所属的组织总数。
        """

        # organizations和organization_memberships通过组织ID连接。
        #
        # 然后只保留user_id等于当前用户ID的成员关系。
        # 所以不会查询出其他用户所属的组织。
        count_statement = (
            select(func.count())
            .select_from(Organization)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id
                == Organization.id,
            )
            .where(
                OrganizationMembership.user_id
                == user_id
            )
        )

        # 查询当前用户一共属于多少个组织。
        total = await self.session.scalar(
            count_statement
        )

        # 查询当前用户所属的当前页组织。
        statement = (
            select(Organization)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id
                == Organization.id,
            )
            .where(
                OrganizationMembership.user_id
                == user_id
            )
            .order_by(
                Organization.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        organizations = list(
            result.all()
        )

        return organizations, int(total or 0)