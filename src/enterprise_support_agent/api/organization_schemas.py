"""
organization_schemas.py

主要功能：
    定义组织接口接收和返回的数据格式。

主要部件：
    CreateOrganizationRequest：
        校验客户端创建组织时提交的数据。

    OrganizationResponse：
        规定接口返回给客户端的组织字段。
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateOrganizationRequest(BaseModel):
    """创建组织时，客户端需要提交的数据。"""

    # 组织名称长度必须在2到100之间。
    name: str = Field(
        min_length=2,
        max_length=100,
    )

    # 组织编码只允许使用小写字母、数字和中划线。
    # 例如：xinghe-tech
    code: str = Field(
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )


class OrganizationResponse(BaseModel):
    """返回给客户端的组织信息。"""

    # 允许Pydantic从SQLAlchemy模型对象的属性中读取字段。
    #
    # 例如从organization.id、organization.name中取值，
    # 不要求我们先手动把ORM对象转换成字典。
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    """组织分页列表的响应格式。"""

    # 当前页的组织数据。
    items: list[OrganizationResponse]

    # 数据库中符合条件的组织总数。
    total: int

    # 当前是第几页。
    page: int

    # 每页最多返回多少条数据。
    page_size: int

    # 一共有多少页。
    total_pages: int