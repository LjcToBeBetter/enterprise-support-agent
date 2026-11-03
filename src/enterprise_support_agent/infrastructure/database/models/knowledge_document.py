"""
knowledge_document.py

主要功能：
    定义企业知识库文档对应的数据库表模型。

主要部件：
    KnowledgeDocument：
        对应knowledge_documents表；
        保存文档所属组织、上传者、文件信息、
        对象存储位置、版本和处理状态。

注意：
    PostgreSQL只保存文档元数据，即文档名称、大小、上传者、状态等信息
    PDF、Word等文件本身后面保存到MinIO。
"""

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_support_agent.application.document_enums import (
    DocumentStatus,
)
from enterprise_support_agent.infrastructure.database.base import (
    Base,
)
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class KnowledgeDocument(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """企业知识库文档的数据库模型。"""

    __tablename__ = "knowledge_documents"

    # 给整张表增加额外约束。
    # CheckConstraint 是数据库的“条件约束”。
    # 它的作用是：
    # 要写进数据库的数据，必须满足指定条件，否则 PostgreSQL拒绝保存
    __table_args__ = (
        # 文件大小不能小于0。
        CheckConstraint(
            "file_size_bytes >= 0",
            name=(
                "ck_knowledge_documents_"
                "file_size_nonnegative"
            ),
        ),

        # 文档版本号必须从1开始。
        CheckConstraint(
            "version >= 1",
            name=(
                "ck_knowledge_documents_"
                "version_positive"
            ),
        ),
    )

    # 文档属于哪个企业组织。
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",

            # 删除组织时，
            # 同时删除该组织的文档元数据。
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 哪个用户上传了文档。
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",

            # 文档仍然存在时，
            # 不允许直接删除上传者记录。
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
    )

    # 用户上传时使用的原始文件名。
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 文件的MIME类型。
    #
    # 例如：
    # application/pdf
    # text/plain
    # application/vnd.openxmlformats-officedocument
    # .wordprocessingml.document
    content_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # 文件大小，单位是字节。
    #
    # BigInteger可以保存较大的文件尺寸。
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # 文件在S3兼容对象存储中的位置。
    #
    # 本地开发环境使用RustFS，
    # 将来可以替换成AWS S3、阿里云OSS等对象存储服务。
    #
    # 例如：
    # organization-id/document-id/manual.pdf
    #
    # 对象存储可以理解成：
    # 专门保存文件的“企业网盘后端”。
    #
    # 它不是关系型数据库，主要保存：
    # PDF、Word、图片、音频、视频和压缩包等文件。
    #
    # PostgreSQL更适合保存结构化的管理信息：
    # 文档ID、文件名、上传者、文件大小、
    # 处理状态、对象地址和创建时间。
    #
    # RustFS更适合保存真正的文件内容。
    object_key: Mapped[str] = mapped_column(
        String(500),

        # 每个对象存储地址必须唯一。
        unique=True,
        index=True,
        nullable=False,
    )

    # 文件内容的SHA-256摘要：根据文件内容计算出来的“文件指纹”，SHA-256结果固定是：64个十六进制字符
    #同一个文件每次计算结果都一样，但是哪怕文件改了一个字，结果也完全不同
    # 后面可以用它判断文件内容是否发生变化，
    # 或者检查是否重复上传了完全相同的文件。
    checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    # 文档当前处理状态。
    status: Mapped[str] = mapped_column(
        String(30),
        default=DocumentStatus.PENDING.value,
        server_default=DocumentStatus.PENDING.value,
        index=True,
        nullable=False,
    )

    # 当前文档版本号。
    #
    # 第一次上传为1；
    # 后面更新文档时可以递增为2、3……
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )

    # 文档处理失败时保存简短错误信息。
    #
    # 正常状态下为空。
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )