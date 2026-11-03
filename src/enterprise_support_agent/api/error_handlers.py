"""
HTTP 异常处理模块。

主要功能：
    将 HTTP 异常转换为统一的 JSON 错误响应。

主要部件：
    register_exception_handlers：注册异常处理器。
    handle_http_exception：接收请求和异常，构造错误响应。
    JSONResponse：生成带状态码的 JSON 响应对象。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Starlette 是 FastAPI 使用的底层框架。
# 使用它的 HTTPException，能同时处理框架产生的404，
# 以及我们通过 FastAPI HTTPException 抛出的异常。
from starlette.exceptions import HTTPException
# 用户传错参数
from fastapi.exceptions import RequestValidationError
from enterprise_support_agent.api.error_schemas import ErrorResponse
from enterprise_support_agent.application.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTicketStatusTransitionError,
    OrganizationAccessDeniedError,
    OrganizationCodeAlreadyExistsError,
    OrganizationMembershipAlreadyExistsError,
    OrganizationMembershipNotFoundError,
    OrganizationNotFoundError,
    TicketAccessDeniedError,
    TicketAssigneeNotOrganizationMemberError,
    TicketAssigneeRoleNotAllowedError,
    TicketNotFoundError,
    UserEmailAlreadyExistsError,
    UserNotFoundError,
    DocumentFileTooLargeError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    EmptyDocumentFileError,
    ObjectStorageUnavailableError,
    UnsupportedDocumentTypeError,
)

def register_exception_handlers(app: FastAPI) -> None:
    """给应用注册异常处理器。"""

    # 注册：指定-遇到 HTTPException 时，由下面的函数处理。
    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        # request：发生异常的那次请求。
        # exc：框架捕获到的异常对象。
        # 这两个参数都由框架自动传入。

        # getattr 是 Python 内置函数：
        # 读取中间件保存的 request_id，找不到时使用 "unknown"。
        request_id = getattr(request.state, "request_id", "unknown")

        # 根据 HTTP 状态码确定错误代码。
        if exc.status_code == 404:
            code = "NOT_FOUND"
        else:
            code = f"HTTP_{exc.status_code}"

        # 创建并校验统一错误响应对象。
        error = ErrorResponse(
            code=code,
            message=str(exc.detail),
            request_id=request_id,
        )

        # 异常处理器需要返回响应对象。
        # model_dump() 将 Pydantic 对象转换为字典，
        # JSONResponse 再将字典转换为 JSON 响应。
        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(),

            # 保留异常携带的响应头。
            headers=exc.headers,
        )

    # 用户漏填必填参数、填错类型等情况，交给这个方法处理。
    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # request 是这次请求，exc 里装着参数检查失败的信息。
        # 两个参数都由框架自动传入。

        # 取出这次请求的编号。
        request_id = getattr(request.state, "request_id", "unknown")

        # 统一告诉客户端：传进来的参数有问题。
        error = ErrorResponse(
            code="VALIDATION_ERROR",
            message="请求参数格式不正确，请检查必填项和数据类型",
            request_id=request_id,
        )

        return JSONResponse(
            # 422 表示请求的数据没有通过参数检查。
            status_code=422,
            content=error.model_dump(),
        )

    @app.exception_handler(
        OrganizationCodeAlreadyExistsError
    )
    async def handle_organization_code_exists(
        request: Request,
        exc: OrganizationCodeAlreadyExistsError,
    ) -> JSONResponse:
        """处理组织编码重复异常。"""

        # 从请求临时状态中取得请求编号。
        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        # 把业务异常转换成统一错误响应。
        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        # 409表示请求与服务器当前数据状态发生冲突。
        # 这里的冲突就是组织编码已经存在。
        return JSONResponse(
            status_code=409,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(OrganizationNotFoundError)
    async def handle_organization_not_found(
            request: Request,
            exc: OrganizationNotFoundError,
    ) -> JSONResponse:
        """处理组织不存在异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        # 404表示客户端请求的资源不存在。
        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )


    @app.exception_handler(
        UserEmailAlreadyExistsError
    )
    async def handle_user_email_exists(
        request: Request,
        exc: UserEmailAlreadyExistsError,
    ) -> JSONResponse:
        """处理用户邮箱重复异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=409,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )
    @app.exception_handler(
        UserNotFoundError
    )
    async def handle_user_not_found(
        request: Request,
        exc: UserNotFoundError,
    ) -> JSONResponse:
        """处理用户不存在异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        OrganizationMembershipAlreadyExistsError
    )
    async def handle_membership_exists(
        request: Request,
        exc: OrganizationMembershipAlreadyExistsError,
    ) -> JSONResponse:
        """处理用户重复加入组织异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=409,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        OrganizationMembershipNotFoundError
    )
    async def handle_membership_not_found(
            request: Request,
            exc: OrganizationMembershipNotFoundError,
    ) -> JSONResponse:
        """处理组织成员关系不存在异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        InvalidCredentialsError
    )
    async def handle_invalid_credentials(
            request: Request,
            exc: InvalidCredentialsError,
    ) -> JSONResponse:
        """处理邮箱或密码错误。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 401表示身份认证失败。
            status_code=401,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id,

                # 告诉客户端该接口使用Bearer令牌认证。
                "WWW-Authenticate": "Bearer",
            },
        )

    @app.exception_handler(
        InactiveUserError
    )
    async def handle_inactive_user(
            request: Request,
            exc: InactiveUserError,
    ) -> JSONResponse:
        """处理账号已被停用。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 403表示身份已经确认，
            # 但当前账号不允许执行操作。
            status_code=403,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        OrganizationAccessDeniedError
    )
    async def handle_organization_access_denied(
            request: Request,
            exc: OrganizationAccessDeniedError,
    ) -> JSONResponse:
        """处理组织访问权限不足异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 403表示已经确认用户身份，
            # 但用户没有执行当前操作的权限。
            status_code=403,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        TicketNotFoundError
    )
    async def handle_ticket_not_found(
        request: Request,
        exc: TicketNotFoundError,
    ) -> JSONResponse:
        """处理工单不存在异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 404表示请求的工单不存在。
            status_code=404,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        TicketAccessDeniedError
    )
    async def handle_ticket_access_denied(
        request: Request,
        exc: TicketAccessDeniedError,
    ) -> JSONResponse:
        """处理工单访问权限不足异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 用户身份已经确认，
            # 但没有权限查看或修改这张工单。
            status_code=403,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        TicketAssigneeNotOrganizationMemberError
    )
    async def handle_ticket_assignee_not_member(
        request: Request,
        exc: TicketAssigneeNotOrganizationMemberError,
    ) -> JSONResponse:
        """处理工单处理人员不属于组织异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 客户端指定了不能使用的处理人员。
            status_code=400,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        TicketAssigneeRoleNotAllowedError
    )
    async def handle_ticket_assignee_role_not_allowed(
        request: Request,
        exc: TicketAssigneeRoleNotAllowedError,
    ) -> JSONResponse:
        """处理指定用户角色不能处理工单异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 用户属于组织，但角色不能处理工单。
            status_code=400,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        InvalidTicketStatusTransitionError
    )
    async def handle_invalid_ticket_status_transition(
        request: Request,
        exc: InvalidTicketStatusTransitionError,
    ) -> JSONResponse:
        """处理工单状态流转不合法异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 409表示请求与工单当前状态发生冲突。
            status_code=409,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        DocumentNotFoundError
    )
    async def handle_document_not_found(
        request: Request,
        exc: DocumentNotFoundError,
    ) -> JSONResponse:
        """处理知识库文档不存在异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=404,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        UnsupportedDocumentTypeError
    )
    async def handle_unsupported_document_type(
        request: Request,
        exc: UnsupportedDocumentTypeError,
    ) -> JSONResponse:
        """处理上传文件类型不支持异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 400表示客户端提交的文件不符合要求。
            status_code=400,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        EmptyDocumentFileError
    )
    async def handle_empty_document_file(
        request: Request,
        exc: EmptyDocumentFileError,
    ) -> JSONResponse:
        """处理上传空文件异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=400,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        DocumentFileTooLargeError
    )
    async def handle_document_file_too_large(
        request: Request,
        exc: DocumentFileTooLargeError,
    ) -> JSONResponse:
        """处理上传文件超过大小限制异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 413表示请求内容超过服务器允许的大小。
            status_code=413,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        DuplicateDocumentError
    )
    async def handle_duplicate_document(
        request: Request,
        exc: DuplicateDocumentError,
    ) -> JSONResponse:
        """处理同一组织重复上传相同文件异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 409表示与当前已有文档状态冲突。
            status_code=409,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    @app.exception_handler(
        ObjectStorageUnavailableError
    )
    async def handle_object_storage_unavailable(
        request: Request,
        exc: ObjectStorageUnavailableError,
    ) -> JSONResponse:
        """处理对象存储暂时不可用异常。"""

        request_id = getattr(
            request.state,
            "request_id",
            "unknown",
        )

        error = ErrorResponse(
            code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        )

        return JSONResponse(
            # 503表示当前依赖服务暂时不可用。
            status_code=503,
            content=error.model_dump(),
            headers={
                "X-Request-ID": request_id
            },
        )

    # 接住前面没有处理掉的普通程序错误。前面的注解是HTTPException,所以不会处理其他的异常
    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        # request 是出错的请求，exc 是具体错误。
        # 两个参数都由框架自动传入。

        # 取出这次请求的编号，方便用户提供编号让我们查日志。
        request_id = getattr(request.state, "request_id", "unknown")

        # 具体错误已经由中间件记录到日志。
        # 给用户返回统一提示。
        error = ErrorResponse(
            code="INTERNAL_SERVER_ERROR",
            message="服务暂时出错，请稍后重试",
            request_id=request_id,
        )

        return JSONResponse(
            # 500 表示服务内部出了问题。
            status_code=500,

            # model_dump把Pydantic对象转换成普通Python字典。
            content=error.model_dump(),

            # 出错后会跳过中间件最后添加响应头的代码，
            # 所以在这里把请求编号补进响应头。
            headers={"X-Request-ID": request_id},
        )