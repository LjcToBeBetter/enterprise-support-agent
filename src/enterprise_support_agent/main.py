"""
后端入口模块。

主要部件：
    settings：读取完成的应用配置。
    app：FastAPI 应用对象。
    health_router：健康检查路由。
    uvicorn.run：使用配置中的地址和端口启动服务。
"""

from fastapi import FastAPI
import uvicorn
from enterprise_support_agent.api.health import router as health_router
from enterprise_support_agent.config import settings
from enterprise_support_agent.lifespan import lifespan
from enterprise_support_agent.logging_config import configure_logging
from enterprise_support_agent.request_middleware import register_request_logging
from enterprise_support_agent.api.error_handlers import register_exception_handlers
from enterprise_support_agent.api.organization_router import (
    router as organization_router,
)
from enterprise_support_agent.api.user_router import (
    router as user_router,
)
from enterprise_support_agent.api.membership_router import (
    router as membership_router,
)
from enterprise_support_agent.api.auth_router import (
    router as auth_router,
)
from enterprise_support_agent.api.ticket_router import (
    router as ticket_router,
)
from enterprise_support_agent.api.document_router import (
    router as document_router,
)
from enterprise_support_agent.api.knowledge_search_router import (
    router as knowledge_search_router,
)
from enterprise_support_agent.api.knowledge_answer_router import (
    router as knowledge_answer_router,
)
from enterprise_support_agent.api.agent_router import (
    router as agent_router,
)

# 应用加载时，先完成日志配置。
configure_logging()

app=FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# #都是往fastapi对象里注册东西，像：
# register_request_logging(app)
# register_exception_handlers(app)
# 是我们自己定义的方法，表面上看只是传参，实际的注册是在方法内部装饰器里实现的
# 而例如：app.include_router(health_router)他是FastAPI自带的注册方法

# 注册请求日志中间件。
register_request_logging(app)

# 告诉 FastAPI：出现异常时，使用我们定义的处理方法。
register_exception_handlers(app)

# 将健康检查路由中的接口注册到应用。
# 注册后，app 才能处理 GET /health 请求。
app.include_router(health_router)

# 注册组织模块的Router。
# 注册后，FastAPI才能处理POST /organizations请求。
app.include_router(organization_router)

# 注册用户模块的Router。
# 注册后，FastAPI才能处理POST /users请求。
app.include_router(user_router)

# 注册组织成员关系接口。
# 注册后，FastAPI才能接收：
# POST /organizations/{organization_id}/members
app.include_router(membership_router)

app.include_router(auth_router)

app.include_router(ticket_router)

# 注册企业知识库RAG问答接口。
#
# 注册后，FastAPI才能处理：
# POST /organizations/{organization_id}/knowledge/answer
app.include_router(
    knowledge_answer_router
)

# 注册知识库文档接口。
#
# 注册后，FastAPI才能处理：
# POST   /organizations/{organization_id}/documents
# GET    /organizations/{organization_id}/documents
# GET    /organizations/{organization_id}/documents/{document_id}
# GET    /organizations/{organization_id}/documents/{document_id}/download
# DELETE /organizations/{organization_id}/documents/{document_id}
app.include_router(
    document_router
)

# 注册知识库检索接口。
#
# 注册后，FastAPI才能处理：
# POST /organizations/{organization_id}/knowledge/search
app.include_router(
    knowledge_search_router
)
# 注册企业支持Agent接口。
#
# 注册后才能处理：
# POST /organizations/{organization_id}/agent/chat
app.include_router(agent_router)


if __name__ == "__main__":
    uvicorn.run(
        # 加载本模块中的 FastAPI 应用对象 app。
        "enterprise_support_agent.main:app",
        host=settings.host,
        port=settings.port,

        # 开发时，修改并保存代码后自动重启。
        reload=settings.reload
    )
