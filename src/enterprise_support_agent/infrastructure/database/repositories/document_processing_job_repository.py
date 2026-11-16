"""负责文档处理任务记录的数据库读写。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.models.document_processing_job import (
    DocumentProcessingJob,
)

from enterprise_support_agent.application.documents.document_enums import (
    DocumentJobStatus,
)
# and_要求条件同时成立；or_表示条件满足任意一组即可。
# func用于构造数据库函数调用，例如取得当前时间。
from sqlalchemy import and_, case, func, or_, select, update

# timedelta表示一段时间，例如120秒。
from datetime import timedelta

class DocumentProcessingJobRepository:
    """操作document_processing_jobs任务记录表。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """保存当前业务使用的数据库Session。"""

        # 后面的数据库操作都使用这个Session。
        # Service和Repository共享它，统一管理事务。
        self.session = session

    async def create(
        self,
        organization_id: UUID,
        document_id: UUID,
        document_version: int,
        requested_by_user_id: UUID,
    ) -> DocumentProcessingJob:
        """
        创建一条文档处理任务记录，返回任务ORM对象。

        organization_id：任务所属组织。
        document_id：需要处理的文档。
        document_version：需要处理的文档版本。
        requested_by_user_id：提交任务的当前登录用户。

        这里只执行flush，事务由上层Service提交。
        """

        # 创建任务ORM对象。
        # 相当于先在Python中准备好一条待插入的记录。
        job = DocumentProcessingJob(
            organization_id=organization_id,
            document_id=document_id,
            document_version=document_version,
            requested_by_user_id=requested_by_user_id,

            # 其余字段使用模型中定义的默认值：
            # status：pending。
            # attempt_count：0。
            # max_attempts：3。
        )

        # 将任务对象加入Session，准备保存。
        self.session.add(job)

        # 向PostgreSQL执行INSERT，但尚未提交事务。
        #
        # 在插入过程中，SQLAlchemy会调用模型中的uuid4，
        # 生成任务ID。执行完成后，可以读取job.id。
        await self.session.flush()

        # 从数据库重新读取这条记录，
        # 取得状态、创建时间等字段。
        await self.session.refresh(job)

        # 将带有任务ID的ORM对象返回给上层Service。
        return job

    async def get_by_id_and_organization(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> DocumentProcessingJob | None:
        """
        查询指定组织中的指定任务。

        organization_id：任务所属组织。
        job_id：需要查询的任务ID。

        找到时返回任务ORM对象；
        找不到时返回None。
        """

        # 构造查询，两个条件必须同时满足：
        # 1. 任务ID匹配；
        # 2. 任务所属组织匹配。
        statement = select(
            DocumentProcessingJob
        ).where(
            DocumentProcessingJob.id == job_id,
            DocumentProcessingJob.organization_id
            == organization_id,
        )

        # 将SELECT发送给PostgreSQL执行。
        result = await self.session.execute(
            statement
        )

        # 从查询结果中取出一个ORM对象。
        # id是主键，所以最多只有一条匹配记录。
        # 没有匹配记录时返回None。
        return result.scalar_one_or_none()


    async def mark_queued(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> bool:
        """
        消息发送成功后，把仍处于pending的任务标记为queued。

        返回True：本次更新了一条记录。
        返回False：没有满足更新条件的记录。

        事务由上层Service提交。
        """

        statement = (
            # 指定要更新哪张表。
            update(DocumentProcessingJob)

            # 三个条件必须同时满足。
            .where(
                DocumentProcessingJob.id == job_id,
                DocumentProcessingJob.organization_id
                == organization_id,

                # 只更新仍然等待发送的任务。
                DocumentProcessingJob.status
                == DocumentJobStatus.PENDING.value,
            )

            # values指定需要修改的字段及新值。
            .values(
                status=DocumentJobStatus.QUEUED.value,
                error_message=None,
            )

            # returning表示：
            # 更新后，让PostgreSQL返回被更新记录的id。
            # 没有匹配记录时，就没有id返回。
            .returning(DocumentProcessingJob.id)
        )

        # 执行UPDATE，尚未提交事务。
        result = await self.session.execute(
            statement
        )

        # 这里取到的是返回的任务ID，类型为UUID；
        # 没有更新任何记录时，得到None。
        updated_job_id = result.scalar_one_or_none()

        # 有返回的ID，说明本次更新了一条记录z。
        return updated_job_id is not None


    async def mark_succeeded(
        self,
        organization_id: UUID,
        job_id: UUID,
        execution_token: UUID,
    ) -> bool:
        """
        将正在执行的任务标记为成功，并记录结束时间。

        返回True：成功更新了一条任务记录。
        返回False：没有符合条件的任务。

        事务由上层调用者提交。
        """

        statement = (
            update(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.id == job_id,
                DocumentProcessingJob.organization_id
                == organization_id,

                # 只有正在执行的任务才能在这里标记成功。
                DocumentProcessingJob.status
                == DocumentJobStatus.RUNNING.value,

                # 必须仍然是本次执行，才能保存成功结果。
                # 如果任务已被重新领取，数据库中的编号会改变，
                # 旧Worker就无法更新这条任务记录。
                DocumentProcessingJob.execution_token
                == execution_token,
            )
            .values(
                status=DocumentJobStatus.SUCCEEDED.value,

                # finished_at是任务表的“最终结束时间”字段。
                # func.now()表示使用数据库当前时间。
                finished_at=func.now(),

                # 成功完成后，清除之前的失败信息。
                error_message=None,

                # 任务已经结束，清除执行编号和租约。
                execution_token=None,
                lease_expires_at=None,
            )

            # 要求数据库返回被更新任务的ID。
            # 没有符合条件的记录时，不会返回ID。
            .returning(DocumentProcessingJob.id)
        )

        # 执行UPDATE，尚未提交事务。
        result = await self.session.execute(statement)

        # 取得被更新任务的UUID，没有更新记录时得到None。
        updated_job_id = result.scalar_one_or_none()

        return updated_job_id is not None


    async def mark_failed_or_retry(
        self,
        organization_id: UUID,
        job_id: UUID,
        # 领取任务时生成的执行编号，用于核对本次执行身份。
        execution_token: UUID,
        error_message: str,
    ) -> DocumentJobStatus | None:
        """
        记录本次执行失败，并决定是否继续重试。

        返回QUEUED：还有执行次数，等待重新执行。
        返回FAILED：次数已耗尽，任务最终失败。
        返回None：没有找到符合更新条件的任务。

        事务由上层Worker提交。
        """

        # 构造数据库比较条件。
        # 真正执行SQL时，由数据库比较这两个字段。
        can_retry = (
            DocumentProcessingJob.attempt_count
            < DocumentProcessingJob.max_attempts
        )

        statement = (
            update(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.id == job_id,
                DocumentProcessingJob.organization_id
                == organization_id,

                # 只处理正在执行的任务。
                DocumentProcessingJob.status
                == DocumentJobStatus.RUNNING.value,

                # 执行编号必须匹配，旧Worker才能被拦住，
                # 避免它覆盖新一轮执行的状态。
                DocumentProcessingJob.execution_token
                == execution_token,
            )
            .values(
                # 本次执行结束，清除执行编号和租约。
                # 下次重新执行时会生成新的编号和到期时间。
                execution_token=None,
                lease_expires_at=None,

                # case表示数据库中的条件选择：
                # 条件成立 → 使用QUEUED；
                # 否则 → 使用else_指定的FAILED。
                status=case(
                    (
                        can_retry,
                        DocumentJobStatus.QUEUED.value,
                    ),
                    else_=DocumentJobStatus.FAILED.value,
                ),

                # 还能重试：任务尚未最终结束，结束时间为空。
                # 次数耗尽：记录数据库当前时间作为结束时间。
                finished_at=case(
                    (can_retry, None),
                    else_=func.now(),
                ),

                # 保存简短错误说明，最多保留2000个字符。
                error_message=error_message[:2000],
            )

            # 这次返回更新后的status字段，而不是任务ID。
            .returning(DocumentProcessingJob.status)
        )

        result = await self.session.execute(statement)

        # 得到更新后的状态字符串；
        # 没有匹配记录时得到None。
        updated_status = result.scalar_one_or_none()

        if updated_status is None:
            return None

        # 将字符串转换成任务状态枚举。
        # 例如："queued" → DocumentJobStatus.QUEUED。
        return DocumentJobStatus(updated_status)



    # 作用是更新任务状态，供后面的 Worker 调用。
    async def try_mark_running(
        self,
        organization_id: UUID,
        job_id: UUID,

        # Worker为本次执行生成的唯一编号。
        execution_token: UUID,
    ) -> bool:
        """
        尝试取得任务执行资格，并将任务标记为running。

        等待执行的任务，或者租约已经过期的running任务，
        都可以尝试开始新一轮执行，但不能超过执行次数上限。

        返回True：成功更新，可以在提交事务后执行任务。
        返回False：没有符合条件的任务，本次不能开始执行。

        事务由上层调用者提交。
        """

        statement = (
            update(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.id == job_id,
                DocumentProcessingJob.organization_id
                == organization_id,

                # 两种情况允许开始：
                # 1. 原本就在等待执行；
                # 2. 原Worker没有继续续期，租约已到期。
                # running且租约有效的任务不能被另一个Worker接手。
                or_(
                    DocumentProcessingJob.status.in_(
                        (
                            DocumentJobStatus.PENDING.value,
                            DocumentJobStatus.QUEUED.value,
                        )
                    ),
                    and_(
                        DocumentProcessingJob.status
                        == DocumentJobStatus.RUNNING.value,
                        DocumentProcessingJob.lease_expires_at
                        <= func.now(),
                    ),
                ),

                # 已执行次数必须小于次数上限。
                DocumentProcessingJob.attempt_count
                < DocumentProcessingJob.max_attempts,
            )
            .values(
                status=DocumentJobStatus.RUNNING.value,

                # 保存本次执行的编号。
                # 后续续期、更新结果时，都需要核对这个编号。
                execution_token=execution_token,

                # 租约到期时间 = 数据库当前时间 + 120秒。
                #
                # func.now()由数据库取得当前时间；
                # timedelta(seconds=120)表示120秒的时间长度。
                #
                # 后面会让Worker定期延长租约，
                # 120秒不是整个文档处理任务的最长执行时间。
                lease_expires_at=(
                        func.now() + timedelta(seconds=120)
                ),


                # 让数据库在原来的次数上加1。
                attempt_count=(
                    DocumentProcessingJob.attempt_count + 1
                ),

                # 给任务表的started_at字段设置“首次开始执行时间”。
                #
                # coalesce是数据库函数，取第一个不为NULL的值：
                # 原来已有开始时间 → 保留原值；
                # 原来没有开始时间 → 使用数据库当前时间。
                started_at=func.coalesce(
                    DocumentProcessingJob.started_at,
                    func.now(),
                ),

                # 开始执行时清除上次的失败信息和结束时间。
                error_message=None,
                finished_at=None,
            )

            # 要求PostgreSQL在更新后，
            # 返回被更新任务的id，供后面的代码判断是否更新成功。
            #
            # 更新了一条记录 → 返回该记录的UUID；
            # 没有记录符合更新条件 → 没有返回记录。
            .returning(DocumentProcessingJob.id)
        )

        # 在同一条UPDATE中判断条件并修改记录，
        # 避免两个Worker同时取得同一个待执行任务。
        result = await self.session.execute(statement)

        updated_job_id = result.scalar_one_or_none()

        return updated_job_id is not None


    async def mark_exhausted_job_failed(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> bool:
        """
        将次数已耗尽、且没有有效执行租约的任务标记为失败。

        例如第三次执行中途退出，恢复时不能再开始第四次执行。
        仍在正常执行、租约有效的任务不会被这个方法修改。
        返回是否更新成功，事务由Worker提交。
        """

        statement = (
            update(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.id == job_id,
                DocumentProcessingJob.organization_id
                == organization_id,
                DocumentProcessingJob.attempt_count
                >= DocumentProcessingJob.max_attempts,
                or_(
                    DocumentProcessingJob.status.in_(
                        (
                            DocumentJobStatus.PENDING.value,
                            DocumentJobStatus.QUEUED.value,
                        )
                    ),
                    and_(
                        DocumentProcessingJob.status
                        == DocumentJobStatus.RUNNING.value,
                        DocumentProcessingJob.lease_expires_at
                        <= func.now(),
                    ),
                ),
            )
            .values(
                status=DocumentJobStatus.FAILED.value,
                finished_at=func.now(),
                error_message="任务执行次数已耗尽，不能继续重试",
                execution_token=None,
                lease_expires_at=None,
            )
            .returning(DocumentProcessingJob.id)
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None


    async def renew_lease(
        self,
        organization_id: UUID,
        job_id: UUID,
        execution_token: UUID,
    ) -> bool:
        """
        延长本次执行的租约。

        任务必须正在执行、执行编号匹配，并且租约尚未到期。

        返回True：续期成功。
        返回False：已失去执行资格，不能继续续期。
        事务由调用者提交。
        """

        statement = (
            update(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.id == job_id,
                DocumentProcessingJob.organization_id
                == organization_id,

                # 任务仍然处于执行中。
                DocumentProcessingJob.status
                == DocumentJobStatus.RUNNING.value,

                # 必须是当前这一次执行。
                DocumentProcessingJob.execution_token
                == execution_token,

                # 已经过期的租约不能通过这个方法重新激活。
                DocumentProcessingJob.lease_expires_at
                > func.now(),
            )
            .values(
                # 每次都延长到“当前时间之后的120秒”，
                # 而不是在原到期时间上累计增加120秒。
                lease_expires_at=(
                    func.now() + timedelta(seconds=120)
                ),
            )
            # 返回被更新任务的ID，用于判断更新是否成功。
            .returning(DocumentProcessingJob.id)
        )

        result = await self.session.execute(statement)

        updated_job_id = result.scalar_one_or_none()

        return updated_job_id is not None
