"""
健康检查接口模块。

主要部件：
    router：收集本模块的接口，供主应用注册。
    health：处理 GET /health 请求，返回服务状态。
"""

from fastapi import APIRouter

# 创建路由对象。
router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    """确认 HTTP 服务能正常响应。"""
    return {"status": "ok"}