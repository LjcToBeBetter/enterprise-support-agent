"""
错误响应结构模块。

主要功能：
    规定接口出错时，返回给客户端的数据格式。

主要部件：
    ErrorResponse：统一错误响应模型。
        使用 Pydantic 校验响应字段和类型。
"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """统一的错误响应格式。"""

    # 业务错误代码，例如 NOT_FOUND。
    code: str

    # 给用户看的错误说明。
    message: str

    # 当前请求编号，与日志中的 request_id 对应。
    request_id: str