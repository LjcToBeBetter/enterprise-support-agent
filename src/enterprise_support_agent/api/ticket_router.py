"""
ticket_router.py

主要功能：
    定义企业工单相关的HTTP接口。

主要部件：
    router：
        保存所有工单接口。

    create_ticket：
        接收客户端提交的工单内容；
        取得当前登录用户；
        调用TicketService创建工单；
        返回创建后的工单数据。
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    status,
    Query
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.api.ticket_schemas import (
    AssignTicketRequest,
    CreateTicketRequest,
    TicketListResponse,
    TicketResponse,
    UpdateTicketStatusRequest,
)
from enterprise_support_agent.application.ticket_service import (
    TicketService,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)


# 当前文件中所有接口的公共路径前缀。
#
# 例如在下面注册空路径""，
# 最终接口就是：
# POST /organizations/{organization_id}/tickets
router = APIRouter(
    prefix=(
        "/organizations/"
        "{organization_id}/tickets"
    ),
    tags=["tickets"],
)


@router.post(
    "",
    response_model=TicketResponse,

    # 201表示服务器成功创建了新工单。
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    # FastAPI从URL路径中读取组织ID，
    # 并转换成UUID对象。
    organization_id: UUID,

    # FastAPI从请求体中读取并校验工单内容。
    request_data: CreateTicketRequest,

    # 为本次请求创建数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 调用接口前验证JWT，
    # 验证成功后取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> TicketResponse:
    """
    在指定组织中创建工单。

    当前登录用户必须属于该组织，
    具体业务检查由TicketService完成。
    """

    # 使用本次请求的Session创建Service。
    service = TicketService(
        session=session
    )

    # Service检查组织成员身份，
    # 然后创建工单并提交事务。
    ticket = await service.create_ticket(
        organization_id=organization_id,
        creator_user_id=current_user.id,
        title=request_data.title,
        description=request_data.description,
        priority=request_data.priority,
    )

    # 从Ticket ORM对象的属性中读取字段，
    # 转换成接口规定的响应格式。
    return TicketResponse.model_validate(
        ticket
    )

@router.get(
    "",
    response_model=TicketListResponse,
)
async def list_tickets(
    # 当前需要查询哪个组织的工单。
    organization_id: UUID,

    # 当前页码，默认第1页，最小为1。
    page: int = Query(
        default=1,
        ge=1,
    ),

    # 每页默认20条，
    # 最少1条，最多100条。
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> TicketListResponse:
    """
    分页查询指定组织中的工单。

    employee只能看到自己创建的工单；
    support和admin可以看到组织全部工单。
    """

    service = TicketService(
        session=session
    )

    # Service根据当前用户的组织角色，
    # 自动决定查询全部工单还是只查自己的工单。
    tickets, total, total_pages = (
        await service.list_tickets(
            organization_id=organization_id,
            current_user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    )

    # 将Ticket ORM对象列表
    # 转换成TicketResponse对象列表。
    items: list[TicketResponse] = []

    for ticket in tickets:
        response_item = (
            TicketResponse.model_validate(
                ticket
            )
        )

        items.append(
            response_item
        )

    return TicketListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
)
async def get_ticket(
    # FastAPI从URL中读取组织ID。
    organization_id: UUID,

    # FastAPI从URL中读取工单ID。
    ticket_id: UUID,

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> TicketResponse:
    """
    根据工单ID查询单张工单。

    employee只能查看自己创建的工单；
    support和admin可以查看组织中的全部工单。
    """

    service = TicketService(
        session=session
    )

    # Service会同时检查：
    # 当前用户是否属于组织；
    # 工单是否属于当前组织；
    # 当前用户是否有权查看这张工单。
    ticket = await service.get_ticket(
        organization_id=organization_id,
        ticket_id=ticket_id,
        current_user_id=current_user.id,
    )

    return TicketResponse.model_validate(
        ticket
    )

@router.patch(
    "/{ticket_id}/assignee",
    response_model=TicketResponse,
)
async def assign_ticket(
    # 当前工单属于哪个组织。
    organization_id: UUID,

    # 需要分配处理人员的工单ID。
    ticket_id: UUID,

    # 从请求体中读取新的处理人员ID。
    request_data: AssignTicketRequest,

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> TicketResponse:
    """
    给工单分配或者取消处理人员。

    只有support和admin可以调用；
    被分配用户必须属于当前组织；
    被分配用户必须是support或admin。
    """

    service = TicketService(
        session=session
    )

    # Service负责完成权限检查、成员检查、
    # 角色检查、数据库更新和事务提交。
    ticket = await service.assign_ticket(
        organization_id=organization_id,
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        assignee_user_id=(
            request_data.assignee_user_id
        ),
    )

    return TicketResponse.model_validate(
        ticket
    )

@router.patch(
    "/{ticket_id}/status",
    response_model=TicketResponse,
)
async def update_ticket_status(
    # 当前工单所属的组织ID。
    organization_id: UUID,

    # 需要修改状态的工单ID。
    ticket_id: UUID,

    # 从请求体中读取目标状态。
    request_data: UpdateTicketStatusRequest,

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> TicketResponse:
    """
    修改工单状态。

    employee不能修改状态；
    support只能修改分配给自己的工单；
    admin可以修改组织内任意工单。
    """

    service = TicketService(
        session=session
    )

    # Service负责权限检查和状态流转检查。
    ticket = await service.update_ticket_status(
        organization_id=organization_id,
        ticket_id=ticket_id,
        current_user_id=current_user.id,
        target_status=request_data.status,
    )

    return TicketResponse.model_validate(
        ticket
    )