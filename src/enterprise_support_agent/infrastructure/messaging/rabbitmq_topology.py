"""统一文档任务的交换机、队列和路由键名称。

后端发送消息、Worker接收消息时，共同使用这些名称，
避免各自写一遍，出现拼写不一致。
"""

# ExchangeType提供交换机类型，例如DIRECT。
from aio_pika import ExchangeType

# 这些类型用于标注通道、交换机和队列对象。
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractQueue,
)

# 文档任务发送到这个交换机。
DOCUMENT_TASK_EXCHANGE = "enterprise.document.tasks"


# 文档处理消息保存在这个队列中。
DOCUMENT_TASK_QUEUE = "enterprise.document.process"

# 路由键就是消息上的“分类标签”，交换机根据它决定把消息送到哪个队列。
# 发送文档处理消息时，携带这个路由键。
#
# 后面会建立绑定规则：
# 发给上述交换机、且路由键为document.process的消息，
# 应进入上述文档处理队列。
DOCUMENT_TASK_ROUTING_KEY = "document.process"

async def ensure_document_task_topology(
    channel: AbstractChannel,
) -> tuple[AbstractExchange, AbstractQueue]:
    """
    在RabbitMQ中创建文档任务交换机、队列，并绑定它们。

    channel：
        已经打开的操作通道，用于向RabbitMQ发送命令。
        本方法不负责关闭它，由外部调用者管理。

    返回：
        一个二元组：(交换机对象, 队列对象)。

    同名对象不存在时创建；
    已存在且配置一致时复用；
    已存在但配置冲突时抛出异常，不会自动覆盖。
    """

    # declare_exchange是aio-pika提供的方法。
    # 它会向RabbitMQ发送声明请求，不只是创建本地Python对象。
    exchange = await channel.declare_exchange(
        name=DOCUMENT_TASK_EXCHANGE,

        # DIRECT表示：
        # 消息的路由键与队列绑定的键完全相同，才匹配。
        type=ExchangeType.DIRECT,

        # durable=True：交换机定义在RabbitMQ重启后保留。
        durable=True,

        # 使用它的程序断开后，不自动删除这个交换机。
        auto_delete=False,
    )

    # 向RabbitMQ声明文档处理队列。
    queue = await channel.declare_queue(
        name=DOCUMENT_TASK_QUEUE,

        # 保留队列定义。
        durable=True,

        # 消费者断开后，不自动删除队列。
        auto_delete=False,

        # arguments是RabbitMQ支持的额外队列配置。
        # x-queue-type指定队列类型。
        # quorum是支持数据复制的一种持久化队列。
        # 支持多节点复制的任务队列，集群中可以保存多份消息，提高故障时的数据可靠性。
        arguments={
            "x-queue-type": "quorum",
        },
    )

    # bind建立“交换机 → 队列”的绑定规则。
    #
    # 以后发给这个交换机，并带有document.process路由键的消息，
    # 就能匹配到文档处理队列。
    await queue.bind(
        exchange,
        routing_key=DOCUMENT_TASK_ROUTING_KEY,
    )

    # 返回操作这些RabbitMQ对象的Python对象。
    # 它们不是某个任务的执行结果，也不是True或False。
    return exchange, queue