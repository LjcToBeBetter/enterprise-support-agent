# 项目目录与路径对照

本次只调整文件位置和引用，不改接口URL、数据库表结构、模型配置及业务规则。
原文件内容快照位于本地 `tmp/directory_refactor_snapshot/`，该目录已被Git忽略。

## 后端按什么规则找文件

```text
src/enterprise_support_agent/
├─ api/                     HTTP与MCP入口
│  ├─ agent/                助手、会话、审批响应和相关接口依赖
│  ├─ auth/                 登录、令牌和身份依赖
│  ├─ organizations/        组织、成员、组织权限依赖
│  ├─ users/                用户接口
│  ├─ tickets/              工单接口
│  ├─ documents/            上传、下载、处理任务接口
│  ├─ knowledge/            检索和流式/非流式问答接口
│  ├─ mcp/                  MCP服务、令牌验证和MCP身份依赖
│  └─ common/               健康检查、错误处理和SSE编码
├─ application/             业务流程
│  ├─ agent/
│  │  ├─ agent_graph.py     组装节点和边
│  │  ├─ langgraph_agent_service.py  会话检查、执行与恢复
│  │  ├─ nodes/             模型、工具、路由和上下文节点
│  │  ├─ routing/           调度模型与结构化路线定义
│  │  ├─ memory/            会话、历史切分/摘要/删除与Token估算
│  │  ├─ tools/             业务工具、工具权限分组和审批辅助逻辑
│  │  ├─ prompts/           各角色的提示词
│  │  └─ legacy/            保留早期手写Agent循环，非当前HTTP执行入口
│  ├─ knowledge/            检索、RRF、Rerank接口、RAG和引用检查
│  ├─ documents/            文档服务、切块、处理任务提交
│  ├─ tickets/              工单服务、状态与优先级枚举
│  ├─ identity/             用户、认证、组织和成员业务
│  └─ common/               共享业务异常
├─ infrastructure/          已按技术分组；新增mcp目录收纳MCP客户端
├─ workers/                 RabbitMQ消费者；启动文件未移动
├─ evaluation/              检索指标与对照评测；入口未移动
├─ scripts/                 手动检查和初始化脚本
│  ├─ connections/          数据库、Qdrant、MCP连通性
│  ├─ knowledge/            PDF、BM25、混合检索、RAG流、引用检查
│  ├─ models/               Embedding、聊天流、Rerank检查
│  ├─ agent/                工具选择和知识工具检查
│  ├─ messaging/            RabbitMQ连接、拓扑、发送和消费
│  ├─ cache/                Redis连接和限流检查
│  └─ setup/                Collection与Checkpoint表初始化
├─ security/                密码和JWT令牌
├─ main.py                  普通后端启动入口，未移动
└─ lifespan.py              共享连接生命周期，未移动
```

`application/agent_routing_schemas.py`仅为旧Checkpoint保留调度模型的导入兼容入口；它不重复实现业务模型，新代码全部使用新路径。不要直接删除此兼容文件，否则旧会话中的调度结果可能无法反序列化。
`infrastructure/database/models`和`repositories`、`migrations`和`tests`原先已经按职责组织，本次保留层次。
查询和写入数据库的Repository仍在原目录；不要把它们与application中的业务Service混淆。

## 前端按什么规则找文件

```text
frontend/src/
├─ main.tsx                 挂载入口，未移动
├─ app/                     应用路由、登录/组织状态、错误边界
├─ pages/                   六个业务页面，未移动
├─ api/                     HTTP、JWT请求头、SSE读取及其单元测试
├─ components/              共享展示组件
├─ types/                   接口数据类型
└─ styles/                  全局样式
```

## 资料和产物

- `evals/corpus/`保存四份模拟检索手册及资料清单；60道题仍在`evals/knowledge_retrieval_cases.json`。
- `output/reports/`保存面试手册，`output/resumes/`保存生成简历；文件内容未改变。
- `tmp/`仍用于临时构建和检查，不移动到业务包。
- 根目录`start_frontend.py`保留，方便在PyCharm直接运行。

## 旧路径到新路径

以下路径相对本项目根目录。旧PDF的代码索引和旧聊天记录可按此表查找；移动后原行号也可能变化。

| 原路径 | 新路径 |
| --- | --- |
| `src/enterprise_support_agent/api/agent_router.py` | `src/enterprise_support_agent/api/agent/agent_router.py` |
| `src/enterprise_support_agent/api/agent_schemas.py` | `src/enterprise_support_agent/api/agent/agent_schemas.py` |
| `src/enterprise_support_agent/api/agent_conversation_router.py` | `src/enterprise_support_agent/api/agent/agent_conversation_router.py` |
| `src/enterprise_support_agent/api/agent_conversation_schemas.py` | `src/enterprise_support_agent/api/agent/agent_conversation_schemas.py` |
| `src/enterprise_support_agent/api/agent_approval_schemas.py` | `src/enterprise_support_agent/api/agent/agent_approval_schemas.py` |
| `src/enterprise_support_agent/api/checkpoint_dependencies.py` | `src/enterprise_support_agent/api/agent/checkpoint_dependencies.py` |
| `src/enterprise_support_agent/api/rate_limit_dependencies.py` | `src/enterprise_support_agent/api/agent/rate_limit_dependencies.py` |
| `src/enterprise_support_agent/api/auth_router.py` | `src/enterprise_support_agent/api/auth/auth_router.py` |
| `src/enterprise_support_agent/api/auth_schemas.py` | `src/enterprise_support_agent/api/auth/auth_schemas.py` |
| `src/enterprise_support_agent/api/auth_dependencies.py` | `src/enterprise_support_agent/api/auth/auth_dependencies.py` |
| `src/enterprise_support_agent/api/organization_router.py` | `src/enterprise_support_agent/api/organizations/organization_router.py` |
| `src/enterprise_support_agent/api/organization_schemas.py` | `src/enterprise_support_agent/api/organizations/organization_schemas.py` |
| `src/enterprise_support_agent/api/organization_dependencies.py` | `src/enterprise_support_agent/api/organizations/organization_dependencies.py` |
| `src/enterprise_support_agent/api/membership_router.py` | `src/enterprise_support_agent/api/organizations/membership_router.py` |
| `src/enterprise_support_agent/api/membership_schemas.py` | `src/enterprise_support_agent/api/organizations/membership_schemas.py` |
| `src/enterprise_support_agent/api/user_router.py` | `src/enterprise_support_agent/api/users/user_router.py` |
| `src/enterprise_support_agent/api/user_schemas.py` | `src/enterprise_support_agent/api/users/user_schemas.py` |
| `src/enterprise_support_agent/api/ticket_router.py` | `src/enterprise_support_agent/api/tickets/ticket_router.py` |
| `src/enterprise_support_agent/api/ticket_schemas.py` | `src/enterprise_support_agent/api/tickets/ticket_schemas.py` |
| `src/enterprise_support_agent/api/document_router.py` | `src/enterprise_support_agent/api/documents/document_router.py` |
| `src/enterprise_support_agent/api/document_schemas.py` | `src/enterprise_support_agent/api/documents/document_schemas.py` |
| `src/enterprise_support_agent/api/knowledge_answer_router.py` | `src/enterprise_support_agent/api/knowledge/knowledge_answer_router.py` |
| `src/enterprise_support_agent/api/knowledge_answer_schemas.py` | `src/enterprise_support_agent/api/knowledge/knowledge_answer_schemas.py` |
| `src/enterprise_support_agent/api/knowledge_search_router.py` | `src/enterprise_support_agent/api/knowledge/knowledge_search_router.py` |
| `src/enterprise_support_agent/api/knowledge_search_schemas.py` | `src/enterprise_support_agent/api/knowledge/knowledge_search_schemas.py` |
| `src/enterprise_support_agent/api/mcp_server.py` | `src/enterprise_support_agent/api/mcp/mcp_server.py` |
| `src/enterprise_support_agent/api/mcp_dependencies.py` | `src/enterprise_support_agent/api/mcp/mcp_dependencies.py` |
| `src/enterprise_support_agent/api/mcp_token_verifier.py` | `src/enterprise_support_agent/api/mcp/mcp_token_verifier.py` |
| `src/enterprise_support_agent/api/error_handlers.py` | `src/enterprise_support_agent/api/common/error_handlers.py` |
| `src/enterprise_support_agent/api/error_schemas.py` | `src/enterprise_support_agent/api/common/error_schemas.py` |
| `src/enterprise_support_agent/api/health.py` | `src/enterprise_support_agent/api/common/health.py` |
| `src/enterprise_support_agent/api/sse.py` | `src/enterprise_support_agent/api/common/sse.py` |
| `src/enterprise_support_agent/application/auth_service.py` | `src/enterprise_support_agent/application/identity/auth_service.py` |
| `src/enterprise_support_agent/application/user_service.py` | `src/enterprise_support_agent/application/identity/user_service.py` |
| `src/enterprise_support_agent/application/organization_service.py` | `src/enterprise_support_agent/application/identity/organization_service.py` |
| `src/enterprise_support_agent/application/membership_service.py` | `src/enterprise_support_agent/application/identity/membership_service.py` |
| `src/enterprise_support_agent/application/organization_roles.py` | `src/enterprise_support_agent/application/identity/organization_roles.py` |
| `src/enterprise_support_agent/application/mcp_identity_service.py` | `src/enterprise_support_agent/application/identity/mcp_identity_service.py` |
| `src/enterprise_support_agent/application/document_service.py` | `src/enterprise_support_agent/application/documents/document_service.py` |
| `src/enterprise_support_agent/application/document_processing_service.py` | `src/enterprise_support_agent/application/documents/document_processing_service.py` |
| `src/enterprise_support_agent/application/document_processing_job_service.py` | `src/enterprise_support_agent/application/documents/document_processing_job_service.py` |
| `src/enterprise_support_agent/application/document_chunker.py` | `src/enterprise_support_agent/application/documents/document_chunker.py` |
| `src/enterprise_support_agent/application/document_enums.py` | `src/enterprise_support_agent/application/documents/document_enums.py` |
| `src/enterprise_support_agent/application/ticket_service.py` | `src/enterprise_support_agent/application/tickets/ticket_service.py` |
| `src/enterprise_support_agent/application/ticket_enums.py` | `src/enterprise_support_agent/application/tickets/ticket_enums.py` |
| `src/enterprise_support_agent/application/knowledge_search_service.py` | `src/enterprise_support_agent/application/knowledge/knowledge_search_service.py` |
| `src/enterprise_support_agent/application/knowledge_answer_service.py` | `src/enterprise_support_agent/application/knowledge/knowledge_answer_service.py` |
| `src/enterprise_support_agent/application/hybrid_retriever.py` | `src/enterprise_support_agent/application/knowledge/hybrid_retriever.py` |
| `src/enterprise_support_agent/application/citation_validator.py` | `src/enterprise_support_agent/application/knowledge/citation_validator.py` |
| `src/enterprise_support_agent/application/rag_prompt.py` | `src/enterprise_support_agent/application/knowledge/rag_prompt.py` |
| `src/enterprise_support_agent/application/reranker.py` | `src/enterprise_support_agent/application/knowledge/reranker.py` |
| `src/enterprise_support_agent/application/exceptions.py` | `src/enterprise_support_agent/application/common/exceptions.py` |
| `src/enterprise_support_agent/application/agent_context.py` | `src/enterprise_support_agent/application/agent/agent_context.py` |
| `src/enterprise_support_agent/application/agent_execution_result.py` | `src/enterprise_support_agent/application/agent/agent_execution_result.py` |
| `src/enterprise_support_agent/application/agent_state.py` | `src/enterprise_support_agent/application/agent/agent_state.py` |
| `src/enterprise_support_agent/application/langgraph_agent_service.py` | `src/enterprise_support_agent/application/agent/langgraph_agent_service.py` |
| `src/enterprise_support_agent/application/agent_graph.py` | `src/enterprise_support_agent/application/agent/agent_graph.py` |
| `src/enterprise_support_agent/application/agent_context_node.py` | `src/enterprise_support_agent/application/agent/nodes/agent_context_node.py` |
| `src/enterprise_support_agent/application/agent_model_node.py` | `src/enterprise_support_agent/application/agent/nodes/agent_model_node.py` |
| `src/enterprise_support_agent/application/agent_routing_node.py` | `src/enterprise_support_agent/application/agent/nodes/agent_routing_node.py` |
| `src/enterprise_support_agent/application/agent_tool_agent.py` | `src/enterprise_support_agent/application/agent/nodes/agent_tool_node.py` |
| `src/enterprise_support_agent/application/agent_router_model.py` | `src/enterprise_support_agent/application/agent/routing/agent_router_model.py` |
| `src/enterprise_support_agent/application/agent_routing_schemas.py` | `src/enterprise_support_agent/application/agent/routing/agent_routing_schemas.py` |
| `src/enterprise_support_agent/application/agent_conversation_service.py` | `src/enterprise_support_agent/application/agent/memory/agent_conversation_service.py` |
| `src/enterprise_support_agent/application/agent_context_messages.py` | `src/enterprise_support_agent/application/agent/memory/agent_context_messages.py` |
| `src/enterprise_support_agent/application/agent_history_remover.py` | `src/enterprise_support_agent/application/agent/memory/agent_history_remover.py` |
| `src/enterprise_support_agent/application/agent_history_splitter.py` | `src/enterprise_support_agent/application/agent/memory/agent_history_splitter.py` |
| `src/enterprise_support_agent/application/agent_history_summarizer.py` | `src/enterprise_support_agent/application/agent/memory/agent_history_summarizer.py` |
| `src/enterprise_support_agent/application/agent_token_counter.py` | `src/enterprise_support_agent/application/agent/memory/agent_token_counter.py` |
| `src/enterprise_support_agent/application/agent_tools.py` | `src/enterprise_support_agent/application/agent/tools/agent_tools.py` |
| `src/enterprise_support_agent/application/agent_tool_groups.py` | `src/enterprise_support_agent/application/agent/tools/agent_tool_groups.py` |
| `src/enterprise_support_agent/application/agent_tool_schemas.py` | `src/enterprise_support_agent/application/agent/tools/agent_tool_schemas.py` |
| `src/enterprise_support_agent/application/mcp_agent_tools.py` | `src/enterprise_support_agent/application/agent/tools/mcp_agent_tools.py` |
| `src/enterprise_support_agent/application/agent_ticket_approval.py` | `src/enterprise_support_agent/application/agent/tools/agent_ticket_approval.py` |
| `src/enterprise_support_agent/application/agent_prompt.py` | `src/enterprise_support_agent/application/agent/prompts/agent_prompt.py` |
| `src/enterprise_support_agent/application/agent_routing_prompt.py` | `src/enterprise_support_agent/application/agent/prompts/agent_routing_prompt.py` |
| `src/enterprise_support_agent/application/knowledge_agent_prompt.py` | `src/enterprise_support_agent/application/agent/prompts/knowledge_agent_prompt.py` |
| `src/enterprise_support_agent/application/ticket_agent_prompt.py` | `src/enterprise_support_agent/application/agent/prompts/ticket_agent_prompt.py` |
| `src/enterprise_support_agent/application/agent_service.py` | `src/enterprise_support_agent/application/agent/legacy/agent_service.py` |
| `src/enterprise_support_agent/scripts/check_database_connection.py` | `src/enterprise_support_agent/scripts/connections/check_database_connection.py` |
| `src/enterprise_support_agent/scripts/check_qdrant_connection.py` | `src/enterprise_support_agent/scripts/connections/check_qdrant_connection.py` |
| `src/enterprise_support_agent/scripts/check_mcp_connection.py` | `src/enterprise_support_agent/scripts/connections/check_mcp_connection.py` |
| `src/enterprise_support_agent/scripts/check_pdf_parser.py` | `src/enterprise_support_agent/scripts/knowledge/check_pdf_parser.py` |
| `src/enterprise_support_agent/scripts/check_citation_validator.py` | `src/enterprise_support_agent/scripts/knowledge/check_citation_validator.py` |
| `src/enterprise_support_agent/scripts/check_bm25_retrieval.py` | `src/enterprise_support_agent/scripts/knowledge/check_bm25_retrieval.py` |
| `src/enterprise_support_agent/scripts/check_hybrid_retrieval.py` | `src/enterprise_support_agent/scripts/knowledge/check_hybrid_retrieval.py` |
| `src/enterprise_support_agent/scripts/check_rag_streaming.py` | `src/enterprise_support_agent/scripts/knowledge/check_rag_streaming.py` |
| `src/enterprise_support_agent/scripts/check_chat_streaming.py` | `src/enterprise_support_agent/scripts/models/check_chat_streaming.py` |
| `src/enterprise_support_agent/scripts/check_embedding_model.py` | `src/enterprise_support_agent/scripts/models/check_embedding_model.py` |
| `src/enterprise_support_agent/scripts/check_reranker.py` | `src/enterprise_support_agent/scripts/models/check_reranker.py` |
| `src/enterprise_support_agent/scripts/check_agent_tool_selection.py` | `src/enterprise_support_agent/scripts/agent/check_agent_tool_selection.py` |
| `src/enterprise_support_agent/scripts/check_knowledge_tool.py` | `src/enterprise_support_agent/scripts/agent/check_knowledge_tool.py` |
| `src/enterprise_support_agent/scripts/check_rabbitmq_connection.py` | `src/enterprise_support_agent/scripts/messaging/check_rabbitmq_connection.py` |
| `src/enterprise_support_agent/scripts/check_rabbitmq_topology.py` | `src/enterprise_support_agent/scripts/messaging/check_rabbitmq_topology.py` |
| `src/enterprise_support_agent/scripts/check_rabbitmq_publish.py` | `src/enterprise_support_agent/scripts/messaging/check_rabbitmq_publish.py` |
| `src/enterprise_support_agent/scripts/check_rabbitmq_consume.py` | `src/enterprise_support_agent/scripts/messaging/check_rabbitmq_consume.py` |
| `src/enterprise_support_agent/scripts/check_redis_connection.py` | `src/enterprise_support_agent/scripts/cache/check_redis_connection.py` |
| `src/enterprise_support_agent/scripts/check_redis_rate_limit.py` | `src/enterprise_support_agent/scripts/cache/check_redis_rate_limit.py` |
| `src/enterprise_support_agent/scripts/ensure_qdrant_collection.py` | `src/enterprise_support_agent/scripts/setup/ensure_qdrant_collection.py` |
| `src/enterprise_support_agent/scripts/set_checkpointer.py` | `src/enterprise_support_agent/scripts/setup/set_checkpointer.py` |
| `src/enterprise_support_agent/infrastructure/mcp_knowledge_client.py` | `src/enterprise_support_agent/infrastructure/mcp/knowledge_client.py` |
| `frontend/src/App.tsx` | `frontend/src/app/App.tsx` |
| `frontend/src/workspace.tsx` | `frontend/src/app/workspace.tsx` |
| `frontend/src/ErrorBoundary.tsx` | `frontend/src/app/ErrorBoundary.tsx` |
| `frontend/src/api.ts` | `frontend/src/api/client.ts` |
| `frontend/src/api.test.ts` | `frontend/src/api/client.test.ts` |
| `frontend/src/ui.tsx` | `frontend/src/components/ui.tsx` |
| `frontend/src/types.ts` | `frontend/src/types/index.ts` |
| `frontend/src/styles.css` | `frontend/src/styles/global.css` |
| `output/pdf/retrieval_corpus/corpus_manifest.json` | `evals/corpus/corpus_manifest.json` |
| `output/pdf/retrieval_corpus/KB-AUTH-005_jwt_organization_access.pdf` | `evals/corpus/KB-AUTH-005_jwt_organization_access.pdf` |
| `output/pdf/retrieval_corpus/KB-MQ-003_rabbitmq_document_jobs.pdf` | `evals/corpus/KB-MQ-003_rabbitmq_document_jobs.pdf` |
| `output/pdf/retrieval_corpus/KB-REDIS-002_redis_connection_cache.pdf` | `evals/corpus/KB-REDIS-002_redis_connection_cache.pdf` |
| `output/pdf/retrieval_corpus/KB-STORAGE-004_object_storage_files.pdf` | `evals/corpus/KB-STORAGE-004_object_storage_files.pdf` |
| `output/docx/Agent简历_最终项目版.docx` | `output/resumes/Agent简历_最终项目版.docx` |
| `output/docx/Agent简历_项目经历更新.docx` | `output/resumes/Agent简历_项目经历更新.docx` |
| `output/pdf/企业支持Agent平台_面试复盘手册.pdf` | `output/reports/企业支持Agent平台_面试复盘手册.pdf` |
