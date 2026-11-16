"""
Agent执行工具时使用的身份信息。

后端验证JWT和组织成员身份后，
创建这个对象，交给工具使用。

模型只填写查询条件等业务参数，
不能自行选择当前用户和组织。
"""

from dataclasses import dataclass
from uuid import UUID


# dataclass自动生成构造方法，
# 不需要手写__init__来保存这两个字段。
#
# frozen=True：
# 创建后禁止直接修改字段，
# 避免执行过程中意外换了用户或组织。
#
# slots=True：
# 限定实例使用声明的字段，
# 避免随意添加其他属性。
@dataclass(
    frozen=True,
    slots=True,
)
class AgentContext:
    """保存本次Agent请求的用户和组织身份。"""

    # 从请求URL中取得，
    # 并且已经检查过当前用户属于这个组织。
    organization_id: UUID

    # 从JWT对应的数据库用户记录中取得，
    # 不接受模型提供的用户ID。
    current_user_id: UUID

    # 本次请求是否允许使用创建工单工具。
    # 默认关闭，由后端从请求设置中读取，
    # 不作为模型填写的工具参数。
    allow_ticket_creation: bool = False