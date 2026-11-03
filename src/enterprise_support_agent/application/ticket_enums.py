"""
ticket_enums.py

主要功能：
    定义工单模块允许使用的固定值。

主要部件：
    TicketStatus：
        工单当前所处的处理阶段。

    TicketPriority：
        工单的紧急程度。
"""

from enum import StrEnum


class TicketStatus(StrEnum):
    """工单状态。"""

    # 工单已经创建，等待客服处理。
    OPEN = "open"

    # 已经有客服开始处理。
    IN_PROGRESS = "in_progress"

    # 问题已经解决，等待最终关闭。
    RESOLVED = "resolved"

    # 工单处理流程已经结束。
    CLOSED = "closed"


class TicketPriority(StrEnum):
    """工单优先级。"""

    # 影响较小，可以稍后处理。
    LOW = "low"

    # 普通问题，默认优先级。
    MEDIUM = "medium"

    # 影响较大，需要优先处理。
    HIGH = "high"

    # 严重影响业务，需要立即处理。
    URGENT = "urgent"