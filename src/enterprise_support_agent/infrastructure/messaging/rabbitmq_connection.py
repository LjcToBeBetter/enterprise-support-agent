"""建立RabbitMQ连接，并在使用结束后关闭连接。"""

# 用于标注异步函数通过yield提供的对象类型。
from collections.abc import AsyncIterator

# 把带yield的异步函数包装成支持async with的资源管理方法。
from contextlib import asynccontextmanager

# aio_pika负责与RabbitMQ通信。
import aio_pika

# 这是库提供的类型，用来标注支持重连的连接对象。
# 实际对象由connect_robust()创建，不需要手动实例化它。
from aio_pika.abc import AbstractRobustConnection

from enterprise_support_agent.config import settings


@asynccontextmanager
async def open_rabbitmq_connection(
    connection_name: str = "enterprise-support-agent",
) -> AsyncIterator[AbstractRobustConnection]:
    """
    为一段async with代码提供RabbitMQ连接。

    connection_name：
        显示在RabbitMQ管理页面中的连接名称，
        方便区分后端、Worker或测试程序。

    进入async with时建立连接；
    离开时自动关闭，即使使用过程中发生异常也会清理。
    """

    # connect_robust由aio-pika提供。
    # await表示等待连接建立完成，拿到连接对象后再往下执行。
    # 这种连接在运行中断开后，会尝试自动重连。
    connection = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,

        # login是库规定的参数名，表示登录用户名。
        login=settings.rabbitmq_username,

        # SecretStr只负责隐藏显示。
        # 连接时需要用get_secret_value()取出实际密码。
        password=settings.rabbitmq_password.get_secret_value(),

        # 指定连接RabbitMQ内部的哪个逻辑分区。
        virtualhost=settings.rabbitmq_virtual_host,

        # 首次建立连接的等待上限，单位是秒。
        timeout=settings.rabbitmq_connection_timeout_seconds,

        # 向服务端提供连接的附加信息。
        # 这个名称只是方便查看，不是账号或权限。
        client_properties={
            "connection_name": connection_name,
        },
    )

    try:
        # 将连接对象交给外面的async with代码使用。
        # 程序会暂停在这里，等外面的代码执行结束后再回来。
        yield connection

    finally:
        # 无论外面的代码正常完成还是抛出异常，
        # 都关闭连接，并停止它的后台重连任务。
        await connection.close()