"""
初始化LangGraph的PostgreSQL存档表。

这是部署初始化脚本，
不需要每次用户提问时执行。
"""

import asyncio
import sys

# AsyncPostgresSaver由LangGraph的PostgreSQL组件提供。把 Checkpoint 保存到 PostgreSQL 的异步存档组件。
#
# 它负责异步保存、读取Checkpoint，
# 并提供setup()初始化内部表。
from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)

from enterprise_support_agent.infrastructure.checkpoint.connection import (
    create_checkpoint_conninfo,
)


async def main() -> None:
    """连接PostgreSQL，初始化Checkpoint内部表。"""

    # 这一步只生成连接字符串。
    conninfo = create_checkpoint_conninfo()

    # from_conn_string()根据连接字符串建立数据库连接，
    # 并创建AsyncPostgresSaver对象。
    # async with负责管理连接：
    # 进入代码块时打开，退出时自动关闭。
    async with AsyncPostgresSaver.from_conn_string(
        conninfo
    ) as checkpointer:
        # setup()执行组件内置的数据库迁移。
        #
        # 第一次：创建内部表和索引。
        # 再次执行：检查版本，执行尚未应用的升级。
        #
        # 不会因为重复运行就清空历史存档。
        await checkpointer.setup()

        print("Checkpoint内部表初始化完成")


if __name__ == "__main__":
    if sys.platform == "win32":
        # Windows默认事件循环不适合psycopg异步连接。
        #
        # loop_factory指定本次运行使用SelectorEventLoop，
        # 让数据库驱动能够正常异步工作。
        asyncio.run(
            main(),
            loop_factory=asyncio.SelectorEventLoop,
        )
    else:
        asyncio.run(main())