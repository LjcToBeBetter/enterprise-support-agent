"""领取并读取一条检查消息，然后向RabbitMQ确认消费完成。"""

import asyncio

from enterprise_support_agent.infrastructure.messaging.document_task_message import (
    DocumentProcessingMessage,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_connection import (
    open_rabbitmq_connection,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_topology import (
    ensure_document_task_topology,
)


async def main() -> None:
    """连接RabbitMQ，领取一条消息，读取字段并发送确认。"""

    async with open_rabbitmq_connection(
        connection_name="check-rabbitmq-consume",
    ) as connection:

        async with connection.channel() as channel:

            # 确保交换机、队列和绑定存在。
            # 这里只需要队列对象，用_接收暂时不用的交换机对象。
            # _ 是一个普通变量名，习惯上表示“这个值暂时不用”。
            _, queue = await ensure_document_task_topology(
                channel=channel,
            )

            # get()由aio-pika提供，向队列领取一条消息。
            #
            # 有消息：返回IncomingMessage对象。
            # 无消息：因为设置了fail=False，所以返回None。
            incoming_message = await queue.get(
                # 领取时不自动确认。
                # 等我们读取成功后，再主动调用ack()。
                no_ack=False,

                # 队列为空时返回None，不抛出队列为空的异常。
                fail=False,

                # 等待本次领取请求响应的上限，单位为秒。
                # 队列为空时会直接返回，不会等新消息。
                timeout=10.0,
            )

            if incoming_message is None:
                print("队列中没有等待领取的消息")
                return

            # incoming_message.body是消息正文，类型为bytes。
            #
            # model_validate_json()由Pydantic提供：
            # 读取JSON正文，校验字段，
            # 再创建DocumentProcessingMessage对象。
            task_message = (
                DocumentProcessingMessage.model_validate_json(
                    incoming_message.body,
                )
            )

            print("成功领取消息")
            print("任务ID：", task_message.job_id)
            print("组织ID：", task_message.organization_id)
            print("文档ID：", task_message.document_id)
            print("文档版本：", task_message.document_version)

            # ack()由aio-pika提供。
            # 通知RabbitMQ：本条消息已经处理完成，可以移除。
            await incoming_message.ack()

            print("已发送消费确认ACK")


if __name__ == "__main__":
    print("开始检查消息接收", flush=True)
    asyncio.run(main())