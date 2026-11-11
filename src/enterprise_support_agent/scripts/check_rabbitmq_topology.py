"""检查文档任务的交换机、队列和绑定是否能够创建成功。"""

import asyncio

from enterprise_support_agent.infrastructure.messaging.rabbitmq_connection import (
    open_rabbitmq_connection,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_topology import (
    DOCUMENT_TASK_ROUTING_KEY,
    ensure_document_task_topology,
)


async def main() -> None:
    """连接RabbitMQ，并建立文档任务消息的投递规则。"""

    print("正在连接RabbitMQ……", flush=True)

    # 建立连接。
    # 离开这个async with后，会自动关闭连接。
    async with open_rabbitmq_connection(
        connection_name="check-rabbitmq-topology",
    ) as connection:

        # channel()由aio-pika提供。
        #
        # 在连接里面打开一个操作通道，
        # 后面通过这个通道向RabbitMQ发送创建命令。
        #
        # 离开内层async with时，自动关闭通道。
        async with connection.channel() as channel:

            # 调用刚才编写的方法：
            # 1. 创建或复用交换机；
            # 2. 创建或复用队列；
            # 3. 根据路由键绑定交换机和队列。
            #
            # 返回值是二元组：
            # (交换机对象, 队列对象)。
            #
            # 下面写两个变量，分别接收这两个对象。
            exchange, queue = (
                await ensure_document_task_topology(
                    channel=channel,
                )
            )

            # name是这些对象提供的属性，表示对应的名称。
            print("交换机：", exchange.name)
            print("队列：", queue.name)
            print("绑定路由键：", DOCUMENT_TASK_ROUTING_KEY)

            print("交换机、队列和绑定检查成功")


if __name__ == "__main__":
    # 启动事件循环，执行上面的异步main方法。
    print("开始检查RabbitMQ消息投递配置", flush=True)
    asyncio.run(main())