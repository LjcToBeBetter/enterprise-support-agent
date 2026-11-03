"""
membership_schemas.py

主要功能：
    定义用户加入组织时的请求和响应格式。

主要部件：
    AddOrganizationMemberRequest：
        指定要加入组织的用户和角色。

    OrganizationMembershipResponse：
        返回创建完成的组织成员关系。
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from enterprise_support_agent.application.organization_roles import (
    OrganizationRole,
)


class AddOrganizationMemberRequest(BaseModel):
    """把用户加入组织时提交的数据。"""

    # 要加入当前组织的用户ID。
    user_id: UUID

    # Literal限制role只能是下面三个固定字符串之一。
    # role: Literal[
    #     "employee",
    #     "support",
    #     "admin",
    # ] = "employee"

    # 等同于上面
    role: OrganizationRole = (
        OrganizationRole.EMPLOYEE
    )

class OrganizationMembershipResponse(BaseModel):
    """组织成员关系的响应格式。"""
    # 限制用户加入组织成功后，后端返回给客户端的数据格式

    # 允许从SQLAlchemy ORM对象属性中读取字段。
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: OrganizationRole
    created_at: datetime
    updated_at: datetime


class UpdateOrganizationMemberRoleRequest(
    BaseModel
):
    """修改组织成员角色的请求格式。"""

    # role: Literal[
    #     "employee",
    #     "support",
    #     "admin",
    # ]
    # 限制role只能是OrganizationRole中提供的
    role: OrganizationRole