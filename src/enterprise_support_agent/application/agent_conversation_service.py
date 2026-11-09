"""
Agent会话业务服务。

负责验证身份、管理会话归属和提交事务。
不直接操作LangGraph的Checkpoint。
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.agent_context import (
    AgentContext,
)
from enterprise_support_agent.application.exceptions import (
    AgentConversationNotFoundError,
    OrganizationAccessDeniedError,
)
from enterprise_support_agent.infrastructure.database.models.agent_conversation import (
    AgentConversation,
)
from enterprise_support_agent.infrastructure.database.repositories.agent_conversation_repository import (
    AgentConversationRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)


class AgentConversationService:
    """管理当前用户在当前组织中的Agent会话。"""

    def __init__(
        self,
        session: AsyncSession,
        context: AgentContext,
    ) -> None:
        """保存本次请求的数据库会话和身份。"""

        self.session = session
        self.context = context

        self.repository = AgentConversationRepository(
            session=session
        )

        self.membership_repository = MembershipRepository(
            session=session
        )

    async def _require_membership(self) -> None:
        """检查当前用户是否仍然属于当前组织。"""

        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=(
                    self.context.organization_id
                ),
                user_id=self.context.current_user_id,
            )
        )

        if membership is None:
            raise OrganizationAccessDeniedError(
                self.context.organization_id
            )

    async def create_conversation(
        self,
        title: str = "新会话",
    ) -> AgentConversation:
        """为当前用户创建会话归属记录并提交。"""

        await self._require_membership()

        normalized_title = title.strip()

        if not 1 <= len(normalized_title) <= 200:
            raise ValueError(
                "会话标题去除首尾空白后，长度必须为1到200"
            )

        try:
            conversation = await self.repository.create(
                organization_id=(
                    self.context.organization_id
                ),
                user_id=self.context.current_user_id,
                title=normalized_title,
            )

            # Repository只执行flush，
            # 这里由Service正式提交事务。
            await self.session.commit()

            return conversation

        except Exception:
            # 创建或提交失败时回滚，
            # 不留下未完成的数据库事务。
            await self.session.rollback()
            raise

    async def get_conversation(
        self,
        conversation_id: UUID,
    ) -> AgentConversation:
        """找到指定用户的指定会话"""

        # 即使用户以前拥有这段会话，
        # 被移出组织后也不再允许访问。
        await self._require_membership()

        conversation = (
            await self.repository
            .get_by_id_and_owner(
                conversation_id=conversation_id,
                organization_id=(
                    self.context.organization_id
                ),
                user_id=self.context.current_user_id,
            )
        )

        if conversation is None:
            raise AgentConversationNotFoundError(
                conversation_id
            )

        return conversation