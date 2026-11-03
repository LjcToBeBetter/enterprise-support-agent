"""
请求日志中间件模块。

主要功能：
    记录 HTTP 请求的方法、路径、状态码和处理耗时。

主要部件：
    register_request_logging：给应用注册请求日志中间件。
    log_requests：每次 HTTP 请求到来时，由框架调用。
    perf_counter：Python 提供的计时函数，单位是秒。


先认识两个参数，它们都由 FastAPI 自动传入：
- request：本次请求的对象，可以读取请求方法和路径。
- call_next：框架提供的函数，用来让请求继续往后执行，并取得响应。
"""

import logging
from time import perf_counter
from uuid import uuid4
from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)

def register_request_logging(app: FastAPI):
    """给传入的 FastAPI 应用注册中间件。"""

    # 注册："http" 表示为 HTTP 请求注册中间件。
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # 记录开始时间，用来计算时间差。
        start_time = perf_counter()
        # 每次请求生成一个新的编号。
        request_id = uuid4().hex

        # state 是本次请求的临时存储空间,request.state 是请求对象提供的属性
        # request_id 是我们自己添加的属性名，
        # 同一次请求中的其他代码可以读取它。
        request.state.request_id = request_id


        try:
            # 让请求继续执行，等待后面的接口生成响应。
            response = await call_next(request)
        except Exception:
            # exception 会记录 ERROR 日志，并附带异常调用栈。
            logger.exception(
                f"request_id={request_id} 请求发生异常：{request.method} {request.url.path}"
            )
            # 重新抛出原异常，交给框架继续处理。
            raise

        # 时间差原本是秒，乘以 1000 转成毫秒。
        duration_ms = (perf_counter() - start_time) * 1000

        # request.method：GET、POST 等请求方法。
        # request.url.path：请求路径，例如 /health。
        # response.status_code：HTTP 状态码，例如 200。
        # :.2f：把耗时显示为两位小数。
        logger.info(
            f"request_id={request_id} {request.method} {request.url.path} status={response.status_code} duration_ms={duration_ms:.2f}"
        )

        # 自定义响应头，将本次请求编号交给客户端。
        response.headers["X-Request-ID"] = request_id

        return response