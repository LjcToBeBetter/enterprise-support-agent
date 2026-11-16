"""检查Redis限流计数，以及计数到期后的重置。"""

import asyncio
from uuid import uuid4

from enterprise_support_agent.infrastructure.cache.redis_connection import (
    open_redis_connection,
)
from enterprise_support_agent.infrastructure.cache.rate_limiter import (
    RedisRateLimiter,
)


async def main() -> None:
    """模拟多次请求，验证限流和到期重置。"""

    # 专门生成一个测试键，不影响真实用户的计数。
    key = f"enterprise-support:check:rate_limit:{uuid4()}"

    async with open_redis_connection() as client:
        limiter = RedisRateLimiter(client=client)

        try:
            # 为了快速验证，这里临时采用：
            # 5秒内最多允许2次。
            # 不会修改真实接口“60秒20次”的规则。
            for request_number in range(1, 4):
                retry_after = await limiter.check_request(
                    key=key,
                    limit=2,
                    window_seconds=5,
                )

                # 返回0表示允许，正整数表示被限流。
                allowed = retry_after == 0

                # 第1、2次应该允许，第3次应该被限流。
                expected_allowed = request_number <= 2

                if allowed != expected_allowed:
                    raise RuntimeError("限流结果不符合预期")

                if allowed:
                    print(f"第{request_number}次：允许")
                else:
                    print(
                        f"第{request_number}次：被限流，"
                        f"建议等待{retry_after}秒"
                    )

            print("等待6秒，让旧计数过期……")

            # 异步等待6秒，超过刚才设置的5秒有效期。
            await asyncio.sleep(6)

            # 旧键过期后，这次请求应该从1重新计数。
            retry_after = await limiter.check_request(
                key=key,
                limit=2,
                window_seconds=5,
            )

            if retry_after != 0:
                raise RuntimeError("计数过期后没有恢复请求资格")

            print("计数过期后：重新允许")

        finally:
            # 只删除本次测试使用的键。
            await client.delete(key)


if __name__ == "__main__":
    print("正在检查Redis限流……", flush=True)
    asyncio.run(main())