"""定义通过RabbitMQ传递的文档处理消息格式。"""

from uuid import UUID

# BaseModel负责校验字段类型。
# ConfigDict用于配置校验规则。
# Field用于给字段增加限制，例如数字不能小于1。
from pydantic import BaseModel, ConfigDict, Field


class DocumentProcessingMessage(BaseModel):
    """
    一条文档处理任务消息。
    后端按照这个格式组织消息；
    Worker收到消息后，也按照这个格式读取和校验。

    消息只携带任务和文档的定位信息。
    Worker根据这些信息查询数据库，再从RustFS读取文件。
    """

    # extra="forbid"表示禁止出现未声明的字段。
    #
    # 例如把document_id误写成document_ids，
    # 校验时会报错，便于及时发现字段拼写问题。
    model_config = ConfigDict(
        extra="forbid",
    )

    # 本次处理任务的ID。
    # 后面会新增任务表，用这个ID查询任务状态。
    #
    # 同一个任务因为发送失败而重新发送时，
    # 应继续使用原来的job_id。
    # 标识一次处理任务。同一份文档重新发起处理，可以产生新的任务 ID。
    job_id: UUID

    # 待处理文档所属的组织ID。
    organization_id: UUID

    # 待处理文档在knowledge_documents表中的ID。
    document_id: UUID

    # 本次任务要处理的文档版本。
    #
    # ge=1表示必须大于或等于1。
    # 没有设置默认值，所以创建消息时必须提供。
    document_version: int = Field(
        ge=1,
    )