"""
organization_roles.py

主要功能：
    集中定义系统支持的组织成员角色。

主要部件：
    OrganizationRole：
        employee：普通员工；
        support：客服人员；
        admin：组织管理员。
"""

from enum import StrEnum


# StrEnum 是 Python提供的字符串枚举。
#
# 它表示这些角色只能从固定选项中选择：
# OrganizationRole.EMPLOYEE
# OrganizationRole.SUPPORT
# OrganizationRole.ADMIN
# 同时它们又可以当成字符串使用：
# OrganizationRole.ADMIN == "admin"
class OrganizationRole(StrEnum):
    """系统支持的组织角色。"""

    EMPLOYEE = "employee"
    SUPPORT = "support"
    ADMIN = "admin"