"""在执行Agent接口前，检查当前用户的请求频率。"""

import logging

from fastapi import Depends, HTTPException, Request

# Redis客户端操作失败时抛出的异常的共同父类。
from redis.exceptions import RedisError

from enterprise_support_agent.api.organization_dependencies import (
    require_organization_member,
)
from enterprise_support_agent.infrastructure.cache.rate_limiter import (
    RedisRateLimiter,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)


logger = logging.getLogger(__name__)


async def require_agent_rate_limit(
    # FastAPI提供本次请求，通过它取得共享的Redis客户端。
    request: Request,

    # 先验证登录身份，以及当前用户是否属于这个组织。
    # 验证通过后，得到成员关系，其中包含组织ID和用户ID。
    membership: OrganizationMembership = Depends(
        require_organization_member,
    ),
) -> None:
    """
    限制同一用户在同一组织中的Agent请求次数。

    从第一次请求开始，60秒内最多允许20次。
    未超限：正常结束，让接口继续执行。
    超限：抛出HTTPException，返回429，停止执行接口。
    """

    # 每个组织中的每个用户都有自己的计数，
    # 避免不同用户、不同组织的请求次数混在一起。
    key = (
        f"rate_limit:agent:"
        f"{membership.organization_id}:"
        f"{membership.user_id}"
    )

    # 取得lifespan创建的客户端，交给限流计数器使用。
    limiter = RedisRateLimiter(
        client=request.app.state.redis_client,
    )

    try:
        # 这个用户又请求了一次：计数加1，并判断是否超限。
        # 返回0表示允许，正整数表示建议等待的秒数。
        retry_after = await limiter.check_request(
            key=key,
            limit=20,
            window_seconds=60,
        )

    except RedisError as exc:
        # Redis不可用时无法检查次数，
        # 记录详细原因，并向客户端返回503。
        logger.exception("Agent请求限流检查失败")

        raise HTTPException(
            status_code=503,
            detail="请求频率检查暂时不可用，请稍后重试",
        ) from exc

    if retry_after > 0:
        # 超过次数限制，直接结束本次接口请求。
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁，请在{retry_after}秒后重试",

            # Retry-After是HTTP响应头，
            # 告诉客户端建议等待多少秒再发送请求。
            headers={
                "Retry-After": str(retry_after),
            },
        )

    # 没有超限，方法正常结束。
    # 后面挂到接口上后，FastAPI就会继续执行接口函数。