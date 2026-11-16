"""
user_router.py

主要功能：
    定义用户相关的HTTP接口。

主要部件：
    router：
        保存用户接口路由。

    create_user：
        接收创建用户请求；
        获取数据库会话；
        调用UserService；
        返回安全的用户响应。
"""

from fastapi import (
    APIRouter,
    Depends,
    status,
    Query
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.users.user_schemas import (
    CreateUserRequest,
    UserResponse,
    UserListResponse
)
from enterprise_support_agent.application.identity.user_service import (
    UserService,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
from enterprise_support_agent.api.auth.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)



from uuid import UUID

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request_data: CreateUserRequest,
    session: AsyncSession = Depends(
        get_db_session
    ),
) -> UserResponse:
    """创建系统用户。"""

    service = UserService(
        session=session
    )

    user = await service.create_user(
        email=str(request_data.email),
        display_name=request_data.display_name,

        # password是SecretStr对象。
        # get_secret_value()在真正需要哈希时取出明文密码。
        plain_password=(
            request_data.password.get_secret_value()
        ),
    )

    # UserResponse中没有password_hash字段，
    # 因此密码哈希不会被返回给客户端。
    return UserResponse.model_validate(
        user
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
async def get_user(
    # 前端把用户ID放在URL中，
    # FastAPI自动读取并转换成UUID对象。
    user_id: UUID,

    # FastAPI自动创建并传入数据库会话。
    session: AsyncSession = Depends(
        get_db_session
    ),
) -> UserResponse:
    """根据用户ID查询用户。"""

    service = UserService(
        session=session
    )

    user = await service.get_user_by_id(
        user_id
    )

    # 把User ORM对象转换成安全的响应对象。
    # UserResponse没有password_hash字段，
    # 所以不会把密码哈希返回给前端。
    return UserResponse.model_validate(
        user
    )

@router.get(
    "",
    response_model=UserListResponse,
)
async def list_users(
    # Query表示它们来自URL查询参数。
    # ge表示大于等于，le表示小于等于。
    page: int = Query(
        default=1,
        ge=1,
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 执行list_users之前先验证JWT。
    # 认证成功后，这里得到当前登录用户。
    # 他的目的是回答：
    # 是谁在请求查看用户列表？
    # 他有没有登录？
    # 如果没有登陆就不让他查询，是为了安全考虑，防止有人跳过前端，直接用各种开发工具发送请求
    current_user: User = Depends(
        get_current_user
    ),
) -> UserListResponse:
    """分页查询用户。"""

    service = UserService(
        session=session
    )

    users, total, total_pages = (
        await service.list_users(
            page=page,
            page_size=page_size,
        )
    )

    # 将User ORM对象列表转换成UserResponse列表。
    response_items = []

    for user in users:
        response_item = UserResponse.model_validate(
            user
        )

        response_items.append(
            response_item
        )

    return UserListResponse(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )