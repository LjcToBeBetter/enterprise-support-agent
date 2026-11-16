"""
organization_router.py

主要功能：
    定义组织相关的HTTP接口。

主要部件：
    router：
        保存组织接口的路由对象。

    create_organization：
        接收创建组织请求；
        获取数据库会话；
        调用OrganizationService；
        返回创建后的组织信息。
"""

from fastapi import (
    APIRouter,
    Depends,
    status,
    Query
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.organizations.organization_schemas import (
    CreateOrganizationRequest,
    OrganizationResponse,
    OrganizationListResponse
)
from enterprise_support_agent.application.identity.organization_service import (
    OrganizationService,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
from uuid import UUID
from enterprise_support_agent.api.auth.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.api.organizations.organization_dependencies import (
    require_organization_member,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)



# 创建组织模块的路由对象。
#
# prefix表示当前文件中的所有接口，
# 路径前面都会自动加上/organizations。
router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)


@router.post(
    # 最终路径由prefix和这里的空字符串组合：
    # POST /organizations
    "",

    # 规定成功响应必须符合OrganizationResponse格式。
    response_model=OrganizationResponse,

    # 201表示服务器成功创建了新资源。
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    # FastAPI会把请求体解析并校验成这个对象。
    request_data: CreateOrganizationRequest,

    # Depends()告诉FastAPI：
    # 调用接口前，先执行get_db_session()取得数据库会话。
    #
    # 请求结束后，get_db_session()会继续完成会话清理。
    session: AsyncSession = Depends(
        get_db_session
    ),
    # 创建组织前，FastAPI会先调用get_current_user()验证JWT。
    #
    # 验证成功后：
    #     current_user是当前登录用户的User ORM对象。
    #
    # 验证失败：
    #     直接返回401，不会执行创建组织逻辑。
    current_user: User = Depends(
        get_current_user
    ),
) -> OrganizationResponse:
    """创建一个企业组织。"""

    # 使用本次请求的数据库会话创建Service。
    service = OrganizationService(
        session=session
    )

    # Service负责检查重复编码、写入数据库和提交事务。
    organization = await service.create_organization(
        name=request_data.name,
        code=request_data.code,

        # 当前登录用户就是新组织的创建者。
        creator_user_id=current_user.id,
    )

    # model_validate()根据OrganizationResponse的字段要求，
    # 从SQLAlchemy的Organization对象中读取数据，
    # 创建最终的Pydantic响应对象。
    return OrganizationResponse.model_validate(
        organization
    )

@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
async def get_organization(
    # URL中的organization_id会被FastAPI转换成UUID对象。
    # 如果格式不是合法UUID，FastAPI会直接返回422。
    organization_id: UUID,

    # 为本次请求创建独立数据库会话。
    session: AsyncSession = Depends(
        get_db_session
    ),
    # 调用接口前，检查当前登录用户是否属于这个组织。
    #
    # FastAPI会把路径中的organization_id交给
    # require_organization_member()进行查询。
    #
    # 用户不属于该组织时，会直接返回403，
    # 不会继续执行下面的接口代码。
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> OrganizationResponse:
    """根据ID查询组织。"""

    service = OrganizationService(
        session=session
    )

    # Service查不到时会抛出OrganizationNotFoundError。
    organization = await service.get_organization(
        organization_id
    )

    # 把Organization ORM对象转换成响应模型。
    return OrganizationResponse.model_validate(
        organization
    )

@router.get(
    "",
    response_model=OrganizationListResponse,
)
async def list_organizations(
    # Query()表示page来自URL查询参数。
    #
    # 默认值是1；
    # ge=1表示page必须大于等于1。
    page: int = Query(
        default=1,
        ge=1,
    ),

    # 每页默认20条；
    # 最少1条，最多100条，防止一次查询过多数据。
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 调用接口前，FastAPI先验证JWT。
    #
    # 验证成功后，current_user就是当前登录用户的User ORM对象。
    # 后面使用current_user.id限制组织查询范围。
    current_user: User = Depends(
        get_current_user
    ),
) -> OrganizationListResponse:
    """分页查询组织列表。"""

    service = OrganizationService(
        session=session
    )

    organizations, total, total_pages = (
        await service.list_organizations(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    )

    # 把每个Organization ORM对象
    # 转换成OrganizationResponse对象。
    items: list[OrganizationResponse] = []

    for organization in organizations:
        response_item = (
            OrganizationResponse.model_validate(
                organization
            )
        )

        items.append(
            response_item
        )

    return OrganizationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )