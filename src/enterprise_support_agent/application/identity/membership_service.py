"""
membership_service.py

主要功能：
    处理用户加入组织的完整业务流程。

主要部件：
    MembershipService：
        检查组织是否存在；
        检查用户是否存在；
        检查成员关系是否重复；
        创建并提交成员关系。
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.common.exceptions import (
    OrganizationMembershipAlreadyExistsError,
    OrganizationNotFoundError,
    UserNotFoundError,
    OrganizationMembershipNotFoundError
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.organization_repository import (
    OrganizationRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.user_repository import (
    UserRepository,
)


class MembershipService:
    """组织成员关系业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

        # 三个Repository共享本次请求的同一个Session。
        self.organization_repository = (
            OrganizationRepository(session)
        )
        self.user_repository = UserRepository(
            session
        )
        self.membership_repository = (
            MembershipRepository(session)
        )

    async def add_member(
        self,
        organization_id: UUID,
        user_id: UUID,
        role: str,
    ) -> OrganizationMembership:
        """把用户加入指定组织。"""

        # 确认组织真实存在。
        organization = (
            await self.organization_repository.get_by_id(
                organization_id
            )
        )

        if organization is None:
            raise OrganizationNotFoundError(
                organization_id
            )

        # 确认用户真实存在。
        user = await self.user_repository.get_by_id(
            user_id
        )

        if user is None:
            raise UserNotFoundError(
                user_id
            )

        # 检查用户是否已经加入这个组织。
        existing_membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=user_id,
            )
        )

        if existing_membership is not None:
            raise OrganizationMembershipAlreadyExistsError(
                organization_id=organization_id,
                user_id=user_id,
            )

        try:
            membership = (
                await self.membership_repository.create(
                    organization_id=organization_id,
                    user_id=user_id,
                    role=role,
                )
            )

            # 将成员关系永久保存到数据库。
            await self.session.commit()

            return membership

        except IntegrityError as error:
            # 防止两个并发请求同时添加相同成员。
            await self.session.rollback()

            raise OrganizationMembershipAlreadyExistsError(
                organization_id=organization_id,
                user_id=user_id,
            ) from error

    async def list_members(
            self,
            organization_id: UUID,
    ) -> list[OrganizationMembership]:
        """查询指定组织的全部成员关系。"""

        # 先确认组织本身确实存在。
        organization = (
            await self.organization_repository.get_by_id(
                organization_id
            )
        )

        if organization is None:
            raise OrganizationNotFoundError(
                organization_id
            )

        # 查询并返回该组织的全部成员关系。
        return (
            await self.membership_repository.list_by_organization(
                organization_id
            )
        )

    async def update_member_role(
            self,
            organization_id: UUID,
            user_id: UUID,
            role: str,
    ) -> OrganizationMembership:
        """修改用户在指定组织中的角色。"""

        # 先确认组织存在。
        organization = (
            await self.organization_repository.get_by_id(
                organization_id
            )
        )

        if organization is None:
            raise OrganizationNotFoundError(
                organization_id
            )

        # 再确认用户存在。
        user = await self.user_repository.get_by_id(
            user_id
        )

        if user is None:
            raise UserNotFoundError(
                user_id
            )

        # 查询这个用户与组织之间的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=user_id,
            )
        )

        # 用户和组织都存在，但用户没有加入这个组织。
        if membership is None:
            raise OrganizationMembershipNotFoundError(
                organization_id=organization_id,
                user_id=user_id,
            )

        # 修改成员角色。
        updated_membership = (
            await self.membership_repository.update_role(
                membership=membership,
                role=role,
            )
        )

        # 正式提交数据库事务。
        await self.session.commit()

        return updated_membership

    async def remove_member(
            self,
            organization_id: UUID,
            user_id: UUID,
    ) -> None:
        """把指定用户从组织中移除。"""

        # 确认组织存在。
        organization = (
            await self.organization_repository.get_by_id(
                organization_id
            )
        )

        if organization is None:
            raise OrganizationNotFoundError(
                organization_id
            )

        # 确认用户存在。
        user = await self.user_repository.get_by_id(
            user_id
        )

        if user is None:
            raise UserNotFoundError(
                user_id
            )

        # 查询需要删除的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=user_id,
            )
        )

        # 用户存在，但并不属于这个组织。
        if membership is None:
            raise OrganizationMembershipNotFoundError(
                organization_id=organization_id,
                user_id=user_id,
            )

        # 删除成员关系。
        await self.membership_repository.delete(
            membership
        )

        # 正式提交删除事务。
        await self.session.commit()