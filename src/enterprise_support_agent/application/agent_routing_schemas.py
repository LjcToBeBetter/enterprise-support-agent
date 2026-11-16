"""兼容目录整理前保存的会话存档，不在这里定义新的业务模型。

旧Checkpoint会记录调度结果类的模块路径，反序列化时仍需导入本模块。
新代码应使用agent.routing.agent_routing_schemas中的正式定义。
"""

from enterprise_support_agent.application.agent.routing.agent_routing_schemas import (
    AgentRoutingDecision,
)

__all__ = ["AgentRoutingDecision"]
