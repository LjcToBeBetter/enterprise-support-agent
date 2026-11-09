"""
Agent会话归属模型。

记录每段会话属于哪个组织、哪个用户。

读取历史或恢复执行前，
必须先验证当前用户能否访问这段会话。
"""

from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    String,
    Uuid,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from enterprise_support_agent.infrastructure.database.base import (
    Base,
)
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class AgentConversation(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """一条记录代表一段Agent会话的归属信息。"""

    __tablename__ = "agent_conversations"

    # id由UUIDPrimaryKeyMixin提供。
    #
    # 后面使用str(conversation.id)作为LangGraph的thread_id，
    # 不再额外生成另一套会话编号。

    # 会话所属组织。
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 会话所属用户。
    #
    # 即使两个用户在同一个组织，
    # 也不能直接读取对方的私人对话。
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 用于前端会话列表展示，
    # 不用于判断访问权限。
    title: Mapped[str] = mapped_column(
        String(200),
        default="新会话",
        server_default="新会话",
        nullable=False,
    )

    # created_at、updated_at由TimestampMixin提供。