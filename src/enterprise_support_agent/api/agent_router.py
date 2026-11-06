"""
企业支持Agent接口。

提供：
POST /organizations/{organization_id}/agent/chat

流程：
1. 验证登录身份和组织成员身份；
2. 创建AgentContext；
3. 调用AgentService；
4. 返回最终回答和工具调用次数。
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.agent_schemas import (
    AgentRequest,
    AgentResponse,
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
from enterprise_support_agent.application.agent_service import (
    AgentService,
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


# 当前文件中所有接口的公共路径和Swagger分组。
router = APIRouter(
    prefix=(
        "/organizations/"
        "{organization_id}/agent"
    ),
    tags=["agent"],
)


@router.post(
    "/chat",
    response_model=AgentResponse,
    summary="企业支持Agent问答",
)
async def chat_with_agent(
    # 从URL路径读取组织ID。
    organization_id: UUID,

    # 从JSON请求体读取用户问题。
    request_data: AgentRequest,

    # 为本次请求提供数据库会话。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT，取得真实的当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),

    # 检查当前用户是否属于URL中的组织。
    #
    # 检查失败会直接抛出异常，
    # 不会进入下面的Agent执行逻辑。
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> AgentResponse:
    """执行一次企业支持Agent任务。"""

    # 使用已经验证过的请求身份创建上下文。
    #
    # 用户ID来自JWT对应的数据库用户，
    # 不从请求体或模型参数中读取。
    context = AgentContext(
        organization_id=organization_id,
        current_user_id=current_user.id,
        allow_ticket_creation=(
            request_data.allow_ticket_creation
        ),
    )

    # 为本次请求创建独立的AgentService。
    service = AgentService(
        session=session,
        context=context,
    )

    # Service负责模型调用、工具执行和多轮循环。
    result = await service.run(
        query=request_data.query
    )

    # 转换成接口规定的响应格式。
    return AgentResponse(
        answer=result.answer,
        tool_call_count=result.tool_call_count,
    )