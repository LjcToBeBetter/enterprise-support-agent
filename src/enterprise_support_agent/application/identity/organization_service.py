"""
organization_service.py

主要功能：
    处理组织相关的业务规则和事务。

主要部件：
    OrganizationService：
        检查组织编码是否重复；
        调用Repository创建组织；
        成功后提交事务；
        发生唯一约束冲突时转换成业务异常。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.common.exceptions import (
    OrganizationCodeAlreadyExistsError,OrganizationNotFoundError
)
from enterprise_support_agent.infrastructure.database.models.organization import (
    Organization,
)
from enterprise_support_agent.infrastructure.database.repositories.organization_repository import (
    OrganizationRepository,
)
from uuid import UUID

from enterprise_support_agent.application.identity.organization_roles import (
    OrganizationRole,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)


class OrganizationService:
    """组织业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        # 保存本次请求的数据库会话。
        self.session = session

        # Repository负责执行Organization表的数据库操作。
        self.repository = OrganizationRepository(
            session=session
        )

        # MembershipRepository负责操作组织成员关系表。
        self.membership_repository = MembershipRepository(
            session=session
        )

    # 该方法用于创建组织，并自动让创建者成为组织管理员。
    #
    # 接收：
    #     name：组织名称；
    #     code：组织编码；
    #     creator_user_id：当前登录用户ID。
    #
    # 返回：
    #     创建完成的Organization ORM对象
    async def create_organization(
        self,
        name: str,
        code: str,
        creator_user_id: UUID,
    ) -> Organization:
        """检查业务规则并创建组织。"""

        # 去除组织名称两端多余的空格。
        normalized_name = name.strip()

        # 组织编码统一转成小写，并去除两端空格。
        normalized_code = code.strip().lower()

        # 先查询数据库，给用户返回容易理解的重复提示。
        existing_organization = (
            await self.repository.get_by_code(
                normalized_code
            )
        )

        if existing_organization is not None:
            raise OrganizationCodeAlreadyExistsError(
                normalized_code
            )

        try:
            # Repository负责执行INSERT和flush。
            organization = await self.repository.create(
                name=normalized_name,
                code=normalized_code,
            )

            # 创建组织后，自动创建一条成员关系：
            # 当前登录用户属于这个新组织，并且角色是admin。
            await self.membership_repository.create(
                organization_id=organization.id,
                user_id=creator_user_id,
                role=OrganizationRole.ADMIN,
            )

            # commit()确认整个业务操作成功，
            # 将当前事务中的修改永久保存到数据库。
            await self.session.commit()

            return organization

        except IntegrityError as error:
            # IntegrityError表示数据库约束发生冲突。
            #
            # 即使前面查询时没有重复数据，
            # 两个并发请求仍可能同时创建相同编码。
            # 因此数据库唯一约束仍然是最后一道保护。
            await self.session.rollback()

            # 异常链写法：raise 新异常 from 原异常
            # 表面上抛出：OrganizationCodeAlreadyExistsError
            # 它的真正原因是：原来的IntegrityError
            # 表示：抛出新异常，同时保留error作为导致这个新异常的原始原因。
            # PostgreSQL发现唯一约束冲突
            # → SQLAlchemy抛出IntegrityError
            # → Service捕获IntegrityError
            # → 转换成更容易理解的业务异常
            # → 同时保留原始异常作为原因
            raise OrganizationCodeAlreadyExistsError(
                normalized_code
            ) from error

    async def get_organization(
        self,
        organization_id: UUID,
    ) -> Organization:
        """根据ID查询组织。"""

        # Repository只负责查询数据库。
        organization = await self.repository.get_by_id(
            organization_id
        )

        # Repository查不到时返回None。
        # Service把None转换成有明确含义的业务异常。
        if organization is None:
            raise OrganizationNotFoundError(
                organization_id
            )

        # 找到后返回Organization ORM对象。
        return organization

    async def list_organizations(
            self,

            # 当前登录用户的ID。
            # Repository会根据这个ID，只查询该用户所属的组织。
            user_id: UUID,

            page: int,
            page_size: int,
    ) -> tuple[
        list[Organization],
        int,
        int,
    ]:
        """
        分页查询当前用户所属的组织。

        接收：
            user_id：当前登录用户ID；
            page：当前页码；
            page_size：每页记录数量。

        返回：
            当前页组织列表；
            当前用户所属的组织总数；
            总页数。
        """

        # 把页码转换成需要跳过的记录数量。
        offset = (
                         page - 1
                 ) * page_size

        # 只查询当前用户所属的组织。
        organizations, total = (
            await self.repository.list_page_by_user(
                user_id=user_id,
                offset=offset,
                limit=page_size,
            )
        )

        # 根据记录总数和每页大小，计算总页数。
        total_pages = (
                              total + page_size - 1
                      ) // page_size

        return (
            organizations,
            total,
            total_pages,
        )