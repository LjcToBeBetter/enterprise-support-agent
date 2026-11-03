"""
document_enums.py

主要功能：
    定义知识库文档允许使用的固定状态。

主要部件：
    DocumentStatus：
        表示文档从上传到可以检索的处理阶段。
"""

from enum import StrEnum


class DocumentStatus(StrEnum):
    """知识库文档处理状态。"""

    # 文件已经上传成功，
    # 正在等待后台任务解析。
    PENDING = "pending"

    # 后台任务正在读取、切块和向量化文档。
    PROCESSING = "processing"

    # 文档正文已经解析完成，
    # 但还没有完成切块和向量化。
    PARSED = "parsed"

    # 文档正文已经切块并保存到PostgreSQL，
    # 但还没有写入向量数据库。
    CHUNKED = "chunked"

    # 文档已经处理完成，可以参与知识库检索。
    READY = "ready"

    # 文档解析、切块或者向量化过程中发生错误。
    FAILED = "failed"