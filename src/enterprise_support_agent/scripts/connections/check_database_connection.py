"""
check_database_connection.py

主要功能：
    检查Python项目能否通过异步会话连接PostgreSQL。

主要部件：
    async_session_factory：
        创建本次检查使用的数据库会话。

    SELECT 1：
        执行一条最简单的SQL，用来确认数据库连接正常。

    engine.dispose：
        检查结束后关闭连接池中的数据库连接。
"""

import asyncio

from sqlalchemy import text

from enterprise_support_agent.infrastructure.database.session import (
    async_session_factory,
    engine,
)

async def check_database_connection() -> None:
    """连接数据库并执行一条简单SQL。"""

    # try...finally保证：
    # 即使连接或SQL执行失败，finally里的关闭操作仍然会执行。
    try:
        # async_session_factory()创建AsyncSession会话。
        #
        # async with负责管理会话：
        # 进入代码块时获得会话，
        # 离开代码块时自动关闭会话。
        async with async_session_factory() as session:

            # text()由SQLAlchemy提供。
            # 它把普通字符串转换成SQLAlchemy可以执行的SQL对象。
            sql = text("SELECT 1")

            # session.execute()把SQL交给数据库执行。
            #
            # 因为这是异步数据库操作，所以前面必须写await，
            # 等待PostgreSQL返回执行结果。
            result = await session.execute(sql)

            # SELECT 1只返回一个值。
            #
            # scalar_one()从查询结果中取出唯一的单个值，
            # 因此这里得到的是整数1。
            value = result.scalar_one()

            print("数据库连接成功")
            print("SELECT 1返回结果：", value)

    finally:
        # dispose()关闭engine连接池里的数据库连接。
        # 这个检查脚本执行结束后，不需要继续保留连接。
        await engine.dispose()


# 只有直接运行当前文件时，才执行下面的代码。
if __name__ == "__main__":

    # asyncio.run()负责：
    # 1. 创建事件循环；
    # 2. 运行异步函数；
    # 3. 等待异步函数执行结束；
    # 4. 关闭事件循环。
    asyncio.run(
        check_database_connection()
    )