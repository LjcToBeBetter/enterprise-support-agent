"""执行RabbitMQ消息所指定的文档处理任务。"""

import logging

from enterprise_support_agent.application.document_enums import (
    DocumentJobStatus,
)
from enterprise_support_agent.application.document_processing_service import (
    DocumentProcessingService,
)
from enterprise_support_agent.infrastructure.database.repositories.document_processing_job_repository import (
    DocumentProcessingJobRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.document_repository import (
    DocumentRepository,
)
from enterprise_support_agent.infrastructure.database.session import (
    async_session_factory,
    engine
)
from enterprise_support_agent.infrastructure.messaging.document_task_message import (
    DocumentProcessingMessage,
)
import asyncio

# Message用于发送消息；
# DeliveryMode.PERSISTENT表示持久化保存消息。
from aio_pika import DeliveryMode, Message

from enterprise_support_agent.logging_config import (
    configure_logging,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_connection import (
    open_rabbitmq_connection,
)
from enterprise_support_agent.infrastructure.messaging.rabbitmq_topology import (
    DOCUMENT_TASK_QUEUE,
    ensure_document_task_topology,
)
# uuid4()用于生成一个新的UUID编号。
from uuid import UUID, uuid4


# 记录Worker执行失败时的详细异常。
logger = logging.getLogger(__name__)

async def keep_job_lease_alive(
    organization_id: UUID,
    job_id: UUID,
    execution_token: UUID,
    stop_event: asyncio.Event,
) -> None:
    """
    每隔30秒，为正在执行的任务续期。

    stop_event是asyncio提供的通知对象：
    调用stop_event.set()，就表示通知这个方法停止续期。
    """

    while True:
        try:
            # stop_event.wait()：等待停止通知。
            #
            # asyncio.wait_for(..., timeout=30)：
            # 最多等待30秒。
            #
            # 收到通知 → 等待正常结束；
            # 30秒没收到通知 → 抛出TimeoutError。
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=30,
            )

        except TimeoutError:
            # 没收到停止通知，继续执行下面的续期操作。
            pass

        else:
            # 收到了停止通知，结束整个续期方法。
            return

        # 续期和文档处理会同时运行，
        # 所以续期必须使用独立的数据库Session，
        # 不能与文档处理共用同一个Session。
        async with async_session_factory() as session:
            repository = DocumentProcessingJobRepository(
                session=session,
            )

            renewed = await repository.renew_lease(
                organization_id=organization_id,
                job_id=job_id,
                execution_token=execution_token,
            )

            # 提交后，新的到期时间才正式保存在数据库中。
            await session.commit()

        if not renewed:
            # 已失去执行资格。
            # 后面接入并发执行时，会利用这个异常停止文档处理。
            raise RuntimeError(
                "任务租约续期失败，已失去执行资格"
            )


async def process_document_job(
    task_message: DocumentProcessingMessage,
) -> DocumentJobStatus | None:
    """
    根据消息执行一次文档处理尝试。

    返回SUCCEEDED：任务成功。
    返回QUEUED：本次失败，还有次数，可以重新排队。
    返回FAILED：任务最终失败。
    返回None：本次没有取得执行资格。

    消息的ACK、重新排队等操作，由后面的接收入口负责。
    """

    # 每条任务创建自己的数据库Session。
    # 离开async with时，自动关闭Session并归还数据库连接。
    async with async_session_factory() as session:
        job_repository = DocumentProcessingJobRepository(
            session=session,
        )

        # 根据消息中的组织ID和任务ID，读取正式任务记录。
        # 注意这里是从数据库里面读取了任务记录而不是任务本身
        job = await job_repository.get_by_id_and_organization(
            organization_id=task_message.organization_id,
            job_id=task_message.job_id,
        )

        if job is None:
            raise ValueError("消息对应的任务记录不存在")

        # 消息中的文档和版本必须与任务记录一致，
        # 避免根据不匹配的消息处理其他文档。
        if (
            job.document_id != task_message.document_id
            or job.document_version
            != task_message.document_version
        ):
            raise ValueError("消息内容与任务记录不一致")

        # 重复收到已经结束的任务时，直接返回已保存的结果。
        if job.status in (
            DocumentJobStatus.SUCCEEDED.value,
            DocumentJobStatus.FAILED.value,
        ):
            return DocumentJobStatus(job.status)

        # 最后一次执行如果中途退出，租约到期后应结束为失败，
        # 而不是超出max_attempts继续执行，或者一直停在running。
        exhausted = await job_repository.mark_exhausted_job_failed(
            organization_id=task_message.organization_id,
            job_id=task_message.job_id,
        )
        await session.commit()

        if exhausted:
            return DocumentJobStatus.FAILED

        # 为本次执行生成唯一编号。
        # 同一个任务重新尝试执行时，也会生成新的编号。
        execution_token = uuid4()

        # 尝试领取任务。
        # 成功时，将执行编号和租约到期时间一起写入数据库。
        claimed = await job_repository.try_mark_running(
            organization_id=task_message.organization_id,
            job_id=task_message.job_id,
            execution_token=execution_token,
        )

        # 先提交执行状态，再开始耗时处理。
        await session.commit()

        if not claimed:
            return None

        try:
            document_repository = DocumentRepository(
                session=session,
            )

            document = (
                await document_repository
                .get_by_id_and_organization(
                    organization_id=task_message.organization_id,
                    document_id=task_message.document_id,
                )
            )

            # 排队期间，文档可能已被删除或更新。
            if document is None:
                raise RuntimeError("待处理文档已不存在")

            if document.version != task_message.document_version:
                raise RuntimeError("文档版本已变化，需要重新提交任务")

            # 调用之前已经写好的文档处理服务。
            # 真正的下载、解析、切块、向量化在这里执行。
            service = DocumentProcessingService(
                session=session,
            )

            # 创建停止通知对象。
            # 刚创建时没有发出通知，续期方法会持续工作。
            stop_event = asyncio.Event()

            # TaskGroup由asyncio提供，用于管理一起运行的异步任务。
            #
            # 离开这个代码块前，会等待它管理的任务结束。
            # 续期任务抛出异常时，会取消代码块中正在等待的
            # 文档处理协程，并把异常交给外层处理。
            async with asyncio.TaskGroup() as task_group:

                # create_task()启动续期协程，
                # 让它与下面的文档处理同时运行。
                task_group.create_task(
                    keep_job_lease_alive(
                        organization_id=task_message.organization_id,
                        job_id=task_message.job_id,
                        execution_token=execution_token,
                        stop_event=stop_event,
                    )
                )

                try:
                    # 当前协程负责处理文档。
                    # 等待下载、模型请求等异步操作时，
                    # 事件循环也可以执行上面的续期协程。
                    await service.process_document(
                        organization_id=task_message.organization_id,
                        document_id=task_message.document_id,
                    )

                finally:
                    # 无论处理成功、失败还是被取消，
                    # 都通知续期方法停止。
                    stop_event.set()

            # 文档处理完成，保存任务成功状态。
            updated = await job_repository.mark_succeeded(
                organization_id=task_message.organization_id,
                job_id=task_message.job_id,
                execution_token=execution_token,
            )

            if not updated:
                raise RuntimeError("未能更新任务成功状态")

            await session.commit()

            return DocumentJobStatus.SUCCEEDED

        except Exception:
            # 先撤销当前尚未提交的数据库修改，
            # 让Session能够继续执行后面的失败状态更新。
            await session.rollback()

            # 完整异常记录到Worker日志，方便根据任务ID排查。
            logger.exception(
                "文档处理任务执行失败，job_id=%s",
                task_message.job_id,
            )

            # 根据剩余次数，将任务改成queued或failed。
            next_status = (
                await job_repository.mark_failed_or_retry(
                    organization_id=task_message.organization_id,
                    job_id=task_message.job_id,
                    error_message="文档处理失败，请根据任务ID查看Worker日志",
                    execution_token=execution_token,
                )
            )

            if next_status is None:
                # 执行编号已经改变，或任务已经结束。
                # 本Worker不再有权更新状态，让接收入口重新检查，
                # 不能把其他Worker的执行结果覆盖掉。
                await session.rollback()
                return None

            await session.commit()

            return next_status


async def run_worker() -> None:
    """持续领取消息，根据任务执行结果确认、重试或保存失败消息。"""

    configure_logging()

    try:
        async with open_rabbitmq_connection(
            connection_name="document-processing-worker",
        ) as connection:

            async with connection.channel(
                # 后面保存失败消息时，需要等待发送确认。
                publisher_confirms=True,
                on_return_raises=True,
            ) as channel:

                # 最多预取一条尚未确认的消息，
                # 避免这个Worker一次领取太多任务。
                await channel.set_qos(
                    prefetch_count=1,
                )

                _, queue = await ensure_document_task_topology(
                    channel=channel,
                )

                # 单独保存最终失败或格式错误的消息，供后续排查。
                failed_queue = await channel.declare_queue(
                    name=f"{DOCUMENT_TASK_QUEUE}.failed",
                    durable=True,
                    arguments={"x-queue-type": "quorum"},
                )

                logger.info("Worker已启动，等待文档处理消息")

                # 【这里开始从RabbitMQ持续领取消息】
                # iterator()提供一个接收消息的异步迭代器。
                # no_ack=False表示需要我们主动确认处理结果。

                # queue.iterator()创建一个QueueIterator对象
                #     ↓
                # Python自动调用这个对象的__aenter__()
                #     ↓
                # __aenter__()里的代码调用self.consume()
                #     ↓
                # 向RabbitMQ注册消费者

                # Worker主动连接RabbitMQ
                #     ↓
                # consume()：订阅这个队列，请沿当前Channel给我发消息
                #     ↓
                # RabbitMQ沿当前Channel投递消息
                #     ↓
                # aio-pika收到消息，for循环取到它
                #     ↓
                # 调用我们写的process_document_job()
                async with queue.iterator(
                    no_ack=False,
                ) as messages:
                    # messages：接收消息的迭代器对象。
                    # 接受的是queue里面的消息

                    # 每收到一条消息，就执行一次循环体。
                    # 没有消息时，异步等待下一条消息。
                    async for incoming_message in messages:

                        try:
                            # 从消息正文中读取JSON，
                            # 校验并转换成我们定义的消息对象。
                            task_message = (
                                DocumentProcessingMessage
                                .model_validate_json(
                                    incoming_message.body,
                                )
                            )

                            logger.info(
                                "领取任务：%s",
                                task_message.job_id,
                            )

                            # 【这里调用之前写好的执行函数】
                            result = await process_document_job(
                                task_message,
                            )

                            while result is None:
                                # 消息已收到，但数据库尚未允许本Worker执行，
                                # 例如上一次执行的租约还没有到期。
                                # 保留这条未确认消息，5秒后重新查数据库。
                                # 不反复nack，避免空转并消耗队列的重复投递次数。
                                logger.info(
                                    "任务暂不可执行，5秒后重新检查：%s",
                                    task_message.job_id,
                                )
                                await asyncio.sleep(5)
                                result = await process_document_job(
                                    task_message,
                                )

                        except ValueError:
                            # 包括JSON格式错误、任务不存在、
                            # 消息内容与任务记录不匹配等情况。
                            logger.exception("任务消息校验失败")
                            result = DocumentJobStatus.FAILED

                        if result == DocumentJobStatus.SUCCEEDED:
                            # 成功结果已保存到数据库，
                            # 再通知RabbitMQ移除本条消息。
                            await incoming_message.ack()
                            logger.info("任务成功，已发送ACK")

                        elif result == DocumentJobStatus.QUEUED:
                            # nack表示本次没有成功处理消息。
                            # requeue=True要求把消息重新放回队列。
                            await incoming_message.nack(
                                requeue=True,
                            )
                            logger.warning("任务等待重新执行")

                        elif result == DocumentJobStatus.FAILED:
                            # 将原始消息复制到失败消息队列。
                            failed_message = Message(
                                body=incoming_message.body,
                                content_type=incoming_message.content_type,
                                message_id=incoming_message.message_id,
                                delivery_mode=DeliveryMode.PERSISTENT,
                            )

                            # default_exchange是RabbitMQ内置的默认交换机。
                            # 它使用队列名称作为路由键，将消息送到对应队列。
                            await channel.default_exchange.publish(
                                message=failed_message,
                                routing_key=failed_queue.name,
                                mandatory=True,
                                timeout=10.0,
                            )

                            # 等失败消息保存成功后，
                            # 再确认原消息，避免提前移除。
                            await incoming_message.ack()
                            logger.error(
                                "失败消息已保存到：%s",
                                failed_queue.name,
                            )

    finally:
        # Worker退出时，关闭自身使用的数据库连接池。
        await engine.dispose()


if __name__ == "__main__":
    print("正在启动文档处理Worker……", flush=True)

    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        # 在终端按Ctrl+C时，结束Worker程序。
        print("Worker已停止", flush=True)
