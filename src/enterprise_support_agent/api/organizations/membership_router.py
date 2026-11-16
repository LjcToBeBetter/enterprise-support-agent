"""
membership_router.py

主要功能：
    提供组织成员关系相关的 HTTP 接口。

当前接口：
    POST /organizations/{organization_id}/members

执行流程：
    接收组织ID、用户ID和角色，
    调用 MembershipService 完成业务校验和数据库写入，
    最后返回创建好的成员关系。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.organizations.membership_schemas import (
    AddOrganizationMemberRequest,
    OrganizationMembershipResponse,
    UpdateOrganizationMemberRoleRequest
)
from enterprise_support_agent.application.identity.membership_service import (
    MembershipService,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
from enterprise_support_agent.api.organizations.organization_dependencies import (
    require_organization_admin,
    require_organization_member,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)

# 这个路由文件中的接口统一以 /organizations 开头。
router = APIRouter(
    prefix="/organizations",
    tags=["organization-memberships"],
)


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_member(
    # 从URL路径中读取组织ID。
    organization_id: UUID,

    # 从请求体中读取用户ID和角色。
    request_data: AddOrganizationMemberRequest,

    # FastAPI自动调用get_db_session，提供数据库会话。
    session: AsyncSession = Depends(get_db_session),

    # 添加成员前，FastAPI自动执行require_organization_admin()。
    #
    # 验证通过后会返回当前用户自己的成员关系对象。
    # 当前接口不需要使用这个对象，所以变量名前加下划线。
    #
    # 验证失败时直接返回403，接口主体不会执行。
    _admin_membership: OrganizationMembership = Depends(
        require_organization_admin
    ),
) -> OrganizationMembershipResponse:
    """把一个已经存在的用户加入指定组织。"""

    service = MembershipService(
        session=session
    )

    membership = await service.add_member(
        organization_id=organization_id,
        user_id=request_data.user_id,
        role=request_data.role,
    )

    # 把数据库ORM对象转换成接口规定的响应格式。
    return OrganizationMembershipResponse.model_validate(
        membership
    )


@router.get(
    "/{organization_id}/members",
    response_model=list[
        OrganizationMembershipResponse
    ],
)
async def list_organization_members(
    organization_id: UUID,
    session: AsyncSession = Depends(
        get_db_session
    ),
    # 查询成员列表前，检查当前用户是否属于这个组织。
    _member_membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> list[OrganizationMembershipResponse]:
    """查询指定组织的全部成员关系。"""

    service = MembershipService(
        session=session
    )

    memberships = await service.list_members(
        organization_id
    )

    # 准备最终返回给客户端的响应对象列表。
    response_items = []

    for membership in memberships:
        response_item = (
            OrganizationMembershipResponse.model_validate(
                membership
            )
        )

        response_items.append(
            response_item
        )

    return response_items

@router.patch(
    "/{organization_id}/members/{user_id}",
    response_model=OrganizationMembershipResponse,
)
async def update_organization_member_role(
    #   organization_id和user_id都是读的路径参数

    # 从URL中读取组织ID。
    organization_id: UUID,

    # 从URL中读取需要修改的用户ID。
    user_id: UUID,

    # 从请求体中读取新的角色。
    request_data: UpdateOrganizationMemberRoleRequest,

    # FastAPI自动提供数据库会话。
    session: AsyncSession = Depends(
        get_db_session
    ),
    # 修改角色前，检查当前用户是否是组织管理员。
    _admin_membership: OrganizationMembership = Depends(
        require_organization_admin
    ),
) -> OrganizationMembershipResponse:
    """修改用户在指定组织中的角色。"""

    service = MembershipService(
        session=session
    )

    membership = await service.update_member_role(
        organization_id=organization_id,
        user_id=user_id,
        role=request_data.role,
    )

    return OrganizationMembershipResponse.model_validate(
        membership
    )


@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_organization_member(
    # 从URL中读取组织ID。
    organization_id: UUID,

    # 从URL中读取需要移除的用户ID。
    user_id: UUID,

    # FastAPI自动提供数据库会话。
    session: AsyncSession = Depends(
        get_db_session
    ),
    # 移除成员前，检查当前用户是否是组织管理员。
    _admin_membership: OrganizationMembership = Depends(
        require_organization_admin
    ),
) -> None:
    """把指定用户从组织中移除。"""

    service = MembershipService(
        session=session
    )

    await service.remove_member(
        organization_id=organization_id,
        user_id=user_id,
    )