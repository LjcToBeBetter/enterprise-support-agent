"""
auth_router.py

主要功能：
    提供用户登录相关的HTTP接口。

当前接口：
    POST /auth/login
        接收邮箱和密码；
        调用AuthService验证用户；
        返回JWT访问令牌。
"""

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.auth_schemas import (
    LoginRequest,
    TokenResponse,
)
from enterprise_support_agent.application.auth_service import (
    AuthService,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)

from enterprise_support_agent.api.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.api.user_schemas import (
    UserResponse,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    # FastAPI从JSON请求体中读取邮箱和密码，
    # 并使用LoginRequest进行校验。
    request_data: LoginRequest,

    # FastAPI自动创建并传入数据库会话。
    session: AsyncSession = Depends(
        get_db_session
    ),
) -> TokenResponse:
    """使用邮箱和密码登录并获取JWT。"""

    service = AuthService(
        session=session
    )

    access_token, expires_in = (
        await service.login(
            email=str(request_data.email),

            # SecretStr不会自动提供明文，
            # 只有真正验证密码时才取出。
            plain_password=(
                request_data.password.get_secret_value()
            ),
        )
    )

    # 将JWT和有效时间包装成规定的响应格式。
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_my_profile(
    # 访问这个接口前，自动检查JWT。
    # 检查成功后，current_user就是当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> UserResponse:
    """查询当前登录用户。"""

    return UserResponse.model_validate(
        current_user
    )