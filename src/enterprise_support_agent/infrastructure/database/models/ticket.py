"""
ticket.py

主要功能：
    定义企业工单对应的数据库表模型。

主要部件：
    Ticket：
        对应数据库中的tickets表，
        保存工单所属组织、创建人、处理人、
        标题、问题描述、状态和优先级。

一条Ticket记录代表一个需要处理的企业问题。
"""

from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_support_agent.application.ticket_enums import (
    TicketPriority,
    TicketStatus,
)
from enterprise_support_agent.infrastructure.database.base import (
    Base,
)
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Ticket(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """企业工单的数据库模型。"""

    # 当前ORM模型对应数据库中的tickets表。
    __tablename__ = "tickets"

    # 当前工单属于哪个组织。
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),

        # organization_id必须对应一个真实存在的组织。
        ForeignKey(
            "organizations.id",

            # 删除组织时，同时删除该组织下的工单。
            ondelete="CASCADE",
        ),

        # 创建索引，加快根据组织ID查询工单的速度。
        index=True,
        nullable=False,
    )

    # 创建这张工单的用户ID。
    creator_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),

        # 创建者必须对应一个真实存在的用户。
        ForeignKey(
            "users.id",

            # 如果用户还有工单，不允许直接删除用户，
            # 避免工单失去创建者信息。
            ondelete="RESTRICT",
        ),

        index=True,
        nullable=False,
    )

    # 当前负责处理工单的用户ID。
    #
    # 新工单可能还没有分配处理人员，
    # 所以这个字段允许为空。
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),

        # 处理人员必须对应一个真实存在的用户。
        ForeignKey(
            "users.id",

            # 删除处理人员时，
            # 将工单的assignee_user_id自动设置为空。
            ondelete="SET NULL",
        ),

        index=True,
        nullable=True,
    )

    # 工单标题，用一句话描述问题。
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # 工单的完整问题描述。
    #
    # Text适合保存长度不固定的较长文本。
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 工单当前状态。
    status: Mapped[str] = mapped_column(
        String(30),

        # 使用Python创建Ticket对象但没有传status时，
        # SQLAlchemy默认使用open。
        default=TicketStatus.OPEN.value,

        # 直接通过数据库插入时也默认使用open。
        server_default=TicketStatus.OPEN.value,

        index=True,
        nullable=False,
    )

    # 工单优先级。
    priority: Mapped[str] = mapped_column(
        String(20),

        # 没有指定优先级时默认使用medium。
        default=TicketPriority.MEDIUM.value,

        server_default=TicketPriority.MEDIUM.value,

        index=True,
        nullable=False,
    )