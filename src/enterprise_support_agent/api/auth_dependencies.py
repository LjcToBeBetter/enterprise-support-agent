"""
auth_dependencies.py

主要功能：
    从HTTP请求头中读取Bearer令牌；
    验证JWT；
    根据JWT中的用户ID查询当前登录用户。

主要部件：
    bearer_scheme：
        。告诉FastAPI从Authorization请求头读取Bearer令牌

    get_current_user：
        验证令牌并返回当前登录用户。
"""

from fastapi import (
    Depends,
    HTTPException,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.exceptions import (
    InactiveUserError,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.repositories.user_repository import (
    UserRepository,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
from enterprise_support_agent.security.tokens import (
    decode_access_token,
)


# HTTPBearer由FastAPI提供。
#
# 它会从下面的请求头中读取令牌：
# Authorization: Bearer JWT字符串
#
# auto_error=False表示没有携带令牌时，
# 先返回None，由我们自己决定错误内容。
bearer_scheme = HTTPBearer(
    auto_error=False
)


async def get_current_user(
    # Depends(bearer_scheme)表示：
    # FastAPI先执行bearer_scheme读取Authorization请求头，
    # 再把读取结果传入credentials。
    credentials: (
        HTTPAuthorizationCredentials | None
    ) = Depends(bearer_scheme),

    session: AsyncSession = Depends(
        get_db_session
    ),
) -> User:
    """验证JWT并返回当前登录用户。"""

    # 没有Authorization请求头，
    # 或者请求头不符合Bearer格式。
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="请先登录",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # credentials.credentials是Bearer后面的JWT字符串。
    token = credentials.credentials

    try:
        # 验证JWT签名和有效期，
        # 验证成功后返回JWT中的用户ID。
        user_id = decode_access_token(
            token
        )

    except InvalidTokenError as error:
        # JWT过期、签名错误或格式错误，
        # 统一转换成401响应。
        raise HTTPException(
            status_code=401,
            detail="登录凭证无效或已过期",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        ) from error

    repository = UserRepository(
        session=session
    )

    # 使用JWT中的用户ID查询数据库。
    user = await repository.get_by_id(
        user_id
    )

    # JWT中的用户可能已经被删除。
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="登录用户不存在",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if not user.is_active:
        raise InactiveUserError(
            user.id
        )

    return user