"""
使用Redis统计请求次数，判断请求是否超过频率限制。
限制的是用户请求我们后端接口的次数
例如限制 Agent 问答接口“同一个用户60秒内最多请求20次”：
"""

from redis.asyncio import Redis


class RedisRateLimiter:
    """在指定时间段内，限制同一个键对应的请求次数。"""

    def __init__(self, client: Redis) -> None:
        """保存已有的Redis客户端，复用应用创建的连接池。"""

        self.client = client

    async def check_request(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> int:
        """
        记录一次请求，并判断是否超出限制。

        key：计数键，后面会包含组织ID、用户ID等信息。计数键就是标识“正在统计谁、哪个接口的请求次数”。
        limit：这个时间段内最多允许多少次请求。
        window_seconds：时间段长度，单位为秒。

        返回0：允许请求。
        返回正整数：超过限制，建议等待这么多秒后重试。

        时间段从第一次请求开始，到期后计数自动清除。
        """

        if limit < 1 or window_seconds < 1:
            raise ValueError("请求次数和时间段长度必须大于0")

        # pipeline是客户端提供的“批量命令容器”。
        # 先把命令放进去，再通过execute()统一发送。
        #
        # transaction=True表示使用Redis事务，
        # 执行这一组命令时，不让其他客户端的命令插进来。
        async with self.client.pipeline(
            transaction=True,
        ) as pipeline:

            # incr()：将这个键的整数值加1。
            # 键不存在时，从0开始加，第一次得到1。
            #
            # 注意：这里先把命令加入pipeline，
            # 尚未发送，因此这里不写await。
            pipeline.incr(key)

            # 给计数设置有效期。
            # nx=True：只有这个键尚未设置有效期时才设置，
            # 避免每次请求都重新开始倒计时。
            # 实现了到期后清零,即用户请求次数在window_seconds秒后清零
            pipeline.expire(
                key,  # 要设置有效期的计数键
                window_seconds,  # 多少秒后过期，例如60秒
                nx=True,  # 已有有效期就保持原样
            )

            # 查询距离这个计数过期还剩多少秒。
            pipeline.ttl(key)

            # 真正发送并执行上面三个命令。
            # 返回列表，顺序与加入命令的顺序一致。
            results = await pipeline.execute()

        # 第一个结果来自incr()：当前累计请求次数。
        current_count = int(results[0])

        # 第三个结果来自ttl()：剩余有效期。
        remaining_seconds = int(results[2])

        if current_count <= limit:
            # 没超过次数限制，允许本次请求。
            return 0

        # 超过限制，返回建议等待时间。
        # 剩余时间不足1秒时，至少提示等待1秒。
        return max(remaining_seconds, 1)