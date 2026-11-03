"""
user.py

主要功能：
    定义系统用户对应的数据库表模型。

主要部件：
    User：
        对应数据库中的users表，
        保存邮箱、显示名称、密码哈希和账号状态。

注意：
    数据库不会保存用户的明文密码，
    只保存经过安全算法处理后的密码哈希。
"""

from sqlalchemy import Boolean, String, true
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_support_agent.infrastructure.database.base import Base
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class User(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """系统用户的数据库模型。"""

    __tablename__ = "users"

    # 用户登录时使用的邮箱。
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # 页面上展示的用户姓名。
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 保存加密处理后的密码结果，绝不能保存明文密码。
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 控制账号是否允许登录和使用系统。
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )