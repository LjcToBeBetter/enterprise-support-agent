"""
session.py

主要功能：
    创建PostgreSQL异步连接引擎和数据库会话工厂。

主要部件：
    database_url：
        根据.env中的配置生成数据库连接地址。

    engine：
        管理程序与PostgreSQL之间的数据库连接。

    async_session_factory：
        每次需要操作数据库时，用它创建一个独立的AsyncSession。
"""

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from enterprise_support_agent.config import settings

from collections.abc import AsyncIterator

# 根据配置生成连接地址。
# 最终效果类似：
# postgresql+asyncpg://用户名:密码@主机:端口/数据库名
database_url = URL.create(
    drivername="postgresql+asyncpg",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)


# 创建异步数据库引擎。
# 引擎负责维护连接池，需要访问数据库时再提供连接。
engine = create_async_engine(
    database_url,

    # 从连接池取出旧连接前，先检查连接是否仍然有效。
    pool_pre_ping=True,
)


# 创建异步会话工厂。
# 后面调用async_session_factory()，就能得到一个AsyncSession。

# async_session_factory本身不建立数据库连接，它是一个生产数据库会话的工厂。
# 会话工厂 → 创建会话 → 会话通过engine连接并操作数据库
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,

    # 提交数据后，保留Python对象中已经读取到的字段。
    expire_on_commit=False,
)


async def get_db_session()->AsyncIterator[AsyncSession]:
    """
    为一次FastAPI请求提供一个独立的数据库会话。

    请求开始：
       创建AsyncSession。

    请求处理中：
       Router、Service和Repository共同使用这个会话。

    请求结束：
       async with自动关闭会话并归还数据库连接。
    """

    # 创建本次请求专用的数据库会话。
    async with async_session_factory() as session:
        try:
            # yield把会话交给FastAPI接口使用。
            # 接口处理结束后，程序会回到yield下面继续执行。
            yield session

        except Exception:
            # 如果本次请求执行数据库操作时发生异常，
            # 回滚尚未提交的修改，避免保存一半的数据。
            # 回滚：撤销当前事务中还没有成功提交的数据库修改。
            await session.rollback()

            # 将原来的异常继续向上抛出，
            # 交给FastAPI统一异常处理器。
            raise