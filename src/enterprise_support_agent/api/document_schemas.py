"""
document_schemas.py

主要功能：
    定义知识库文档接口返回的数据格式。

主要部件：
    DocumentResponse：
        单个知识库文档的响应格式。

    DocumentListResponse：
        文档分页列表的响应格式。
"""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
)

from enterprise_support_agent.application.document_enums import (
    DocumentStatus,
)
from enterprise_support_agent.application.document_enums import (
    DocumentJobStatus,
    DocumentStatus,
)

class DocumentResponse(BaseModel):
    """单个知识库文档的响应格式。"""

    # 允许Pydantic从KnowledgeDocument ORM对象
    # 的属性中读取字段。
    model_config = ConfigDict(
        from_attributes=True
    )

    # 文档元数据记录ID。
    id: UUID

    # 文档属于哪个组织。
    organization_id: UUID

    # 上传文档的用户ID。
    uploaded_by_user_id: UUID

    # 用户上传时的原始文件名。
    original_filename: str

    # 文件的MIME类型。
    content_type: str

    # 文件大小，单位为字节。
    file_size_bytes: int

    # 文件内容的SHA-256摘要。
    checksum_sha256: str

    # 当前文档处理状态。
    status: DocumentStatus

    # 当前文档版本号。
    version: int

    # 处理失败时的错误信息。
    error_message: str | None

    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """知识库文档分页列表的响应格式。"""

    # 当前页的文档数据。
    items: list[DocumentResponse]

    # 当前组织中的文档总数。
    total: int

    # 当前页码。
    page: int

    # 每页最多返回多少条。
    page_size: int

    # 总页数。
    total_pages: int


class DocumentProcessingJobResponse(BaseModel):
    """返回一次文档处理任务的信息，供前端展示进度和结果。"""

    # 允许直接从DocumentProcessingJob ORM对象读取属性。
    model_config = ConfigDict(
        from_attributes=True,
    )

    # 任务ID，对应RabbitMQ消息中的job_id。
    id: UUID

    # 任务所属组织。
    organization_id: UUID

    # 本次任务处理的文档。
    document_id: UUID

    # 本次任务处理的文档版本。
    document_version: int

    # 提交任务的用户。
    requested_by_user_id: UUID

    # 任务状态：pending、queued、running、
    # succeeded或failed。
    status: DocumentJobStatus

    # 已经开始执行了多少次。
    attempt_count: int

    # 最多允许执行多少次，包含首次执行。
    max_attempts: int

    # 失败原因，正常情况下可以为空。
    error_message: str | None

    # 第一次开始执行的时间，尚未开始时为空。
    started_at: datetime | None

    # 最终结束的时间，尚未结束时为空。
    finished_at: datetime | None

    # 任务记录的创建时间和最后更新时间。
    created_at: datetime
    updated_at: datetime