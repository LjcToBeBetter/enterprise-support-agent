"""在PostgreSQL临时表中验证重试不会重复创建，不写正式业务表。"""

import os
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from enterprise_support_agent.application.tickets.ticket_enums import TicketPriority
from enterprise_support_agent.application.tickets.ticket_service import TicketService
from enterprise_support_agent.infrastructure.database.models.organization_membership import OrganizationMembership
from enterprise_support_agent.infrastructure.database.session import engine


@unittest.skipUnless(os.environ.get("RUN_POSTGRES_RECOVERY_TESTS") == "1", "需要明确启用本机PostgreSQL临时表测试")
class TicketRecoveryPostgresTests(unittest.IsolatedAsyncioTestCase):
    """真实INSERT、提交、重新读取和主键冲突；连接关闭后临时表消失。"""

    async def test_committed_ticket_is_reused_after_application_failure(self):
        try:
            async with engine.connect() as connection:
                # PostgreSQL会优先找到当前连接的同名临时表。
                # INCLUDING INDEXES保留主键唯一性；不会复制正式表中的记录。
                for table in ("tickets", "organization_memberships"):
                    await connection.execute(text(
                        f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL) ON COMMIT PRESERVE ROWS"
                    ))
                await connection.commit()
                organization_id, user_id, ticket_id = uuid4(), uuid4(), uuid4()
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    session.add(OrganizationMembership(organization_id=organization_id, user_id=user_id, role="admin"))
                    await session.commit()
                    arguments = dict(
                        organization_id=organization_id, creator_user_id=user_id,
                        title="临时表恢复测试", description="模拟数据库提交成功、流程结果尚未存档时发生异常。",
                        priority=TicketPriority.HIGH, ticket_id=ticket_id,
                    )
                    first = await TicketService(session).create_ticket(**arguments)
                    self.assertEqual(first.id, ticket_id)

                # 重建Session和Service，模拟原进程已退出后重新运行。
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    recovered = await TicketService(session).create_ticket(**arguments)
                    self.assertEqual(recovered.id, ticket_id)
                    count = await session.scalar(text("SELECT count(*) FROM pg_temp.tickets"))
                    self.assertEqual(count, 1)
                    with self.assertRaisesRegex(ValueError, "参数不能"):
                        await TicketService(session).create_ticket(**{**arguments, "title": "试图更换同一次操作的标题"})
                    await session.rollback()

                    # 相同内容的新操作仍可创建，不能把正常新工单误当作重复请求。
                    await TicketService(session).create_ticket(**{**arguments, "ticket_id": uuid4()})
                    self.assertEqual(await session.scalar(text("SELECT count(*) FROM pg_temp.tickets")), 2)
                    await session.commit()

                # 直接重复INSERT也会被真实数据库主键挡住。
                with self.assertRaises(IntegrityError):
                    await connection.execute(text(
                        "INSERT INTO pg_temp.tickets SELECT * FROM pg_temp.tickets WHERE id=:id"
                    ), {"id": ticket_id})
                await connection.rollback()
        finally:
            # 关闭物理连接，销毁此测试连接创建的临时表。
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
