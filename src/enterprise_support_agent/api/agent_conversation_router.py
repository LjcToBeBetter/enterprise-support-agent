"""
Agent会话归属接口。

负责创建会话、查询指定会话的归属信息。
暂不提供聊天历史读取。
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.agent_conversation_schemas import (
    AgentConversationResponse,
    CreateAgentConversationRequest,
)
from enterprise_support_agent.api.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.api.organization_dependencies import (
    require_organization_member,
)
from enterprise_support_agent.application.agent_context import (
    AgentContext,
)
from enterprise_support_agent.application.agent_conversation_service import (
    AgentConversationService,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)

router = APIRouter(
    prefix=(
        "/organizations/"
        "{organization_id}/agent/conversations"
    ),
    tags=["agent-conversations"],
)


@router.post(
    "",
    response_model=AgentConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建Agent会话",
)
async def create_agent_conversation(
    # 从URL读取组织ID。
    organization_id: UUID,

    # 从请求体读取会话标题。
    request_data: CreateAgentConversationRequest,

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 从有效JWT取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),

    # 接口执行前检查当前用户属于这个组织。
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> AgentConversationResponse:
    """为当前登录用户创建一段会话归属记录。"""

    context = AgentContext(
        organization_id=organization_id,
        current_user_id=current_user.id,
    )

    service = AgentConversationService(
        session=session,
        context=context,
    )

    # Service检查成员身份、创建记录并提交事务。
    conversation = await service.create_conversation(
        title=request_data.title
    )

    # from_attributes=True允许从ORM属性读取数据，
    # 转换成接口要求的响应对象。
    return AgentConversationResponse.model_validate(
        conversation
    )


@router.get(
    "/{conversation_id}",
    response_model=AgentConversationResponse,
    summary="查询当前用户的指定Agent会话",
)
async def get_agent_conversation(
    # 两个ID都从URL路径中读取。
    organization_id: UUID,
    conversation_id: UUID,

    session: AsyncSession = Depends(
        get_db_session
    ),

    current_user: User = Depends(
        get_current_user
    ),

    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> AgentConversationResponse:
    """查询当前组织中属于当前登录用户的指定会话。"""

    context = AgentContext(
        organization_id=organization_id,
        current_user_id=current_user.id,
    )

    service = AgentConversationService(
        session=session,
        context=context,
    )

    # Service会同时限定：
    # 会话ID、组织ID、当前用户ID。
    #
    # 不存在或归属不符时抛出异常，
    # 不会返回其他用户的会话。
    conversation = await service.get_conversation(
        conversation_id=conversation_id
    )

    return AgentConversationResponse.model_validate(
        conversation
    )