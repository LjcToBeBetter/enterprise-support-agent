"""
文档文本块数据库模型。

一份知识库文档解析完成后，
会被切分成多个较小的文本块。

这些文本块会保存在document_chunks表中，
后面再根据每个文本块生成向量并写入Qdrant。
"""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from enterprise_support_agent.infrastructure.database.base import (
    Base,
)
from enterprise_support_agent.infrastructure.database.mixins import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class DocumentChunk(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """知识库文档切分后的一块正文。"""

    # 规定这个ORM模型对应的数据库表名。
    __tablename__ = "document_chunks"

    # 给整张表增加数据库约束。
    __table_args__ = (
        # 同一份文档、同一个版本中，
        # chunk_index不能重复。
        #
        # 例如一份文档不能同时存在两个“第0块”。
        UniqueConstraint(
            "document_id",
            "document_version",
            "chunk_index",
            name=(
                "uq_document_chunks_"
                "document_version_index"
            ),
        ),

        # PDF页码必须从1开始。
        CheckConstraint(
            "page_number >= 1",
            name=(
                "ck_document_chunks_"
                "page_number_positive"
            ),
        ),

        # 文本块编号从0开始，
        # 因此不能是负数。
        CheckConstraint(
            "chunk_index >= 0",
            name=(
                "ck_document_chunks_"
                "chunk_index_nonnegative"
            ),
        ),

        # 字符数量不能是负数。
        CheckConstraint(
            "character_count >= 0",
            name=(
                "ck_document_chunks_"
                "character_count_nonnegative"
            ),
        ),

        # Token数量不能是负数。
        CheckConstraint(
            "token_count >= 0",
            name=(
                "ck_document_chunks_"
                "token_count_nonnegative"
            ),
        ),
    )

    # 文本块属于哪个组织。
    #
    # 保存organization_id可以让后面查询时
    # 直接按照组织过滤，实现组织数据隔离。
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",

            # 删除组织时，
            # 同时删除这个组织的文本块。
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 文本块属于哪一份知识库文档。
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "knowledge_documents.id",

            # 删除原文档记录时，
            # 同时删除它的所有文本块。
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # 这块正文来自文档的哪个版本。
    #
    # 第一次上传的文档版本是1；
    # 文档更新后可以是2、3……
    document_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 这块正文主要来自PDF的第几页。
    #
    # 页码从1开始。
    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 这块正文在当前文档中的编号。
    #
    # 第一块是0，第二块是1，以此类推。
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 文本块的真正正文。
    #
    # Text适合保存长度不固定的长字符串。
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 这块正文包含多少个字符。
    #
    # 例如：
    # len(content)
    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 这块正文大约包含多少个Token。
    #
    # 后面切块时会使用Token计数器计算。
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 这块正文的SHA-256摘要。
    #
    # 相同正文会得到相同的content_hash，
    # 后面可用于检查重复块或内容是否发生变化。
    content_hash: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )