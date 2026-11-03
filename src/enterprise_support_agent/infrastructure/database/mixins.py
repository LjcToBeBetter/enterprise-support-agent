"""
mixins.py

主要功能：
    定义多个数据库表都会使用的公共字段。

主要部件：
    UUIDPrimaryKeyMixin：
        为表提供UUID类型的id主键。

    TimestampMixin：
        为表提供创建时间和更新时间。

Mixin本身不对应数据库表，
它只是让其他表模型能够复用这些字段。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """为数据库表提供UUID主键。"""

    # Mapped[UUID]表示：
    # 这个Python属性由SQLAlchemy映射到数据库字段，
    # Python程序中读取到的类型是UUID。
    id: Mapped[UUID] = mapped_column(
        # 数据库使用UUID类型保存，读取时返回Python的UUID对象。
        Uuid(as_uuid=True),

        # 将id设置为这张表的主键。
        primary_key=True,

        # 把uuid4函数交给SQLAlchemy。
        # 每次创建新记录时，SQLAlchemy都会调用一次uuid4()生成新编号。
        default=uuid4,
    )


class TimestampMixin:
    """为数据库表提供创建时间和更新时间。"""

    created_at: Mapped[datetime] = mapped_column(
        # 保存包含时区信息的日期时间。
        DateTime(timezone=True),

        # 插入新记录时，让数据库自动填写当前时间。
        server_default=func.now(),

        # 这个字段不允许为空。
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),

        # 新记录创建时，先填写当前时间。
        server_default=func.now(),

        # 这条记录被SQLAlchemy更新时，重新填写当前时间。
        onupdate=func.now(),

        nullable=False,
    )