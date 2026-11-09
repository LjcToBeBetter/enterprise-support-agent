import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 导入所有模型。
# 导入models包时会执行models/__init__.py，
# 进而把三张表登记到Base.metadata。
import enterprise_support_agent.infrastructure.database.models

# Base.metadata中保存了所有已登记的表结构。
from enterprise_support_agent.infrastructure.database.base import Base

# database_url是session.py根据.env生成的数据库连接地址。
from enterprise_support_agent.infrastructure.database.session import (
    database_url,
)





# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# 把项目自己的数据库连接地址交给Alembic。
#
# render_as_string()把SQLAlchemy的URL对象转换成连接字符串。
# hide_password=False表示必须带上真实密码，否则Alembic无法连接数据库。
database_url_text = database_url.render_as_string(
    hide_password=False
)

# Alembic内部使用ConfigParser读取配置。
# 如果密码中出现%，需要写成%%，防止它被当成配置占位符。
database_url_text = database_url_text.replace(
    "%",
    "%%",
)

# set_main_option()用代码覆盖alembic.ini中的sqlalchemy.url。
# 这样数据库账号和密码不需要写死在alembic.ini中。
config.set_main_option(
    "sqlalchemy.url",
    database_url_text,
)


# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# 告诉Alembic：
# 用Base.metadata中的表结构和真实数据库进行比较。
target_metadata = Base.metadata


# LangGraph Checkpointer自己创建和维护的表。
# 不为它们编写业务ORM，也不交给Alembic自动比较。
CHECKPOINT_TABLE_NAMES = {
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
}


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    """
    决定数据库中的对象是否参与自动迁移比较。

    Alembic自动调用这个方法并传入：

    name：对象名称，例如表名。
    type_：对象类型，例如table。
    parent_names：所属schema、表等上级信息，本次暂不使用。

    返回True：参与比较。
    返回False：忽略。
    """

    if (
        type_ == "table"
        and name in CHECKPOINT_TABLE_NAMES
    ):
        return False

    # 其他对象继续按原来的方式比较。
    return True



# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,

        # 将过滤方法交给Alembic，
        # 自动生成迁移时由它调用。
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
