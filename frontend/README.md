# 知序 · 企业支持工作台

React + TypeScript + Vite + Ant Design，直接调用本项目的 FastAPI 接口。界面不内置演示账号、不伪造业务数据，也不保存模型 API Key。

## 本地启动

### 在 PyCharm 中点击运行（推荐）

先启动 Docker 中的 PostgreSQL、RustFS、Qdrant、RabbitMQ 和 Redis，然后分别打开下面的 Python 文件，右键选择“运行”：

1. 后端：`D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent\src\enterprise_support_agent\main.py`。
2. MCP 服务：`D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent\src\enterprise_support_agent\api\mcp\mcp_server.py`，智能助手检索知识库时需要。
3. 文档 Worker：`D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent\src\enterprise_support_agent\workers\document_processing_worker.py`。
4. 前端入口：`D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent\start_frontend.py`。

前端入口会自动打开浏览器。已运行的后端、Worker无需重复启动；前端入口检测到已有前端时会直接打开页面。保留运行窗口，前端实际仍由 Node.js 执行，Python负责启动它。本机前端依赖已经安装。

### 使用终端启动（可选）

先启动 Docker 中的 PostgreSQL、RustFS、Qdrant、RabbitMQ 和 Redis。接着分别启动以下服务，不是在容器的 Exec 中执行：

### 终端一：后端

```powershell
cd D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent
uv run uvicorn enterprise_support_agent.main:app --host 127.0.0.1 --port 8002 --reload
```

后端已经运行时，不要重复启动。数据库结构应已执行 `uv run alembic upgrade head`。

### 终端二：MCP 服务

```powershell
cd D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent
uv run python -u -m enterprise_support_agent.api.mcp.mcp_server
```

### 终端三：文档 Worker

```powershell
cd D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent
uv run python -u -m enterprise_support_agent.workers.document_processing_worker
```

Worker 未运行时，前端仍可提交任务，任务会等待处理。上传文件与处理文档是两个步骤；管理员可以在上传窗口选择自动提交处理。

### 终端四：前端

```powershell
cd D:\develop\Pyproject\PythonProject\Hello_agent\enterprise_support_agent\frontend
npm.cmd install
npm.cmd run dev
```

打开 **http://127.0.0.1:5173**，使用已有账号登录。也可以在页面注册，再创建组织，或让管理员将用户加入组织。

## 可操作的页面

- 智能助手：自动创建会话、发送问题、选择是否允许发起创建、同意或拒绝工单审批。执行中断后可点击“重试本次任务”，在原会话继续；刷新或连接已有会话时会查询后端任务状态。不会自动批准写操作，也不会自动重发创建请求。
- 知识问答：普通或 SSE 流式回答、引用正文、检索参数、独立检索模式及向量/BM25/RRF/Rerank 分数。未收到完成事件或引用校验失败时，临时文本会被丢弃。
- 知识文档：批量 PDF 上传、处理任务提交、定时查询进度、查询历史任务 ID、重新发送 pending 消息、下载和删除文档。上传时先检查20MiB上限，最终规则由后端执行。
- 工单中心：搜索、筛选、新建、查看、分配处理人，以及后端允许的状态流转。
- 组织与成员：创建组织、添加已有用户、创建成员账号、修改角色、移除成员。界面根据当前组织角色显示操作，后端继续执行最终权限验证。

## 会话与登录状态

JWT 保存在当前标签页的 `sessionStorage` 中，请求自动发送 `Authorization: Bearer ...`。后端返回401时清除登录状态，回到登录页；页面不会显示令牌。

后端已有会话创建和按ID读取接口，没有全量会话列表及完整历史消息读取接口。因此当前浏览器按“用户ID＋组织ID”保存会话入口、已展示消息和待审批信息；真实 Agent 状态仍由后端 Checkpointer 持久化。刷新后可以继续本浏览器中的会话。其他会话可以输入 ID，经后端验证归属后继续，但页面无法补回此前未在该浏览器展示过的历史消息。

任务状态通过 `GET /organizations/{organization_id}/agent/conversations/{conversation_id}/execution` 读取；失败时使用对应的 `POST .../retry` 继续原任务，不再次发送问题。正在执行时等待，等待审批时仍需点击同意或拒绝。创建工单使用由会话、任务和工具调用编号计算的固定UUID，同一次操作重试会找回原工单，数据库表结构无需迁移。

旧任务没有记录原创建授权时，点击重试会单独弹窗：可选择“只恢复查询”或“允许发起审批并重试”，也可以取消。后端要求明确选择，并把任务编号和选择保存到原会话存档；再次失败或刷新后会保留，不再采用页面默认关闭状态。每个会话的页面开关选择也会保存在当前浏览器。新任务仍以存档中的原授权恢复，不能借重试扩大权限；实际创建始终须审批。

兼容边界：修复前的旧任务如果恰好在创建工单的工具节点失败，又没有保存创建结果，无法可靠判断当时是否已经提交。页面会提示先核对工单，并禁止直接重跑这个旧创建操作；旧检索失败仍可恢复。修复后新任务通过固定工单ID覆盖提交后存档失败的重复创建窗口。

## 接口代理

开发时浏览器请求 `/api/...`，Vite 转发到 `http://127.0.0.1:8002` 并去掉 `/api` 前缀，包含 SSE 和带JWT的下载。无需为本地开发修改 FastAPI 的 CORS 设置。

要修改后端地址，复制 `.env.example` 为 `.env.local`，调整 `BACKEND_URL` 后重启前端。这里的地址由 Node 开发服务器读取，不包含密码或 API Key。

## 构建和检查

```powershell
npm.cmd run build
npm.cmd test
npm.cmd run test:e2e
```

浏览器测试使用本机 Google Chrome，所有业务接口都由测试拦截，不会调用真实模型、上传真实文件或修改数据库。测试涵盖审批编号、失败重试、刷新恢复、响应丢失后的结果核对、上传及任务轮询、SSE错误处理、组织切换、角色按钮、工单流转和移动端布局。

```powershell
npm.cmd run preview
```

构建预览位于 `http://127.0.0.1:4173`，同样带本地后端代理。正式部署静态产物 `dist` 时，需要由Web服务器配置 `/api` 反向代理，并把非文件页面路径回退到 `index.html`。

## 常见问题

- 无法连接后端：先访问 `http://127.0.0.1:8002/health`，确认后端及启动所需基础服务可用。
- 没有组织：到“组织与成员”创建，或者让管理员添加你的真实用户ID。
- 上传后仍不可检索：管理员提交处理任务，确认Worker运行，并等任务成功、文档变为“可检索”。
- 返回429：按照错误提示等待限流窗口结束，不要连续重发。
- 出错后需要排查：页面会保留后端返回的请求编号，可以复制它定位日志。

Swagger `http://127.0.0.1:8002/docs` 继续保留，适合检查接口原始参数、响应状态和边界条件。
