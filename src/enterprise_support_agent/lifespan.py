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
from enterprise_support_agent.infrastructure.checkpoint.client import (
    open_checkpointer,
)

# getLogger 返回日志记录器对象。
# __name__ 是当前模块名称：
# enterprise_support_agent.lifespan
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """管理对象存储检查和Checkpointer的生命周期。"""

    logger.info(
        "服务启动：%s",
        app.title,
    )

    # 保留原来的对象存储检查。
    await asyncio.to_thread(
        object_storage.ensure_bucket_exists
    )

    logger.info(
        "对象存储连接成功，Bucket已就绪：%s",
        object_storage.bucket_name,
    )

    # 进入时：
    # 打开连接池，等待连接就绪，
    # 取得open_checkpointer()中yield出来的对象。
    #
    # 退出时：
    # open_checkpointer()继续执行清理，
    # 关闭连接池。
    async with open_checkpointer() as checkpointer:
        # app.state是FastAPI应用的共享存储位置。
        #
        # 将AsyncPostgresSaver对象放在这里，
        # 后续接口就能从request.app.state中取得。
        #
        # 这里保存的是运行时对象，
        # 不是把Checkpoint保存到了app.state。
        app.state.checkpointer = checkpointer

        logger.info(
            "Checkpoint数据库连接池已就绪"
        )

        try:
            # 暂停在这里，让FastAPI开始处理请求。
            #
            # 因为仍处在上面的async with里面，
            # 所以连接池会在服务运行期间保持打开。
            yield

        finally:
            # 后端关闭时，先移除共享对象的引用，
            # 避免继续从app.state取得它。
            del app.state.checkpointer

            logger.info(
                "服务关闭：%s",
                app.title,
            )

    # 离开async with后，
    # open_checkpointer()负责关闭连接池。