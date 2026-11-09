"""
管理应用运行期间使用的Checkpointer和连接池。

后端启动时打开，
后端关闭时释放，
不在每次请求时重新创建。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)

# dict_row让数据库查询结果以字典形式返回。
# Checkpointer内部会按字段名读取这些结果。
from psycopg.rows import dict_row

# psycopg提供的异步数据库连接池。
from psycopg_pool import AsyncConnectionPool

from enterprise_support_agent.infrastructure.checkpoint.connection import (
    create_checkpoint_conninfo,
)


# 将下面的异步生成器包装成上下文管理器，
# 这样调用者就可以使用：
#
# async with open_checkpointer() as checkpointer:
#     ...
@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[
    AsyncPostgresSaver
]:
    """打开连接池，提供Checkpointer，用完自动关闭。"""

    conninfo = create_checkpoint_conninfo()

    # 创建连接池配置，此时暂不打开连接。
    pool = AsyncConnectionPool(
        conninfo=conninfo,

        # 最少准备1条连接，最多使用5条连接。
        min_size=1,
        max_size=5,

        # 从池中等待可用连接的超时时间，单位为秒。
        timeout=10,

        open=False,

        # 这些参数会传给池中创建的数据库连接。
        kwargs={
            # 连接处于自动提交模式，没有显式事务时
            # SQL 执行成功后就会提交，不需要再手动调用 commit()。
            "autocommit": True,

            # 与官方from_conn_string使用的配置保持一致。
            "prepare_threshold": 0,

            # 数据库行以字典形式返回。
            "row_factory": dict_row,
        },
    )

    # 进入时打开连接池，
    # 离开时自动关闭池和它管理的连接。
    async with pool:
        # 等待最少连接准备好。
        # 数据库不可用时，让启动过程明确失败。
        await pool.wait(timeout=10)

        # 将连接池交给Checkpointer。
        # 保存或读取状态时，它会从池中借用连接。
        # 创建一个 AsyncPostgresSaver 对象，把连接池交给它使用。
        checkpointer = AsyncPostgresSaver(pool)

        # 把对象交给调用者。
        # 调用者退出async with后，会继续执行下面的清理。
        yield checkpointer

    # 执行到这里，连接池已关闭。