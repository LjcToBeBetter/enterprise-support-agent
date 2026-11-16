# 企业支持 Agent 平台

个人后端项目，提供多组织知识库问答与工单协作，并包含 React 操作页面。

## 从哪里开始看

| 要找的内容 | 目录 |
| --- | --- |
| HTTP 接口、请求与响应格式、接口依赖 | `src/enterprise_support_agent/api/`，按业务分组 |
| Agent 编排、会话、摘要、工具、审批 | `src/enterprise_support_agent/application/agent/` |
| 检索、RRF、Rerank、RAG 问答 | `src/enterprise_support_agent/application/knowledge/` |
| 文档上传、切块、后台任务提交 | `src/enterprise_support_agent/application/documents/` |
| 用户、组织、成员与认证业务 | `src/enterprise_support_agent/application/identity/` |
| 工单业务 | `src/enterprise_support_agent/application/tickets/` |
| 数据库、Redis、RabbitMQ、Qdrant、RustFS、模型客户端 | `src/enterprise_support_agent/infrastructure/` |
| 文档任务消费者 | `src/enterprise_support_agent/workers/` |
| 手动检查脚本和初始化工具 | `src/enterprise_support_agent/scripts/`，按用途分组 |
| 检索评测程序与题集 | `src/enterprise_support_agent/evaluation/`、`evals/` |
| 前端页面与共享代码 | `frontend/src/` |

本次移动对照表和更详细的目录说明见 `docs/project_structure.md`。旧面试 PDF 中的路径属于整理前版本，查代码时请对照该表。

## 本地启动：在 PyCharm 中直接运行

先在 Docker Desktop 启动 PostgreSQL、RustFS、Qdrant、RabbitMQ 和 Redis。
使用本项目 `.venv` 解释器；前端另需已安装 Node.js 和 `frontend/node_modules`。
配置放在项目根目录 `.env`；可以参考 `.env.example` 的字段，不要提交真实密钥。
首次建库或新增迁移后，需要先执行 `uv run alembic upgrade head`。

依次打开以下文件，右键选择“运行”，并保留各自的运行窗口：

| 程序 | 文件路径（相对本项目根目录） | 用途 |
| --- | --- | --- |
| FastAPI 后端 | `src/enterprise_support_agent/main.py` | 普通 HTTP 接口，默认 8002 |
| MCP 服务 | `src/enterprise_support_agent/api/mcp/mcp_server.py` | 智能助手通过 MCP 检索资料，默认 8003，路径 `/mcp` |
| 文档 Worker | `src/enterprise_support_agent/workers/document_processing_worker.py` | 消费 RabbitMQ 文档任务；未运行时任务会等待 |
| 前端启动器 | `start_frontend.py` | 启动 Vite 并打开 `http://127.0.0.1:5173` |

前端启动器只负责前端；后端、MCP 和 Worker 是独立进程。开发时若已有相应服务，不要重复启动。
服务地址以 `.env` 和 MCP 启动文件为准。MCP 客户端的 `MCP_SERVER_URL` 需要与 MCP 服务监听地址一致。

## 核心调用链

- 文档处理：上传接口 → RustFS 保存原 PDF、PostgreSQL 保存元数据 → 提交任务 → RabbitMQ → Worker → 解析、切块、文本入库与 Qdrant 入库。
- 知识问答：HTTP 接口 → 检索服务 → 向量与 BM25 召回 → RRF → Rerank → 模型回答与引用编号检查；支持 SSE。
- 智能助手：HTTP 接口 → LangGraph 调度 → 知识库角色或工单角色；知识检索经 MCP 复用检索服务，创建工单需要审批。
- 会话：检查用户和组织归属 → 用会话 ID 作为 `thread_id` → PostgreSQL Checkpointer 读取、保存图状态。

## 测试与评测

```powershell
# 不调用真实模型的恢复、防重与审批测试。
uv run python -m unittest discover -s tests -p "test_agent_recovery.py"

# 目录调整前的Checkpoint类路径兼容测试。
uv run python -m unittest discover -s tests -p "test_checkpoint_compatibility.py"

# SSE 解析器测试与前端构建（在 frontend 目录中）。
npm.cmd test
npm.cmd run build

# 浏览器流程测试使用模拟接口（在 frontend 目录中）。
npm.cmd run test:e2e
```

`tests/test_ticket_recovery_postgres.py` 需要显式设置 `RUN_POSTGRES_RECOVERY_TESTS=1`，并连接本机 PostgreSQL；它使用临时表，不是普通离线单元测试。
检索评测会调用真实 Embedding／Rerank 服务，运行方式、60 道固定题的范围和指标解释见 `evals/README.md`。

## 文件管理约定

- `evals/corpus/`：检索评测使用的模拟 PDF 与资料清单，作为可复现输入保留。
- `output/reports/`：本地生成的面试复盘 PDF。
- `output/resumes/`：本地生成的个人简历。
- `tmp/`：临时构建、排版检查和本次整理前快照；不属于业务源码。
- `.env`、虚拟环境、依赖缓存、构建产物、`tmp/` 和 `output/` 不纳入 Git。

旧版手写 Agent 循环保留在 `application/agent/legacy/`；当前接口运行的是 `application/agent/langgraph_agent_service.py`。`application/agent_routing_schemas.py`仅保留旧Checkpoint类路径兼容，不是第二份业务实现。本次目录整理保留已有业务行为，不补加工单处理日志等新功能。
