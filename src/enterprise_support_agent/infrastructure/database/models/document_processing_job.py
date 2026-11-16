"""
定义文档处理任务的数据库表模型。
这里指的是：在现有的 PostgreSQL 数据库中，新增一张“任务记录表”。

比如你点击“处理文档”，要求对 排查手册.pdf 进行解析、切块、向量化，这就产生了一次任务。

表里记录这次任务的情况：
- 任务 ID 是多少。
- 要处理哪份文档。
- 谁提交的。
- 是等待执行、正在执行，还是成功、失败。
- 失败的话，原因是什么。

RabbitMQ 保存消息，让任务排队；任务表保存执行情况，让前端能查询进度和结果。
例如消息处理成功后会从队列移除，但任务表仍然保留“这个任务已经成功”的记录。
"""

from uuid import UUID

# datetime：Python中的日期时间类型。
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    DateTime
)
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_support_agent.application.documents.document_enums import (
    DocumentJobStatus,
)
from enterprise_support_agent.infrastructure.database.base import (
    Base,
)
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class DocumentProcessingJob(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    一条记录代表一次文档处理任务。

    同一份文档可以先后产生多次处理任务，
    每次任务都有自己的ID、状态和执行结果。
    """

    __tablename__ = "document_processing_jobs"

    # 数据库约束：任务对应的文档版本必须从1开始。
    __table_args__ = (
        # 文档版本必须从1开始。
        CheckConstraint(
            "document_version >= 1",
            name="ck_document_processing_jobs_version_positive",
        ),

        # 已执行次数不能为负数。
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_document_processing_jobs_attempts_nonnegative",
        ),

        # 至少允许执行一次。
        CheckConstraint(
            "max_attempts >= 1",
            name="ck_document_processing_jobs_max_attempts_positive",
        ),

        # 已执行次数不能超过次数上限。
        CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_document_processing_jobs_attempts_within_limit",
        ),
    )

    # id由UUIDPrimaryKeyMixin提供。
    #
    # 插入记录且未指定id时，
    # SQLAlchemy会调用uuid4()生成任务ID。
    #
    # 后面消息中的job_id，就使用这条记录的id。

    # 任务属于哪个组织。
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",

            # 删除组织时，同时删除该组织的任务记录。
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 本次任务要处理哪份文档。
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "knowledge_documents.id",

            # 删除文档时，同时删除它的任务记录。
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 本次任务要处理的文档版本。
    # 创建任务时，从文档记录中读取这个值。
    document_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 哪个用户提交了这次任务。
    # 后面由后端根据当前登录用户填写。
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",

            # 用户仍有关联任务记录时，阻止直接删除该用户。
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # 本次任务的执行状态。
    # 新任务默认为pending，等待发送任务消息。
    status: Mapped[str] = mapped_column(
        String(30),
        default=DocumentJobStatus.PENDING.value,
        server_default=DocumentJobStatus.PENDING.value,
        index=True,
        nullable=False,
    )

    # 任务失败时保存简短原因。
    # 正常情况下可以为空。
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # created_at和updated_at由TimestampMixin提供。

    # 本次任务已经开始执行了多少次。
    # 新任务是0，Worker每开始执行一次，后面会通过代码加1。
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    # 本次任务最多允许执行多少次。
    #
    # 3次包含第一次执行，
    # 因此最多允许在首次失败后再重试2次。
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
        nullable=False,
    )

    # 任务第一次开始执行的时间。
    # 新任务还没有开始，所以允许为空。
    # 后面由Worker填写，重试时保留第一次的时间。
    started_at: Mapped[datetime | None] = mapped_column(
        # timezone=True表示保存带时区的时间。
        DateTime(timezone=True),
        nullable=True,
    )

    # 任务最终结束的时间。
    # 成功或最终失败时填写；等待执行、等待重试时为空。
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


    # 当前这一次执行的唯一编号。
    #
    # 同一个任务重试时，会生成新的执行编号。
    # 后续更新任务状态时，需要核对这个编号，
    # 避免上一次执行的Worker覆盖新一轮执行的状态。
    execution_token: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


    # Worker 处理到一半意外退出，任务记录可能一直停在 running，重启后也无法重新领取。
    #
    # 我们给任务增加一个“执行资格的有效期”，叫租约：Worker 正常工作时定期延长它；过期后，才允许重新领取任务。

    # 当前执行资格的到期时间，也叫“租约到期时间”。
    #
    # Worker正常处理时，定期把这个时间往后延长。
    # 如果Worker意外退出，不再延长，
    # 到期后就可以根据后续恢复逻辑重新领取任务。
    #
    # 任务尚未开始时，这个字段为空。
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,

        # 后面需要按到期时间查找任务，所以建立索引。
        index=True,
    )
