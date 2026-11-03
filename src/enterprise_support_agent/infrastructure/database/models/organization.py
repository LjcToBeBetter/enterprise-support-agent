"""
organization.py

主要功能：
    定义企业组织对应的数据库表模型。

主要部件：
    Organization：
        对应数据库中的organizations表，
        保存组织名称、组织编码和启用状态。

一条Organization记录代表一个使用本系统的企业或团队。
"""

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_support_agent.infrastructure.database.base import Base
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Organization(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """企业组织的数据库模型。"""
    # __tablename__：SQLAlchemy规定的特殊名称
    # SQLAlchemy读取模型时，会主动查找：
    # Organization.__tablename__,然后知道这个类应该映射到哪张数据库表：
    # 指定这个模型对应数据库中的organizations表。
    __tablename__ = "organizations"

    # 组织名称，例如“星河科技有限公司”。
    name: Mapped[str] = mapped_column(
        String(100),

        # 表示不允许为空
        nullable=False,
    )

    # 组织编码，例如“xinghe-tech”。
    # 它用于在程序中稳定地标识组织。
    code: Mapped[str] = mapped_column(
        String(50),

        # 数据库不允许两个组织使用相同编码。
        unique=True,

        # 为这个字段创建索引，加快根据编码查找组织的速度。
        index=True,

        nullable=False,
    )

    # 表示这个组织当前是否可以继续使用系统。
    is_active: Mapped[bool] = mapped_column(
        Boolean,

        # 使用Python代码创建对象时，默认设置为True。
        default=True,

        # 如果直接在数据库中插入数据，也默认设置为true。
        server_default=true(),

        nullable=False,
    )