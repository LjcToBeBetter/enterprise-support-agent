"""
models包的统一入口。

主要功能：
    集中导入项目中的所有数据库表模型。
    这样其他文件使用数据表模型的时候就不用分别导入这三个模型，而是直接导入:
    import enterprise_support_agent.infrastructure.database.models
    Python规定：导入一个包时，会自动执行这个包中的__init__.py文件
为什么需要：
    Python只有执行模型文件后，
    SQLAlchemy才会把对应表结构登记到Base.metadata。

    后面Alembic只需要导入当前models包，
    就能加载这里列出的所有表模型。
"""

from enterprise_support_agent.infrastructure.database.models.organization import (
    Organization,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.models.ticket import (
    Ticket,
)
from enterprise_support_agent.infrastructure.database.models.knowledge_document import (
    KnowledgeDocument,
)
# 导入文档文本块ORM模型。
#
# 导入这个模块时，Python会执行document_chunk.py，
# SQLAlchemy便会把document_chunks表结构
# 登记到Base.metadata中。
from enterprise_support_agent.infrastructure.database.models.document_chunk import (
    DocumentChunk,
)

from enterprise_support_agent.infrastructure.database.models.agent_conversation import (
    AgentConversation,
)
# 导入任务模型，让SQLAlchemy把表结构登记到Base.metadata。
# Alembic才能读取到这张新表的定义。
from enterprise_support_agent.infrastructure.database.models.document_processing_job import (
    DocumentProcessingJob,
)

# __all__表示：
# 当外部模块从当前models包导入内容时，
# 这些是当前包明确对外提供的模型名称。
# 这一步不会创建数据库表，它只是确保三个模型文件都会被执行，从而把表结构登记到：
# Base.metadata
__all__ = [
    "Organization",
    "OrganizationMembership",
    "User",
    "Ticket",
    "KnowledgeDocument",
    "DocumentChunk",
    "AgentConversation",
    "DocumentProcessingJob"
]