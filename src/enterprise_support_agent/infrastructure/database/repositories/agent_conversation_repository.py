"""
Agent会话归属数据访问层。

这里只操作agent_conversations表，
不读取或保存Checkpoint。

事务提交由上层Service负责。
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.models.agent_conversation import (
    AgentConversation,
)


class AgentConversationRepository:
    """负责会话归属记录的数据库读写。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """保存当前请求使用的数据库会话。"""

        self.session = session

    async def create(
        self,
        organization_id: UUID,
        user_id: UUID,
        title: str,
    ) -> AgentConversation:
        """创建会话归属记录，但不提交事务。"""

        conversation = AgentConversation(
            organization_id=organization_id,
            user_id=user_id,
            title=title,
        )

        # 将对象加入当前Session，准备保存。
        self.session.add(conversation)

        # 执行INSERT，取得默认生成的UUID等字段。
        # 事务尚未提交，仍然可以回滚。
        await self.session.flush()

        # 重新读取数据库生成的时间等字段。
        await self.session.refresh(conversation)

        return conversation

    async def get_by_id_and_owner(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        user_id: UUID,
    ) -> AgentConversation | None:
        """
        查询当前用户在当前组织中的指定会话。

        找到：返回AgentConversation ORM对象。
        找不到或归属不匹配：返回None。
        """

        statement = select(
            AgentConversation
        ).where(
            # 三个条件必须同时满足，
            # 相当于SQL中的AND。
            AgentConversation.id == conversation_id,
            AgentConversation.organization_id
            == organization_id,
            AgentConversation.user_id == user_id,
        )

        result = await self.session.execute(
            statement
        )

        # id是主键，最多返回一条记录。
        return result.scalar_one_or_none()