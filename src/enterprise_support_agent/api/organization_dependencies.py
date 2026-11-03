"""
organization_dependencies.py

主要功能：
    提供组织访问权限相关的FastAPI依赖。

当前部件：
    require_organization_member：
        检查当前登录用户是否属于指定组织；
        检查成功后返回成员关系对象。
"""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.application.exceptions import (
    OrganizationAccessDeniedError,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
from enterprise_support_agent.application.organization_roles import (
    OrganizationRole,
)

# 该方法用于检查当前登录用户是否属于URL指定的组织。
#
# 调用时机：
#     需要组织成员身份的接口执行之前，
#     由FastAPI通过Depends自动调用。
#
# 参数来源：
#     organization_id：
#         FastAPI从URL路径中读取。
#
#     current_user：
#         get_current_user()验证JWT后返回。
#
#     session：
#         get_db_session()提供的数据库会话。
#
# 返回：
#     当前用户在指定组织中的OrganizationMembership记录。
#
# 异常：
#     查不到成员关系时，抛出OrganizationAccessDeniedError，
#     最终返回403。
async def require_organization_member(
    organization_id: UUID,

    current_user: User = Depends(
        get_current_user
    ),

    session: AsyncSession = Depends(
        get_db_session
    ),
) -> OrganizationMembership:
    """检查当前登录用户是否属于指定组织。"""

    repository = MembershipRepository(
        session=session
    )

    membership = (
        await repository
        .get_by_organization_and_user(
            organization_id=organization_id,
            user_id=current_user.id,
        )
    )

    if membership is None:
        raise OrganizationAccessDeniedError(
            organization_id
        )

    return membership

# 该方法用于检查当前用户是否是URL指定组织的管理员。
#
# 调用时机：
#     需要管理员权限的接口执行之前，
#     由FastAPI通过Depends自动调用。
#
# 接收：
#     require_organization_member返回的成员关系对象。
#
# 返回：
#     验证通过后的OrganizationMembership对象。
#
# 异常：
#     当前用户不是管理员时，抛出403权限异常。
async def require_organization_admin(
    membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> OrganizationMembership:
    """要求当前用户必须是指定组织的管理员。"""

    if membership.role != OrganizationRole.ADMIN:
        raise OrganizationAccessDeniedError(
            membership.organization_id
        )

    return membership