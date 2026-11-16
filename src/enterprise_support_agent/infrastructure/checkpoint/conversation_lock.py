"""
避免同一会话同时执行两个请求。

使用PostgreSQL咨询锁：
它是数据库提供的协作锁，不需要创建额外的表。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from psycopg import AsyncConnection

from enterprise_support_agent.application.common.exceptions import (
    AgentConversationConflictError,
)
from enterprise_support_agent.infrastructure.checkpoint.connection import (
    create_checkpoint_conninfo,
)


@asynccontextmanager
async def lock_agent_conversation(
    conversation_id: UUID,
) -> AsyncIterator[None]:
    """取得会话锁，退出时关闭连接并释放锁。"""

    # 使用独立连接持有锁。
    #
    # 这样工具中的业务事务commit，
    # 不会提前释放会话执行锁。
    async with await AsyncConnection.connect(
        create_checkpoint_conninfo(),
        autocommit=True,
    ) as connection:
        # hashtextextended把会话ID转换成数据库锁编号。
        #
        # pg_try_advisory_lock：让 PostgreSQL 申请锁,PostgreSQL 数据库自带的函数
        # 锁空闲时取得锁并返回True；
        # 已被其他请求占用时立即返回False，不一直等待。
        #
        # %s是参数占位符，实际值通过第二个参数传入。
        # hashtextextended(...)` 根据会话ID算出锁编号。
        # 先用 hashtextextended() 根据会话ID算出锁编号，再由 pg_try_advisory_lock() 申请这个编号对应的锁。
        # %s：参数占位符，实际传入的是 str(conversation_id)，也就是要计算哈希的会话ID。
        # - 0：固定的哈希种子，用来参与计算。
        # 相同会话ID配上相同的 0，每次都会算出相同锁编号，确保同一会话的请求争抢的是同一把锁
        cursor = await connection.execute(
            "SELECT pg_try_advisory_lock("
            "hashtextextended(%s, 0))",
            (str(conversation_id),),
        )

        # fetchone()由psycopg的游标提供，
        # 从SQL执行结果中取出一行；没有行时返回None。
        #
        # 默认一行数据用元组表示。
        # 当前SQL只返回一个值，所以结果是：
        # (True,)  → 取得锁
        # (False,) → 没取得锁
        row = await cursor.fetchone()

        # row is None：没有读到结果。
        # not row[0]：读到了结果，但第一个值是 False，表示没拿到锁。
        if row is None or not row[0]:
            raise AgentConversationConflictError(
                "当前会话正在处理其他请求，请稍后再试"
            )

        yield

    # 连接关闭后，PostgreSQL自动释放它持有的会话级咨询锁。