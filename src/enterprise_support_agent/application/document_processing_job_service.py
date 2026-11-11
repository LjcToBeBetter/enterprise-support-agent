"""组织文档处理任务的提交、投递和查询流程。"""

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.infrastructure.database.repositories.document_processing_job_repository import (
    DocumentProcessingJobRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.document_repository import (
    DocumentRepository,
)
from enterprise_support_agent.infrastructure.database.repositories.membership_repository import (
    MembershipRepository,
)

from uuid import UUID

from enterprise_support_agent.application.exceptions import (
    DocumentNotFoundError,
    OrganizationAccessDeniedError,
)
from enterprise_support_agent.application.organization_roles import (
    OrganizationRole,
)
from enterprise_support_agent.infrastructure.database.models.document_processing_job import (
    DocumentProcessingJob,
)
from aio_pika.abc import AbstractRobustConnection
from enterprise_support_agent.infrastructure.messaging.document_task_message import (
    DocumentProcessingMessage,
)
from enterprise_support_agent.infrastructure.messaging.document_task_publisher import (
    publish_document_processing_message,
)
from enterprise_support_agent.application.exceptions import (
    DocumentProcessingJobNotFoundError,
)
from enterprise_support_agent.application.document_enums import (
    DocumentJobStatus,
)


class DocumentProcessingJobService:
    """协调文档处理任务的业务流程。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        保存数据库Session，创建业务需要的Repository对象。

        三个Repository共用同一个Session，
        后面由Service统一决定何时提交或回滚事务。
        """

        self.session = session

        # 查询当前用户在组织中的成员关系和角色，
        # 后面用来判断是否有权提交文档处理任务。
        self.membership_repository = MembershipRepository(
            session=session,
        )

        # 查询文档是否存在、属于哪个组织、当前版本是多少。
        self.document_repository = DocumentRepository(
            session=session,
        )

        # 创建、查询任务记录，以及更新任务状态。
        self.job_repository = DocumentProcessingJobRepository(
            session=session,
        )

    async def create_job(
        self,
        organization_id: UUID,
        document_id: UUID,
        current_user_id: UUID,
    ) -> DocumentProcessingJob:
        """
        校验权限和文档归属，保存一条待发送的任务记录。

        organization_id：当前组织ID。
        document_id：需要处理的文档ID。
        current_user_id：后端验证登录后取得的当前用户ID。

        只有当前组织的管理员可以提交。
        返回已提交到数据库的任务ORM对象，状态为pending。
        """

        # 查询当前用户在这个组织中的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 不属于这个组织，或者不是组织管理员，
        # 都不能提交文档处理任务。
        if (
            membership is None
            or membership.role != OrganizationRole.ADMIN
        ):
            raise OrganizationAccessDeniedError(
                organization_id=organization_id,
            )

        # 同时按照组织ID和文档ID查询。
        # 确保这份文档属于当前组织。
        document = (
            await self.document_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                document_id=document_id,
            )
        )

        if document is None:
            raise DocumentNotFoundError(
                organization_id=organization_id,
                document_id=document_id,
            )

        try:
            # 使用数据库中的文档ID和版本创建任务。
            # Repository会执行INSERT，并取得生成的任务ID。
            job = await self.job_repository.create(
                organization_id=organization_id,
                document_id=document.id,
                document_version=document.version,
                requested_by_user_id=current_user_id,
            )

            # 正式提交任务记录。
            # 提交后，其他数据库连接才能查询到这个任务。
            await self.session.commit()

        except Exception:
            # 创建或提交失败时，撤销尚未提交的数据库修改，
            # 并把异常继续交给上层处理。
            await self.session.rollback()
            raise

        # 返回任务对象。
        # job.id就是后面消息中要使用的job_id。
        return job

    async def submit_job(
        self,
        organization_id: UUID,
        document_id: UUID,
        current_user_id: UUID,
        connection: AbstractRobustConnection,
    ) -> DocumentProcessingJob:
        """
        完成一次文档处理任务的提交。

        先检查权限并保存任务记录，
        再发送消息、更新排队状态，
        最后返回任务对象。
        """

        # 第一步：检查权限和文档归属，
        # 创建任务记录，并提交到PostgreSQL。
        job = await self.create_job(
            organization_id=organization_id,
            document_id=document_id,
            current_user_id=current_user_id,
        )

        # 第二步：使用任务记录构造并发送消息，
        # 更新状态，返回刷新后的任务对象。
        return await self.publish_job(
            job=job,
            connection=connection,
        )


    async def publish_job(
        self,
        job: DocumentProcessingJob,
        connection: AbstractRobustConnection,
    ) -> DocumentProcessingJob:
        """
        将已经保存的任务发送给RabbitMQ，
        再更新排队状态，返回刷新后的任务对象。
        """

        # 从数据库任务记录中读取信息，构造消息。
        # 消息的job_id和任务记录的id使用同一个编号。
        task_message = DocumentProcessingMessage(
            job_id=job.id,
            organization_id=job.organization_id,
            document_id=job.document_id,
            document_version=job.document_version,
        )

        try:
            # 调用之前写好的发送方法。
            # 等待RabbitMQ确认接收消息。
            await publish_document_processing_message(
                connection=connection,
                task_message=task_message,
            )

            # 仅将仍处于pending的任务改成queued。
            # 如果Worker已开始执行，就保留它更新后的状态。
            await self.job_repository.mark_queued(
                organization_id=task_message.organization_id,
                job_id=task_message.job_id,
            )

            # 提交状态更新。
            await self.session.commit()

            # 从数据库读取任务最新状态。
            await self.session.refresh(job)

        except Exception:
            # 回滚当前尚未提交的数据库修改。
            # 之前已提交的任务记录仍然保留；
            # 已发送给RabbitMQ的消息也不会因此撤回。
            await self.session.rollback()
            raise

        return job


    async def get_job(
        self,
        organization_id: UUID,
        job_id: UUID,
        current_user_id: UUID,
    ) -> DocumentProcessingJob:
        """
        查询当前组织中的指定文档处理任务。

        只有这个组织的管理员可以查询。
        返回任务记录，其中包含状态、尝试次数和失败原因。
        """

        # 查询当前用户在指定组织中的成员关系。
        membership = (
            await self.membership_repository
            .get_by_organization_and_user(
                organization_id=organization_id,
                user_id=current_user_id,
            )
        )

        # 用户必须属于这个组织，并且是管理员。
        if (
            membership is None
            or membership.role != OrganizationRole.ADMIN
        ):
            raise OrganizationAccessDeniedError(
                organization_id=organization_id,
            )

        # 按组织ID和任务ID一起查询，
        # 确保只能取得当前组织中的任务。
        job = (
            await self.job_repository
            .get_by_id_and_organization(
                organization_id=organization_id,
                job_id=job_id,
            )
        )

        # 没找到任务，就抛出上一步定义的异常。
        if job is None:
            raise DocumentProcessingJobNotFoundError(
                job_id=job_id,
            )

        # 返回数据库中的任务ORM对象。
        # 这里只执行查询，因此不需要commit。
        return job

    async def retry_publish_job(
        self,
        organization_id: UUID,
        job_id: UUID,
        current_user_id: UUID,
        connection: AbstractRobustConnection,
    ) -> DocumentProcessingJob:
        """
        重新发送仍处于pending状态的任务消息。

        使用已有任务记录和任务ID，不创建新任务。
        只有当前组织的管理员可以操作。
        """

        # 复用查询方法：
        # 检查管理员权限，并查询指定组织中的任务。
        job = await self.get_job(
            organization_id=organization_id,
            job_id=job_id,
            current_user_id=current_user_id,
        )

        # 只重新发送pending任务。
        # 如果任务已经排队、正在执行或已经结束，
        # 就直接返回当前任务信息。
        if job.status != DocumentJobStatus.PENDING.value:
            return job

        # 复用原来的发送方法：
        # 构造消息 → 发送给RabbitMQ → 更新数据库状态。
        return await self.publish_job(
            job=job,
            connection=connection,
        )