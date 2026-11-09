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
from fastapi import (
    APIRouter,
    Depends,
    Response,
)
from enterprise_support_agent.config import settings

from enterprise_support_agent.security.mcp_tokens import (
    create_mcp_access_token,
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


@router.post(
    "/mcp-token",
    response_model=TokenResponse,
    summary="申请MCP专用访问令牌",
)
async def issue_mcp_token(
    # FastAPI注入的响应对象，可用来设置响应头。
    response: Response,

    # 先校验普通登录令牌，并查询当前用户。
    # 验证失败时，不会进入下面的签发逻辑。
    current_user: User = Depends(
        get_current_user
    ),
) -> TokenResponse:
    """为当前已登录用户签发知识库检索用途的MCP令牌。"""

    # 用户ID来自已验证的身份，
    # 不接受前端或模型自行填写的用户ID。
    access_token = create_mcp_access_token(
        user_id=current_user.id,
    )

    # 告诉浏览器和代理：不要缓存包含令牌的响应。
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    # 复用已有响应格式。
    # 配置单位是分钟，expires_in的单位是秒。
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=(
            settings.jwt_access_token_expire_minutes * 60
        ),
    )