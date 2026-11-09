"""
向接口提供应用启动时创建的Checkpointer。

这里只取出已有对象，
不新建连接池，也不关闭连接池。
"""

from fastapi import (
    HTTPException,
    Request,
)
from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)


def get_checkpointer(
    request: Request,
) -> AsyncPostgresSaver:
    """从当前FastAPI应用中取得Checkpointer对象。"""

    # request.app是处理这次请求的FastAPI应用。
    #
    # app.state.checkpointer是在lifespan启动阶段保存的。
    #
    # getattr()读取这个属性：
    # 如果属性不存在，则返回None。
    checkpointer = getattr(
        request.app.state,
        "checkpointer",
        None,
    )

    # 防止生命周期没有正确初始化，
    # 或者共享属性被错误地设置成其他类型。
    if not isinstance(
        checkpointer,
        AsyncPostgresSaver,
    ):
        raise HTTPException(
            status_code=503,
            detail="Checkpoint服务尚未就绪",
        )

    return checkpointer