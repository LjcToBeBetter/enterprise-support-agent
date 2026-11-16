"""验证移动模块后，目录整理前的调度状态仍可从Checkpoint恢复。"""

import unittest

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from enterprise_support_agent.application.agent.routing.agent_routing_schemas import (
    AgentRoutingDecision,
)


class CheckpointCompatibilityTests(unittest.TestCase):
    """真实序列化和反序列化，不连接数据库或调用模型。"""

    def test_old_routing_module_restores_to_current_model(self):
        """模拟旧类路径写入的存档，读取后必须得到当前正式模型。"""
        legacy_type = type(
            "AgentRoutingDecision",
            (BaseModel,),
            {
                "__module__": "enterprise_support_agent.application.agent_routing_schemas",
                "__annotations__": {"route": str},
            },
        )
        serializer = JsonPlusSerializer()
        saved = serializer.dumps_typed(
            {"routing_decision": legacy_type(route="knowledge_then_ticket")}
        )

        restored = serializer.loads_typed(saved)

        self.assertIsInstance(restored["routing_decision"], AgentRoutingDecision)
        self.assertEqual(restored["routing_decision"].route, "knowledge_then_ticket")


if __name__ == "__main__":
    unittest.main()
