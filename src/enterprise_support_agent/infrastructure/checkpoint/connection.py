"""
为LangGraph Checkpointer准备PostgreSQL连接参数。

复用项目现有数据库配置。
这里只生成连接字符串，不建立连接、不创建表。
"""

# make_conninfo由psycopg提供。
#
# 根据主机、端口、账号等参数，
# 生成psycopg能够识别的数据库连接字符串。
# psycopg 是一个 Python 连接 PostgreSQL 的驱动库,可以理解成 Python 和 PostgreSQL 之间的通信工具。
# 它会处理密码中的空格、引号等特殊字符，
# 不需要我们手动拼接和转义。
from psycopg.conninfo import make_conninfo

from enterprise_support_agent.config import (
    settings,
)


def create_checkpoint_conninfo() -> str:
    """根据项目配置生成Checkpointer连接字符串。"""


    # ake_conninfo() 则是 psycopg 提供的一个辅助函数，用来整理连接信息。
    # 它只是把参数整理成连接字符串，不会连接数据库。 后面把这个字符串交给 Checkpointer，才会由 psycopg 真正建立连接。
    return make_conninfo(
        host=settings.db_host,
        port=settings.db_port,

        # psycopg将数据库名这个参数叫作dbname。
        dbname=settings.db_name,

        user=settings.db_user,
        password=settings.db_password,

        # 建立数据库连接最多等待10秒。
        # 这不是SQL执行的超时时间。
        connect_timeout=10,

        # 数据库连接的应用名称，
        # 便于在PostgreSQL中识别这类连接。
        application_name="enterprise_support_checkpoint",
    )