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

from enterprise_support_agent.api.agent.agent_schemas import (
    AgentRequest,
    AgentResponse,
    AgentRetryRequest,
    AgentExecutionStateResponse,
)
from enterprise_support_agent.api.auth.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.api.organizations.organization_dependencies import (
    require_organization_member,
)
from enterprise_support_agent.application.agent.agent_context import (
    AgentContext,
)
from enterprise_support_agent.application.agent.langgraph_agent_service import (
    LangGraphAgentService,
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
# PostgreSQL存档组件的类型，
# 用于标注接口参数。
from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)

# 我们自己写的依赖函数，
# 从request.app.state中取得已有Checkpointer。
from enterprise_support_agent.api.agent.checkpoint_dependencies import (
    get_checkpointer,
)
from enterprise_support_agent.application.agent.memory.agent_conversation_service import (
    AgentConversationService,
)
from enterprise_support_agent.api.agent.agent_approval_schemas import (
    PendingTicketApprovalResponse,
    TicketApprovalDecisionRequest,
)
from enterprise_support_agent.api.agent.rate_limit_dependencies import (
    require_agent_rate_limit,
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

    # 执行接口函数之前，先检查这个用户的请求次数。
    # 未超限：继续执行接口。
    # 已超限：直接返回429，不执行下面的Agent逻辑。
    #
    # 这里只需要检查通过，不需要接收返回值，
    # 所以把依赖放在装饰器的dependencies列表中。
    dependencies=[
        Depends(require_agent_rate_limit),
    ],
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

    # FastAPI先执行get_checkpointer()，
    # 再把返回的AsyncPostgresSaver对象传到这里。
    #
    # 不是在这里创建新对象，
    # 而是取得lifespan启动时创建的那个对象。
    checkpointer: AsyncPostgresSaver = Depends(
        get_checkpointer
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

    conversation_service = AgentConversationService(
        session=session,
        context=context,
    )

    # 同时检查：
    # 1. 当前用户仍属于该组织；
    # 2. 会话ID存在；
    # 3. 会话属于当前组织和当前用户。
    #
    # 检查失败会直接返回对应错误，
    # 不会继续调用模型或读取历史存档。
    conversation = (
        await conversation_service.get_conversation(
            conversation_id=request_data.conversation_id
        )
    )


    # 为本次请求创建独立的AgentService。
    # service = AgentService(
    #     session=session,
    #     context=context,
    # )

    # 使用支持会话持久化的Service。
    service = LangGraphAgentService(
        session=session,
        context=context,

        # 由Depends取得的共享存档组件。
        checkpointer=checkpointer,
    )

    # Service负责模型调用、工具执行和多轮循环。
    result = await service.run(
        query=request_data.query,

        # 使用已经检查过归属的会话ID。
        # Service内部会将它作为thread_id。
        conversation_id = conversation.id,
    )

    # 默认没有待审批信息。
    pending_approval = None

    # Service返回了待确认的工单时，
    # 将它转换为接口规定的响应格式。
    if result.pending_approval is not None:
        pending_approval = PendingTicketApprovalResponse(
            tool_call_id=(
                result.pending_approval.tool_call_id
            ),
            arguments=(
                result.pending_approval.arguments
            ),
        )

    # 把执行状态、回答、待审批内容交给前端。
    return AgentResponse(
        status=result.status,
        answer=result.answer,
        tool_call_count=result.tool_call_count,
        conversation_id=conversation.id,
        pending_approval=pending_approval,
    )

@router.post(
    "/conversations/{conversation_id}/approval",
    response_model=AgentResponse,
    summary="审批工单创建操作并继续Agent任务",
)
async def approve_agent_ticket(
    # 从URL读取组织ID和会话ID。
    organization_id: UUID,
    conversation_id: UUID,

    # 请求体包含工具调用编号，以及同意或拒绝。
    request_data: TicketApprovalDecisionRequest,

    session: AsyncSession = Depends(
        get_db_session
    ),
    checkpointer: AsyncPostgresSaver = Depends(
        get_checkpointer
    ),
    current_user: User = Depends(
        get_current_user
    ),
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> AgentResponse:
    """接收用户决定，恢复当前会话中等待审批的任务。"""

    # 身份来自登录信息，不由前端自行指定。
    context = AgentContext(
        organization_id=organization_id,
        current_user_id=current_user.id,
    )

    service = LangGraphAgentService(
        session=session,
        context=context,
        checkpointer=checkpointer,
    )

    # resume内部会再次检查：
    # 会话归属、待审批操作编号，以及是否确实在等待审批。
    result = await service.resume(
        conversation_id=conversation_id,
        tool_call_id=request_data.tool_call_id,
        approved=request_data.approved,
    )

    # 恢复后仍可能再次暂停，所以也要处理待审批信息。
    pending_approval = None

    if result.pending_approval is not None:
        pending_approval = PendingTicketApprovalResponse(
            tool_call_id=(
                result.pending_approval.tool_call_id
            ),
            arguments=(
                result.pending_approval.arguments
            ),
        )

    return AgentResponse(
        status=result.status,
        answer=result.answer,
        tool_call_count=result.tool_call_count,
        conversation_id=conversation_id,
        pending_approval=pending_approval,
    )


@router.get(
    "/conversations/{conversation_id}/execution",
    response_model=AgentExecutionStateResponse,
    summary="查询当前会话的任务状态",
)
async def get_agent_execution_state(
    organization_id: UUID,
    conversation_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMembership = Depends(require_organization_member),
) -> AgentExecutionStateResponse:
    """只读状态；服务内部还会核对会话属于当前组织和当前用户。"""
    service = LangGraphAgentService(
        session=session, checkpointer=checkpointer,
        context=AgentContext(
            organization_id=organization_id, current_user_id=current_user.id,
        ),
    )
    return AgentExecutionStateResponse.model_validate(
        await service.get_execution_state(conversation_id),
    )


@router.post(
    "/conversations/{conversation_id}/retry",
    response_model=AgentResponse,
    summary="在原会话中重试中断的任务",
    dependencies=[Depends(require_agent_rate_limit)],
)
async def retry_agent_execution(
    organization_id: UUID,
    conversation_id: UUID,
    request_data: AgentRetryRequest,
    session: AsyncSession = Depends(get_db_session),
    checkpointer: AsyncPostgresSaver = Depends(get_checkpointer),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMembership = Depends(require_organization_member),
) -> AgentResponse:
    """恢复指定任务；不重新发送问题，也不将重试当成人工批准。"""
    service = LangGraphAgentService(
        session=session, checkpointer=checkpointer,
        context=AgentContext(
            organization_id=organization_id, current_user_id=current_user.id,
            allow_ticket_creation=request_data.allow_ticket_creation is True,
        ),
    )
    result = await service.retry(
        conversation_id, request_data.execution_id,
        allow_ticket_creation=request_data.allow_ticket_creation,
    )
    pending = result.pending_approval
    return AgentResponse(
        status=result.status, answer=result.answer,
        tool_call_count=result.tool_call_count, conversation_id=conversation_id,
        pending_approval=PendingTicketApprovalResponse(
            tool_call_id=pending.tool_call_id, arguments=pending.arguments,
        ) if pending is not None else None,
    )
