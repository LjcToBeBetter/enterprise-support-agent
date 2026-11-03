"""
应用生命周期模块。

主要功能：
    集中安排服务启动和关闭时的操作。

主要部件：
    asynccontextmanager：Python 标准库提供的装饰器，
        将下面的函数转换为异步上下文管理器。
    lifespan：供 FastAPI 管理应用生命周期。
    yield：分隔启动阶段和关闭阶段。

启动阶段：
    记录启动日志；
    检查RustFS对象存储；
    确保知识库Bucket存在。

关闭阶段：
    记录服务关闭日志。
"""


import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from enterprise_support_agent.infrastructure.storage.object_storage import object_storage


# getLogger 返回日志记录器对象。
# __name__ 是当前模块名称：
# enterprise_support_agent.lifespan
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """
    管理FastAPI应用的启动和关闭过程。

    yield之前：
        服务启动阶段。

    yield之后：
        服务关闭阶段。
    """

    logger.info(
        "服务启动：%s",
        app.title,
    )

    # boto3是同步客户端，
    # ensure_bucket_exists()执行时可能等待网络响应。
    #
    # asyncio.to_thread()把这个同步操作放进工作线程，
    # 避免阻塞FastAPI的事件循环。
    await asyncio.to_thread(
        object_storage.ensure_bucket_exists
    )

    logger.info(
        "对象存储连接成功，Bucket已就绪：%s",
        object_storage.bucket_name,
    )

    try:
        # yield执行后，
        # FastAPI开始正式接收HTTP请求。
        yield

    finally:
        # 应用关闭时执行这里。
        logger.info(
            "服务关闭：%s",
            app.title,
        )