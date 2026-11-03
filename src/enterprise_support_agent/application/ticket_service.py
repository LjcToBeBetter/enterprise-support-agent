"""
ticket_service.py

主要功能：
    处理工单相关的业务规则和数据库事务。

主要部件：
    TicketService：
        检查用户是否属于组织；
        创建工单；
        成功时提交事务；
        发生异常时回滚事务。

Service负责业务规则，
Repository负责具体数据库操作。
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.exceptions import (
    OrganizationAccessDeniedError,
    TicketAccessDeniedError,
    TicketAssigneeNotOrganizationMemberError,
    TicketAssigneeRoleNotAllowedError,
    TicketNotFoundError,
    InvalidTicketStatusTransitionError,
)
from enterprise_support_agent.application.ticket_enums import (
    TicketPriority,
    TicketStatus,
)
from enterprise_support_agent.infrastructure.database.models.ticket import (
    Ticket,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.ticket_repository import (
    TicketRepository,
)

from enterprise_support_agent.application.organization_roles import (
    OrganizationRole,
)

# 工单允许使用的状态流转规则。
#
# key表示当前状态；
# value集合表示可以修改成哪些状态。
ALLOWED_TICKET_STATUS_TRANSITIONS: dict[
    # 字典的key必须是TicketStatus
    TicketStatus,

    # 字典的value必须是由TicketStatus组成的集合
    set[TicketStatus],
] = {
    # 新工单只能进入处理中状态。
    TicketStatus.OPEN: {
        TicketStatus.IN_PROGRESS,
    },

    # 处理中的工单可以标记为已解决。
    TicketStatus.IN_PROGRESS: {
        TicketStatus.RESOLVED,
    },

    # 已解决的工单可以正式关闭，
    # 也可以因为问题复发而重新进入处理中。
    TicketStatus.RESOLVED: {
        TicketStatus.CLOSED,
        TicketStatus.IN_PROGRESS,
    },

    # 已关闭工单不能继续修改状态。
    TicketStatus.CLOSED: set(),
}



class TicketService:
    """工单业务服务。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        创建工单业务服务。

        session：
            当前请求使用的AsyncSession对象。

        Service和Repository使用同一个Session，
        因此它们的数据库操作属于同一个事务。
        """

        self.session = session

        # 负责tickets表的数据库操作。
        self.ticket_repository = (
            TicketRepository(
                session=session
            )
        )

        # 负责查询用户和组织之间的成员关系。
        self.membership_repository = (
            MembershipRepository(
                session=session
            )
        )

    async def create_ticket(
        self,
        organization_id: UUID,
        creator_user_id: UUID,
        title: str,
        description: str,
        priority: TicketPriority,
    ) -> Ticket:
        """
        检查业务规则并创建工单。

        接收：
            organization_id：工单所属组织；
            creator_user_id：当前登录用户ID；
            title：工单标题；
            description：问题描述；
            priority：工单优先级。

        返回：
            创建完成的Ticket ORM对象。

        异常：
            当前用户不属于该组织时，
            抛出OrganizationAccessDeniedError。
        """

        # 查询当前用户是否属于这个组织。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=creator_user_id,
            )
        )

        # 没有成员关系，说明当前用户不能在该组织创建工单。
        if membership is None:
            raise OrganizationAccessDeniedError(
                organization_id
            )

        try:
            # Repository执行INSERT和flush，
            # 但不会自己提交事务。
            ticket = (
                await self.ticket_repository.create(
                    organization_id=organization_id,
                    creator_user_id=creator_user_id,

                    # 去除标题和描述两端多余空格。
                    title=title.strip(),
                    description=description.strip(),

                    priority=priority,
                )
            )

            # 所有业务操作成功后，
            # 将工单永久写入数据库。
            await self.session.commit()

            return ticket

        except Exception:
            # 创建过程中发生任何异常时，
            # 撤销当前事务中尚未提交的数据库操作。
            await self.session.rollback()

            # 将原来的异常继续向上抛出，
            # 交给统一异常处理器处理。
            raise


    async def get_ticket(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        current_user_id: UUID,
    ) -> Ticket:
        """
        查询指定组织中的一张工单。

        接收：
            organization_id：当前组织ID；
            ticket_id：需要查询的工单ID；
            current_user_id：当前登录用户ID。

        返回：
            有权限访问的Ticket ORM对象。

        权限规则：
            employee只能查看自己创建的工单；
            support和admin可以查看组织内全部工单。
        """

        # 查询当前用户在组织中的成员关系和角色。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 当前用户不属于该组织时，拒绝访问。
        if membership is None:
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 同时根据组织ID和工单ID查询，
        # 避免查询到其他组织的工单。
        ticket = (
            await self.ticket_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                ticket_id=ticket_id,
            )
        )

        # 当前组织中不存在这张工单。
        if ticket is None:
            raise TicketNotFoundError(
                organization_id=organization_id,
                ticket_id=ticket_id,
            )

        # 普通员工只能查看自己创建的工单。
        #
        # 如果角色是employee，
        # 并且工单创建者不是当前用户，
        # 则拒绝访问。
        if (
            membership.role
            == OrganizationRole.EMPLOYEE
            and ticket.creator_user_id
            != current_user_id
        ):
            raise TicketAccessDeniedError(
                ticket_id
            )

        # support和admin不会进入上面的异常分支，
        # 可以查看组织中的全部工单。
        return ticket


    async def list_tickets(
        self,
        organization_id: UUID,
        current_user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[
        list[Ticket],
        int,
        int,
    ]:
        """
        根据当前用户角色分页查询组织工单。

        接收：
            organization_id：当前组织ID；
            current_user_id：当前登录用户ID；
            page：当前页码；
            page_size：每页记录数量。

        返回：
            当前页工单列表；
            符合条件的工单总数；
            总页数。

        权限规则：
            employee只能查询自己创建的工单；
            support和admin可以查询组织全部工单。
        """

        # 查询当前用户是否属于该组织，
        # 同时取得用户在组织中的角色。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 用户不属于该组织时，拒绝查询。
        if membership is None:
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 把页码转换成数据库需要跳过的记录数量。
        #
        # 第1页跳过0条；
        # 第2页跳过page_size条。
        offset = (
            page - 1
        ) * page_size

        # 普通员工只能查询自己创建的工单。
        if (
            membership.role
            == OrganizationRole.EMPLOYEE
        ):
            tickets, total = (
                await self.ticket_repository
                .list_page_by_creator(
                    organization_id=organization_id,
                    creator_user_id=current_user_id,
                    offset=offset,
                    limit=page_size,
                )
            )

        else:
            # support和admin可以查询当前组织的全部工单。
            tickets, total = (
                await self.ticket_repository
                .list_page_by_organization(
                    organization_id=organization_id,
                    offset=offset,
                    limit=page_size,
                )
            )

        # 根据总记录数计算总页数。
        total_pages = (
            total + page_size - 1
        ) // page_size

        return (
            tickets,
            total,
            total_pages,
        )

    async def assign_ticket(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        current_user_id: UUID,
        assignee_user_id: UUID | None,
    ) -> Ticket:
        """
        给工单分配或者取消处理人员。

        接收：
            organization_id：当前组织ID；
            ticket_id：需要操作的工单ID；
            current_user_id：当前登录用户ID；
            assignee_user_id：新的处理人员ID。
                传入None表示取消分配。

        返回：
            更新后的Ticket ORM对象。

        权限规则：
            只有support和admin可以分配工单；
            处理人员必须属于当前组织；
            处理人员必须是support或者admin。
        """

        # 查询当前登录用户在组织中的身份。
        current_membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 用户不属于组织，或者只是普通员工，
        # 都不能分配工单。
        if (
            current_membership is None
            or current_membership.role
            not in (
                OrganizationRole.SUPPORT,
                OrganizationRole.ADMIN,
            )
        ):
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 查询当前组织中的目标工单。
        ticket = (
            await self.ticket_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                ticket_id=ticket_id,
            )
        )

        if ticket is None:
            raise TicketNotFoundError(
                organization_id=organization_id,
                ticket_id=ticket_id,
            )

        # assignee_user_id为None表示取消分配，
        # 不需要检查目标用户的成员关系。
        if assignee_user_id is not None:
            assignee_membership = (
                await self.membership_repository
                .get_by_organization_and_user(
                    organization_id=organization_id,
                    user_id=assignee_user_id,
                )
            )

            # 指定的处理人员不属于当前组织。
            if assignee_membership is None:
                raise (
                    TicketAssigneeNotOrganizationMemberError(
                        organization_id=organization_id,
                        assignee_user_id=assignee_user_id,
                    )
                )

            # 只有support和admin可以成为处理人员。
            if assignee_membership.role not in (
                OrganizationRole.SUPPORT,
                OrganizationRole.ADMIN,
            ):
                raise TicketAssigneeRoleNotAllowedError(
                    assignee_user_id
                )

        try:
            # Repository修改ORM对象并执行UPDATE。
            updated_ticket = (
                await self.ticket_repository
                .update_assignee(
                    ticket=ticket,
                    assignee_user_id=assignee_user_id,
                )
            )

            # 所有检查和更新成功后提交事务。
            await self.session.commit()

            return updated_ticket

        except Exception:
            # 更新或提交失败时撤销事务。
            await self.session.rollback()
            raise

    async def update_ticket_status(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        current_user_id: UUID,
        target_status: TicketStatus,
    ) -> Ticket:
        """
        修改工单状态。

        接收：
            organization_id：当前组织ID；
            ticket_id：需要修改的工单ID；
            current_user_id：当前登录用户ID；
            target_status：希望修改成的新状态。

        返回：
            更新后的Ticket ORM对象。

        权限规则：
            employee不能修改工单状态；
            support只能修改分配给自己的工单；
            admin可以修改组织内任意工单。

        状态规则：
            只能按照ALLOWED_TICKET_STATUS_TRANSITIONS
            中规定的顺序修改。
        """

        # 查询当前用户在组织中的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 不属于组织，或者只是普通员工，
        # 都不能修改工单状态。
        if (
            membership is None
            or membership.role
            == OrganizationRole.EMPLOYEE
        ):
            raise OrganizationAccessDeniedError(
                organization_id
            )

        # 查询当前组织中的目标工单。
        ticket = (
            await self.ticket_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                ticket_id=ticket_id,
            )
        )

        if ticket is None:
            raise TicketNotFoundError(
                organization_id=organization_id,
                ticket_id=ticket_id,
            )

        # support只能处理分配给自己的工单。
        #
        # admin不会进入这个分支，
        # 可以修改组织内任意工单。
        if (
            membership.role
            == OrganizationRole.SUPPORT
            and ticket.assignee_user_id
            != current_user_id
        ):
            raise TicketAccessDeniedError(
                ticket_id
            )

        # 数据库中保存的是字符串，
        # 这里把它转换成TicketStatus枚举。
        current_status = TicketStatus(
            ticket.status
        )

        # 根据当前状态取得允许进入的下一状态集合。
        allowed_statuses = (
            ALLOWED_TICKET_STATUS_TRANSITIONS[
                current_status
            ]
        )

        # 目标状态不在允许集合中，
        # 说明这次状态修改不符合业务流程。
        if target_status not in allowed_statuses:
            raise InvalidTicketStatusTransitionError(
                current_status=current_status.value,
                target_status=target_status.value,
            )

        try:
            # Repository修改ORM对象并执行UPDATE。
            updated_ticket = (
                await self.ticket_repository
                .update_status(
                    ticket=ticket,
                    status=target_status,
                )
            )

            # 更新成功后永久提交事务。
            await self.session.commit()

            return updated_ticket

        except Exception:
            # 更新或者提交失败时撤销事务。
            await self.session.rollback()
            raise