"""
ticket_repository.py

主要功能：
    集中处理Ticket表的数据库操作。

主要部件：
    TicketRepository：
        创建工单；
        后续还会加入查询和更新工单的方法。

Repository只负责数据库读写，
不负责权限判断、业务规则和HTTP响应。
"""

from uuid import UUID



from enterprise_support_agent.infrastructure.database.models.ticket import (
    Ticket,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from enterprise_support_agent.application.tickets.ticket_enums import (
    TicketPriority,
    TicketStatus,
)


class TicketRepository:
    """工单数据访问对象。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        保存本次请求使用的数据库会话。

        session由FastAPI的数据库依赖创建，
        Service创建Repository时会把它传进来。
        """

        self.session = session

    async def create(
        self,
        organization_id: UUID,
        creator_user_id: UUID,
        title: str,
        description: str,
        priority: TicketPriority,
        ticket_id: UUID | None = None,
    ) -> Ticket:
        """
        创建工单记录，但暂时不提交事务。

        接收：
            organization_id：工单所属组织；
            creator_user_id：创建工单的用户；
            title：工单标题；
            description：问题描述；
            priority：工单优先级。

        返回：
            创建后的Ticket ORM对象。
        """

        # 创建一个对应tickets表的Python ORM对象。
        #
        # 没有主动传入status，
        # SQLAlchemy会使用模型中定义的默认值open。
        #
        # 没有传入assignee_user_id，
        # 表示新工单暂时没有处理人员。
        ticket = Ticket(
            organization_id=organization_id,
            creator_user_id=creator_user_id,
            title=title,
            description=description,

            # priority是TicketPriority枚举，
            # .value取出真正保存到数据库的字符串。
            priority=priority.value,
        )

        # 普通接口不指定ID，继续使用原来的随机UUID。
        # Agent重试传入固定ID，让数据库主键阻止同一次操作生成两张工单。
        if ticket_id is not None:
            ticket.id = ticket_id

        # 把Ticket对象加入当前Session。
        #
        # 此时只是告诉Session准备保存，
        # 还没有永久写入数据库。
        self.session.add(
            ticket
        )

        # 执行INSERT语句。
        #
        # flush后数据库已经收到这条记录，
        # 但事务还没有commit，所以仍然可以rollback。
        await self.session.flush()

        # 重新从数据库读取当前工单，
        # 得到id、status、created_at等默认生成的字段。
        await self.session.refresh(
            ticket
        )

        return ticket

    async def get_by_id_and_organization(
        self,
        ticket_id: UUID,
        organization_id: UUID,
    ) -> Ticket | None:
        """
        根据工单ID和组织ID查询一张工单。

        接收：
            ticket_id：需要查询的工单ID；
            organization_id：当前请求对应的组织ID。
            为什么不能只根据工单ID查询：
            因为用户可能在组织A的接口中，传入组织B的工单ID。
        返回：
            找到时返回Ticket ORM对象；
            没找到时返回None。
        """

        # 同时使用两个条件查询：
        #
        # 1. 工单ID必须相同；
        # 2. 工单所属组织也必须相同。
        #
        # 这样即使用户知道其他组织的ticket_id，
        # 也不能通过当前组织的接口查询到它。
        statement = select(
            Ticket
        ).where(
            Ticket.id == ticket_id,
            Ticket.organization_id
            == organization_id,
        )

        # 把SELECT语句发送给PostgreSQL执行。
        result = await self.session.execute(
            statement
        )

        # 找到一条记录时返回Ticket对象；
        # 没有符合两个条件的记录时返回None。
        return result.scalar_one_or_none()

    async def list_page_by_organization(
        self,
        organization_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Ticket], int]:
        """
        分页查询指定组织的全部工单。

        接收：
            organization_id：要查询的组织ID；
            offset：跳过前面多少条记录；
            limit：本次最多返回多少条记录。

        返回：
            当前页的Ticket对象列表；
            该组织的工单总数。
        """

        # 第一条SQL只统计当前组织有多少张工单。
        count_statement = (
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.organization_id
                == organization_id
            )
        )

        # scalar()执行查询，并直接取得COUNT返回的数字。
        total = await self.session.scalar(
            count_statement
        )

        # 第二条SQL查询当前页的具体工单。
        statement = (
            select(Ticket)

            # 只查询当前组织的工单，
            # 防止返回其他组织的数据。
            .where(
                Ticket.organization_id
                == organization_id
            )

            # 最新创建的工单排在前面。
            .order_by(
                Ticket.created_at.desc()
            )

            # 跳过前面指定数量的记录。
            .offset(offset)

            # 限制本次最多返回多少条。
            .limit(limit)
        )

        # 执行查询，并直接取得Ticket ORM对象序列。
        result = await self.session.scalars(
            statement
        )

        # all()取出全部结果，
        # list()转换成普通Python列表。
        tickets = list(
            result.all()
        )

        return tickets, int(total or 0)

    async def list_page_by_creator(
        self,
        organization_id: UUID,
        creator_user_id: UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[Ticket], int]:
        """
        分页查询指定用户在指定组织中创建的工单。

        接收：
            organization_id：当前组织ID；
            creator_user_id：工单创建者ID；
            offset：跳过前面多少条记录；
            limit：本次最多返回多少条记录。

        返回：
            当前页的Ticket对象列表；
            符合条件的工单总数。

        主要用于：
            普通员工查看自己的工单列表。
        """

        # 统计当前用户在当前组织中创建了多少张工单。
        count_statement = (
            select(func.count())
            .select_from(Ticket)
            .where(
                # 工单必须属于当前组织。
                Ticket.organization_id
                == organization_id,

                # 工单必须由当前用户创建。
                Ticket.creator_user_id
                == creator_user_id,
            )
        )

        total = await self.session.scalar(
            count_statement
        )

        # 查询当前页的具体工单。
        statement = (
            select(Ticket)
            .where(
                Ticket.organization_id
                == organization_id,

                Ticket.creator_user_id
                == creator_user_id,
            )
            .order_by(
                Ticket.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        tickets = list(
            result.all()
        )

        return tickets, int(total or 0)


    async def update_assignee(
        self,
        ticket: Ticket,
        assignee_user_id: UUID | None,
    ) -> Ticket:
        """
        修改工单的处理人员，但暂时不提交事务。

        接收：
            ticket：从数据库查询到的工单记录；
            assignee_user_id：新的处理人员ID。
                传入UUID表示分配处理人员；
                传入None表示取消分配。

        返回：
            更新后的Ticket ORM对象。
        """

        # ticket是Session查询出来的ORM对象。
        #
        # 修改对象属性后，SQLAlchemy会记录这个变化，
        # 后续flush时生成对应的UPDATE语句。
        ticket.assignee_user_id = (
            assignee_user_id
        )

        # 将UPDATE发送给PostgreSQL执行。
        #
        # 目前仍未commit，
        # 发生业务错误时仍然可以rollback。
        await self.session.flush()

        # 重新读取数据库中的最新数据，
        # 包括更新后的updated_at。
        await self.session.refresh(
            ticket
        )

        return ticket

    async def update_status(
        self,
        ticket: Ticket,
        status: TicketStatus,
    ) -> Ticket:
        """
        修改工单状态，但暂时不提交事务。

        接收：
            ticket：从数据库查询到的工单记录；
            status：新的工单状态。

        返回：
            更新后的Ticket ORM对象。
        """

        # TicketStatus是字符串枚举，
        # .value取得保存到数据库中的实际字符串。
        ticket.status = status.value

        # 将UPDATE发送给数据库，
        # 但事务还没有永久提交。
        await self.session.flush()

        # 重新读取更新后的工单数据。
        await self.session.refresh(
            ticket
        )

        return ticket
