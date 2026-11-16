"""检查RabbitMQ连接配置，以及连接是否自动关闭。"""

import asyncio

from enterprise_support_agent.infrastructure.messaging.rabbitmq_connection import (
    open_rabbitmq_connection,
)


async def main() -> None:
    """建立连接，检查状态，再退出并检查关闭状态。"""

    print("正在连接RabbitMQ……", flush=True)

    # 进入async with时：
    # 执行连接方法，等待连接建立，取得yield提供的连接对象。
    async with open_rabbitmq_connection(
        connection_name="check-rabbitmq-connection",
    ) as connection:

        print("RabbitMQ连接成功")

        # is_closed是aio-pika连接对象提供的属性。
        # False：连接尚未关闭。
        # True：连接已经关闭。
        print(
            "使用期间，连接是否关闭：",
            connection.is_closed,
        )

    # 离开async with后，
    # 连接方法的finally已经执行，连接应当关闭。
    print(
        "退出后，连接是否关闭：",
        connection.is_closed,
    )


if __name__ == "__main__":
    print("开始检查RabbitMQ连接", flush=True)

    # 启动事件循环，执行上面的异步方法。
    asyncio.run(main())