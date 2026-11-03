"""
user_schemas.py

主要功能：
    定义创建用户时的请求格式和用户响应格式。

主要部件：
    CreateUserRequest：
        校验邮箱、姓名和明文密码。

    UserResponse：
        返回可以公开的用户信息，
        不包含password和password_hash。
"""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
)


class CreateUserRequest(BaseModel):
    """创建用户时客户端提交的数据。"""

    # EmailStr会校验输入是否符合邮箱格式。
    email: EmailStr

    display_name: str = Field(
        min_length=2,
        max_length=100,
    )

    # SecretStr会在打印和日志中隐藏密码内容，
    # 减少明文密码被意外记录的风险。
    password: SecretStr = Field(
        min_length=8,
        max_length=128,
    )


class UserResponse(BaseModel):
    """可以安全返回给客户端的用户信息。"""

    # 允许从SQLAlchemy User对象的属性中读取字段。
    # SQLAlchemy查询得到的是一个User对象，但Pydantic默认更擅长接收字典：
    # 这个设置就是告诉Pydantic：
    # 如果传入的不是字典，而是Python对象，
    # 就从对象的属性中读取字段。
    # UserResponse.model_validate(user)时生效，他会读取UserResponse里的配置
    # 发现from_attributes=T
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class UserListResponse(BaseModel):
    """用户分页查询的响应格式。"""

    # 当前页的用户列表。
    items: list[UserResponse]

    # 数据库中的用户总数量。
    total: int

    # 当前页码。
    page: int

    # 每页最多返回多少条。
    page_size: int

    # 一共有多少页。
    total_pages: int