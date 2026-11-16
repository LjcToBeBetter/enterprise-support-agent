# 项目问题记录

## 2026-11-08：多 Agent 协作中，知识库角色误调用创建工单工具

状态：已定位并实施改进；用户已展示一例成功进入审批、同意后恢复并返回创建成功的接口结果，完整回归尚未完成。

### 2026-11-08 测试进展

- 一次后续测试截图中请求的allow_ticket_creation实际为false，因此没有提供创建工具。此处是本次开关限制生效，不能归因于模型或工具配置错误，也不能据此断言所有早期失败都是该原因。
- 将开关改为true后，用户截图显示status为awaiting_approval，待审批工具为create_ticket，工单标题、描述和high优先级完整。
- 用户提交同意后，接口返回completed、真实工单编号、open状态、high优先级，pending_approval为null，tool_call_count为2。
- 以上是接口层单次成功证据。尚未独立查询工单表核对该记录；尚未完成修复后的拒绝审批、重复审批、强制越界调用以及混合路线重复运行等回归。
- 不能用这一次成功计算准确率，或宣称模型越界调用问题已彻底消除。

### 首步修改

工具节点接收knowledge或ticket角色。知识库误调用工单工具时，返回TOOL_NOT_AVAILABLE_FOR_ROLE，明确要求完成知识库回答后由程序交接，不再笼统声称系统不存在该工具。工单节点未获得创建工具时，单独说明本次创建能力未开放。继续保留工具白名单、ToolMessage与调用编号配对、执行次数限制和人工审批。该修改不能保证模型一定纠正，仍需验证实际交接行为。

### 场景与现象

用户要求先检索 E1007 数据库连接超时的排查资料，再创建高优先级排查工单。调度选择 `knowledge_then_ticket`。在后续补充工单信息的测试中，响应为 `completed`，模型说明创建工具不存在，没有返回待审批信息，也没有创建工单。

首步错误反馈调整后，用户反馈新会话仍返回“未提供create_ticket”的文字回答，未进入审批。因此不能认为单靠错误反馈已经修复。后续增加角色模型的运行时阶段说明和实际工具名称，明确知识库阶段完成后交接、工单阶段根据自己的实际工具执行；同时调整角色和调度提示词。真实模型回归仍待完成，不能仅凭模型的文字说明判断后端是否提供了工具。

### 已确认的执行过程

只读检查测试会话存档，确认路线为 `knowledge_then_ticket`，历史中先出现 `search_knowledge` 成功结果，随后出现工具名为 `create_ticket` 的调用和 `UNKNOWN_TOOL` 结果。任务写入记录包含 `knowledge_tools`，未出现 `ticket_tools` 的执行结果。

结合图和节点配置，执行过程为：

1. 知识库模型请求检索，知识库工具节点返回资料。
2. 模型读到检索结果后，没有先完成知识库阶段，而是提出创建工单调用。
3. `choose_after_knowledge()` 只判断是否存在工具调用，将它交给知识库工具节点，没有按工具名称自动跨角色转发。
4. 知识库工具节点仅持有 `search_knowledge`，查找 `create_ticket` 得到 `None`，返回 `UNKNOWN_TOOL`。
5. 失败结果写入共享消息，后续模型把角色内不可用理解为整个系统不可用，最终没有进入创建审批。

工具名称本身正确，问题在于提出调用的角色不正确。工具隔离阻止了知识库角色执行写操作，不应通过向知识库角色开放创建工具来绕过问题。

### 相关代码

- `src/enterprise_support_agent/application/agent/agent_graph.py`：角色节点、条件边和交接路线。
- `src/enterprise_support_agent/application/agent/nodes/agent_model_node.py`：调用模型，以及知识库回答转为中间结果的逻辑。
- `src/enterprise_support_agent/application/agent/tools/agent_tool_groups.py`：各角色的工具范围。
- `src/enterprise_support_agent/application/agent/nodes/agent_tool_node.py`：工具查找、执行和错误结果。
- `src/enterprise_support_agent/application/agent/prompts/agent_routing_prompt.py`：根据当前问题和历史选择路线。
- `src/enterprise_support_agent/application/agent/prompts/knowledge_agent_prompt.py`、`ticket_agent_prompt.py`：角色职责与交接说明。

### 修复方向（尚未验证）

- 调度优先识别本轮需求，避免把已完成的历史查询再次安排执行。
- 知识库角色明确只完成知识检索阶段，工单角色接手剩余任务。
- 后端检查模型提出的工具是否属于当前角色，不能只依赖提示词和模型工具绑定。
- 越界调用应配对返回明确的工具错误，保留 AI 工具调用与 ToolMessage 的对应关系；再通过受控纠正或交接处理，避免直接丢弃调用或擅自执行写操作。
- 保留组织权限、创建开关、人工审批以及调用次数保护。

### 待验证

知识库检索、直接创建工单、知识库后创建工单、审批同意与拒绝、无创建权限、模型越界调用、修正失败后的有界退出。修复完成后补充实际结果，不编造成功率和性能提升数据。

### 项目介绍可用的表述

多 Agent 拆分后发现，模型仍可能输出不属于当前角色的工具调用。通过检查会话存档和任务节点记录，定位到知识库角色提前请求创建工单。该案例说明：模型提示词和工具声明不能替代后端权限边界；角色交接还需要明确的数据协议和异常处理。具体修复方案及效果应在实现和验证后再补充。
