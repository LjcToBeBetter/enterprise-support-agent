"""检查文档处理消息能否成功发送到RabbitMQ队列。"""

import asyncio

# UUID：把UUID字符串转换成UUID对象。
# uuid4：生成一个新的UUID。
from uuid import UUID, uuid4

from enterprise_support_agent.infrastructure.messaging.document_task_message import (
    DocumentProcessingMessage,
)
from enterprise_support_agent.infrastructure.messaging.document_task_publisher import (
    publish_document_processing_message,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_connection import (
    open_rabbitmq_connection,
)


async def main() -> None:
    """准备一条检查消息，建立连接，然后发送。"""

    # 创建消息数据对象。
    task_message = DocumentProcessingMessage(
        # 当前先生成一个ID，用于检查发送流程。
        # 正式接入任务表后，会使用数据库中的任务ID。
        job_id=uuid4(),

        # 使用之前测试文档时的真实组织ID。
        organization_id=UUID(
            "633b0933-507f-4e9d-8364-691a39b0d5cb"
        ),

        # 使用之前上传的PDF文档ID。
        document_id=UUID(
            "12287a4a-439c-417c-86b7-3911945611ed"
        ),

        # 这份文档的版本是1。
        document_version=1,
    )

    print("准备发送消息", flush=True)
    print("本次任务ID：", task_message.job_id, flush=True)

    # 建立RabbitMQ连接。
    # 离开async with后，自动关闭连接。
    async with open_rabbitmq_connection(
        connection_name="check-rabbitmq-publish",
    ) as connection:

        # 调用刚才编写的发送方法。
        # 它会打开Channel，把消息发给交换机，
        # 再由交换机根据路由键投递到队列。
        await publish_document_processing_message(
            connection=connection,
            task_message=task_message,
        )

        print("RabbitMQ已确认接收消息", flush=True)

    print("发送程序结束，连接已关闭", flush=True)


if __name__ == "__main__":
    # 启动事件循环，执行异步main方法。
    print("开始检查消息发送", flush=True)
    asyncio.run(main())