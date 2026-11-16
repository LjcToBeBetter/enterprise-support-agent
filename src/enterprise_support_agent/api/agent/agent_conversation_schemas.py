"""
Agent会话接口的数据格式。

CreateAgentConversationRequest：
    前端创建会话时提交的数据。

AgentConversationResponse：
    返回给前端的会话归属信息。
"""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class CreateAgentConversationRequest(BaseModel):
    """创建会话时接收的请求体。"""

    model_config = ConfigDict(
        # 禁止额外指定user_id、organization_id等字段。
        extra="forbid",

        # 自动去掉标题首尾空白，再检查长度。
        str_strip_whitespace=True,
    )

    # 用户没有填写标题时，默认使用“新会话”。
    title: str = Field(
        default="新会话",
        min_length=1,
        max_length=200,
        description="会话标题，用于会话列表展示",
    )


class AgentConversationResponse(BaseModel):
    """返回一段会话的归属信息，不包含聊天消息。"""

    # 允许model_validate()从ORM对象的属性中读取字段。
    #
    # 例如从conversation.id中读取id，
    # 而不是要求输入必须是字典。
    model_config = ConfigDict(
        from_attributes=True,
    )

    # 会话ID。
    # 后面使用它的字符串形式作为LangGraph的thread_id。
    id: UUID

    # 这段会话属于哪个组织、哪个用户。
    organization_id: UUID
    user_id: UUID

    title: str

    created_at: datetime
    updated_at: datetime