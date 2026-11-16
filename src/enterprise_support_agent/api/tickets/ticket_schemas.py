"""
ticket_schemas.py

主要功能：
    定义工单接口接收和返回的数据格式。

主要部件：
    CreateTicketRequest：
        创建工单时客户端需要提交的数据。

    AssignTicketRequest：
        分配或者取消分配处理人员时提交的数据。

    UpdateTicketStatusRequest：
        修改工单状态时提交的数据。

    TicketResponse：
        单个工单的响应格式。

    TicketListResponse：
        工单分页列表的响应格式。
"""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from enterprise_support_agent.application.tickets.ticket_enums import (
    TicketPriority,
    TicketStatus,
)


class CreateTicketRequest(BaseModel):
    """创建工单时客户端提交的数据。"""

    # 工单标题，长度必须在3到200之间。
    title: str = Field(
        min_length=3,
        max_length=200,
    )

    # 工单的完整问题描述。
    description: str = Field(
        min_length=10,
        max_length=10000,
    )

    # 没有传priority时，默认使用中等优先级。
    priority: TicketPriority = (
        TicketPriority.MEDIUM
    )


class AssignTicketRequest(BaseModel):
    """分配工单处理人员的请求格式。"""

    # 要把工单分配给哪个用户。
    #
    # 传入UUID：将工单分配给指定用户。
    # 传入null：取消当前处理人员。
    assignee_user_id: UUID | None


class UpdateTicketStatusRequest(BaseModel):
    """修改工单状态的请求格式。"""

    # 新的工单状态。
    #
    # Pydantic会限制它只能是：
    # open、in_progress、resolved、closed。
    status: TicketStatus


class TicketResponse(BaseModel):
    """单个工单的响应格式。"""

    # 允许Pydantic直接从Ticket ORM对象属性中读取数据。
    model_config = ConfigDict(
        from_attributes=True
    )

    # 工单自己的唯一编号。
    id: UUID

    # 工单属于哪个组织。
    organization_id: UUID

    # 谁创建了这张工单。
    creator_user_id: UUID

    # 当前处理人员。
    # 工单未分配时返回null。
    assignee_user_id: UUID | None

    title: str
    description: str

    # 返回时将数据库中的字符串转换成对应枚举。
    status: TicketStatus
    priority: TicketPriority

    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    """工单分页列表的响应格式。"""

    # 当前页的工单数据。
    items: list[TicketResponse]

    # 符合查询条件的工单总数。
    total: int

    # 当前页码。
    page: int

    # 每页记录数量。
    page_size: int

    # 总页数。
    total_pages: int