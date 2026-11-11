"""创建Redis异步客户端，并管理连接的关闭。"""

# 用于标注这个异步生成器通过yield提供的对象类型。
from collections.abc import AsyncIterator

# 让下面的方法可以通过async with使用，
# 自动管理资源的创建和清理。
from contextlib import asynccontextmanager

# Redis库提供的异步客户端类。
# 通过它向Redis服务发送读写命令。
from redis.asyncio import Redis

# 读取我们之前添加的Redis配置。
from enterprise_support_agent.config import settings


@asynccontextmanager
async def open_redis_connection() -> AsyncIterator[Redis]:
    """
    为async with代码块提供Redis客户端。

    进入时创建客户端，并发送PING检查连接；
    使用结束后关闭客户端及其连接池。
    """

    # 创建客户端对象。
    # 这里只准备客户端和连接池，·
    # 后面执行ping()时才真正连接Redis并发送命令。
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,

        # 使用Redis内部编号为0的逻辑数据库。
        db=settings.redis_db,

        # 建立网络连接的超时时间，单位为秒。
        socket_connect_timeout=settings.redis_timeout_seconds,

        # 等待Redis命令响应的超时时间，单位为秒。
        socket_timeout=settings.redis_timeout_seconds,

        # 将返回的文本内容自动解码为Python字符串，
        # 方便后续读取缓存，不必自己把bytes转换成str。
        decode_responses=True,
    )

    try:
        # 向Redis发送PING命令。
        # 正常响应说明连接可用；连接失败则抛出异常。
        await client.ping()

        # 将客户端交给外面的async with代码块使用。
        yield client

    finally:
        # 无论正常结束还是发生异常，
        # 都关闭客户端，以及这个客户端创建的连接池。
        # 关闭连接不会删除Redis中的数据。
        await client.aclose(
            close_connection_pool=True,
        )