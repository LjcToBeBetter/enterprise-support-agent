"""把“处理某份文档”的任务消息发送给 RabbitMQ，让他进入队列排队"""

# Message：aio-pika提供的待发送消息类。
# DeliveryMode：设置消息的保存方式。
from aio_pika import DeliveryMode, Message

from aio_pika.abc import AbstractRobustConnection

from enterprise_support_agent.infrastructure.messaging.document_task_message import (
    DocumentProcessingMessage,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_topology import (
    DOCUMENT_TASK_ROUTING_KEY,
    ensure_document_task_topology,
)


async def publish_document_processing_message(
    connection: AbstractRobustConnection,
    task_message: DocumentProcessingMessage,
) -> None:
    """
    通过已有连接，发送一条文档处理消息。

    connection：
        外部已经建立的RabbitMQ连接。
        本方法负责打开、关闭自己使用的Channel。

    task_message：
        包含任务ID、组织ID、文档ID和版本的消息对象。

    正常执行完毕，表示RabbitMQ已经确认接收消息。
    Worker后续收到消息，才会执行文档处理。
    """

    # model_dump_json()由Pydantic提供。
    # 将消息对象转换成JSON字符串；
    # UUID字段也会自动转换成字符串。
    message_json = task_message.model_dump_json()

    # encode("utf-8")将字符串转换成bytes。
    # RabbitMQ消息的body需要接收bytes类型。
    message_body = message_json.encode("utf-8")

    # 将消息正文和附加信息，装进aio-pika的Message对象。
    outgoing_message = Message(
        body=message_body,

        # 告诉接收方：正文是JSON，采用UTF-8编码。
        content_type="application/json",
        content_encoding="utf-8",

        # PERSISTENT表示要求持久化保存这条消息。
        delivery_mode=DeliveryMode.PERSISTENT,

        # 使用任务ID标记这条消息，方便追踪。
        # 注意：设置message_id不会自动实现消息去重。
        message_id=str(task_message.job_id),
    )

    # 打开一个用于发送消息的通道。
    async with connection.channel(
        # 发送后，等待RabbitMQ确认接收。
        publisher_confirms=True,

        # 配合下面的mandatory=True：
        # 消息没有匹配到任何队列时，抛出异常。
        on_return_raises=True,
    ) as channel:

        # 确保交换机、队列和绑定已经存在。
        #
        # 方法返回：(交换机对象, 队列对象)。
        # 这里只需要交换机，用_接收暂时不用的队列对象。
        exchange, _ = await ensure_document_task_topology(
            channel=channel,
        )

        # publish()由aio-pika提供，将消息发给交换机。
        await exchange.publish(
            message=outgoing_message,

            # 交换机根据这个路由键，
            # 把消息送到绑定的文档处理队列。
            routing_key=DOCUMENT_TASK_ROUTING_KEY,

            # 找不到匹配队列时，要求RabbitMQ退回消息。
            mandatory=True,

            # 本次发送并等待确认的时间上限，单位为秒。
            timeout=10.0,
        )