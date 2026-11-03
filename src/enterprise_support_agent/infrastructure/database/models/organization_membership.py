"""
organization_membership.py

主要功能：
    建立用户和企业组织之间的成员关系。

主要部件：
    OrganizationMembership：
        对应organization_memberships表，
        保存用户属于哪个组织，以及用户在组织中的角色。

角色暂时使用：
    employee：普通员工
    support：技术支持人员
    admin：组织管理员
"""

from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_support_agent.infrastructure.database.base import Base
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class OrganizationMembership(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """用户与组织之间的成员关系。"""

    __tablename__ = "organization_memberships"

    # __table_args__用来配置整张表的额外约束。
    #
    # 这里规定：
    # 同一个用户不能重复加入同一个组织。
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_membership_organization_user",
        ),
    )

    # 当前成员关系属于哪个组织。
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),

        # ForeignKey表示外键。
        # 它要求organization_id必须对应organizations表中真实存在的id。
        ForeignKey(
            "organizations.id",

            # 被关联的主记录删除时，数据库自动删除引用它的关系记录。
            ondelete="CASCADE",
        ),

        index=True,
        nullable=False,
    )

    # 当前成员关系属于哪个用户。
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),

        # 这个值必须对应users表中真实存在的id。
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),

        index=True,
        nullable=False,
    )

    # 用户在这个组织中的角色。
    role: Mapped[str] = mapped_column(
        String(30),
        default="employee",
        server_default="employee",
        nullable=False,
    )