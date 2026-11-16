"""
exceptions.py

主要功能：
    定义应用业务处理中可能发生的异常。

主要部件：
    ApplicationError：
        所有业务异常共同继承的父类。

    OrganizationCodeAlreadyExistsError：
        创建组织时，组织编码已经存在。
"""

from uuid import UUID

class ApplicationError(Exception):
    """应用业务异常的共同父类。"""

    # 默认错误编码。
    error_code = "APPLICATION_ERROR"

    def __init__(
        self,
        message: str,
    ) -> None:
        # 保存给客户端展示的错误信息。
        self.message = message

        # 调用Exception父类，让Python异常机制能够正常工作。
        super().__init__(message)


class OrganizationCodeAlreadyExistsError(
    ApplicationError
):
    """组织编码已被使用。"""

    # 程序可以通过稳定的错误编码识别异常类型。
    error_code = "ORGANIZATION_CODE_ALREADY_EXISTS"

    def __init__(
        self,
        organization_code: str,
    ) -> None:
        # 保存发生冲突的组织编码，方便日志和调试使用。
        self.organization_code = organization_code

        super().__init__(
            f"组织编码“{organization_code}”已存在"
        )

class OrganizationNotFoundError(
    ApplicationError
):
    """根据ID没有找到组织。"""

    # 给前端程序识别的稳定错误编码。
    error_code = "ORGANIZATION_NOT_FOUND"

    def __init__(
        self,
        organization_id: UUID,
    ) -> None:
        # 保存没有查询到的组织ID。
        self.organization_id = organization_id

        # 调用父类，保存最终错误信息。
        super().__init__(
            f"没有找到ID为“{organization_id}”的组织"
        )


class UserEmailAlreadyExistsError(
    ApplicationError
):
    """创建用户时，邮箱已经被使用。"""

    error_code = "USER_EMAIL_ALREADY_EXISTS"

    def __init__(
        self,
        email: str,
    ) -> None:
        # 保存发生冲突的邮箱，方便日志排查。
        self.email = email

        super().__init__(
            f"邮箱“{email}”已被使用"
        )

class UserNotFoundError(
    ApplicationError
):
    """根据ID没有找到用户。"""

    error_code = "USER_NOT_FOUND"

    def __init__(
        self,
        user_id: UUID,
    ) -> None:
        self.user_id = user_id

        super().__init__(
            f"没有找到ID为“{user_id}”的用户"
        )


class OrganizationMembershipAlreadyExistsError(
    ApplicationError
):
    """用户已经属于指定组织。"""

    error_code = "ORGANIZATION_MEMBERSHIP_ALREADY_EXISTS"

    def __init__(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> None:
        self.organization_id = organization_id
        self.user_id = user_id

        super().__init__(
            f"用户“{user_id}”已经属于组织“{organization_id}”"
        )


class OrganizationMembershipNotFoundError(
    ApplicationError
):
    """指定用户不属于指定组织。"""

    error_code = "ORGANIZATION_MEMBERSHIP_NOT_FOUND"

    def __init__(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> None:
        self.organization_id = organization_id
        self.user_id = user_id

        super().__init__(
            f"用户“{user_id}”不属于组织“{organization_id}”"
        )


class InvalidCredentialsError(
    ApplicationError
):
    """邮箱或密码错误。"""

    error_code = "INVALID_CREDENTIALS"

    def __init__(self) -> None:
        # 不明确告诉前端到底是邮箱不存在，
        # 还是密码错误，避免泄露用户是否存在。
        super().__init__(
            "邮箱或密码错误"
        )


class InactiveUserError(
    ApplicationError
):
    """用户账号已被停用。"""

    error_code = "USER_INACTIVE"

    def __init__(
        self,
        user_id: UUID,
    ) -> None:
        self.user_id = user_id

        super().__init__(
            "用户账号已被停用"
        )

class OrganizationAccessDeniedError(
    ApplicationError
):
    """当前用户无权访问指定组织或执行当前操作。"""

    error_code = "ORGANIZATION_ACCESS_DENIED"

    def __init__(
        self,
        organization_id: UUID,
    ) -> None:
        self.organization_id = organization_id

        super().__init__(
            f"没有权限访问组织“{organization_id}”"
        )

class TicketNotFoundError(
    ApplicationError
):
    """指定组织中没有找到对应工单。"""

    error_code = "TICKET_NOT_FOUND"

    def __init__(
        self,
        organization_id: UUID,
        ticket_id: UUID,
    ) -> None:
        # 保存组织ID和工单ID，方便日志排查。
        self.organization_id = organization_id
        self.ticket_id = ticket_id

        super().__init__(
            f"组织“{organization_id}”中不存在工单“{ticket_id}”"
        )


class TicketAssigneeNotOrganizationMemberError(
    ApplicationError
):
    """指定的工单处理人员不属于当前组织。"""

    error_code = (
        "TICKET_ASSIGNEE_NOT_ORGANIZATION_MEMBER"
    )

    def __init__(
        self,
        organization_id: UUID,
        assignee_user_id: UUID,
    ) -> None:
        self.organization_id = organization_id
        self.assignee_user_id = assignee_user_id

        super().__init__(
            f"用户“{assignee_user_id}”"
            f"不属于组织“{organization_id}”，"
            "不能处理该组织的工单"
        )


class InvalidTicketStatusTransitionError(
    ApplicationError
):
    """工单不能从当前状态直接修改成目标状态。"""

    error_code = "INVALID_TICKET_STATUS_TRANSITION"

    def __init__(
        self,
        current_status: str,
        target_status: str,
    ) -> None:
        self.current_status = current_status
        self.target_status = target_status

        super().__init__(
            f"工单不能从“{current_status}”"
            f"直接修改为“{target_status}”"
        )


class TicketAccessDeniedError(
    ApplicationError
):
    """当前用户无权查看或操作指定工单。"""

    error_code = "TICKET_ACCESS_DENIED"

    def __init__(
        self,
        ticket_id: UUID,
    ) -> None:
        self.ticket_id = ticket_id

        super().__init__(
            f"没有权限访问工单“{ticket_id}”"
        )

class TicketAssigneeRoleNotAllowedError(
    ApplicationError
):
    """指定用户的组织角色不能处理工单。"""

    error_code = "TICKET_ASSIGNEE_ROLE_NOT_ALLOWED"

    def __init__(
        self,
        assignee_user_id: UUID,
    ) -> None:
        self.assignee_user_id = assignee_user_id

        super().__init__(
            f"用户“{assignee_user_id}”"
            "不是技术支持人员或组织管理员，"
            "不能被设置为工单处理人"
        )

class DocumentNotFoundError(
    ApplicationError
):
    """指定组织中没有找到对应文档。"""

    error_code = "DOCUMENT_NOT_FOUND"

    def __init__(
        self,
        organization_id: UUID,
        document_id: UUID,
    ) -> None:
        self.organization_id = organization_id
        self.document_id = document_id

        super().__init__(
            f"组织“{organization_id}”中"
            f"不存在文档“{document_id}”"
        )


class UnsupportedDocumentTypeError(
    ApplicationError
):
    """上传的文件类型不受支持。"""

    error_code = "UNSUPPORTED_DOCUMENT_TYPE"

    def __init__(
        self,
        content_type: str,
    ) -> None:
        self.content_type = content_type

        super().__init__(
            f"不支持文件类型“{content_type}”，"
            "当前只允许上传PDF、Word、TXT和Markdown文档"
        )


class DocumentFileTooLargeError(
    ApplicationError
):
    """上传的文档超过大小限制。"""

    error_code = "DOCUMENT_FILE_TOO_LARGE"

    def __init__(
        self,
        file_size_bytes: int,
        max_size_bytes: int,
    ) -> None:
        self.file_size_bytes = file_size_bytes
        self.max_size_bytes = max_size_bytes

        # 把字节转换成MB，方便用户理解。
        file_size_mb = (
            file_size_bytes / 1024 / 1024
        )
        max_size_mb = (
            max_size_bytes / 1024 / 1024
        )

        super().__init__(
            f"文件大小为{file_size_mb:.2f}MB，"
            f"超过最大限制{max_size_mb:.2f}MB"
        )


class EmptyDocumentFileError(
    ApplicationError
):
    """上传的文档内容为空。"""

    error_code = "EMPTY_DOCUMENT_FILE"

    def __init__(self) -> None:
        super().__init__(
            "上传的文档内容不能为空"
        )


class DuplicateDocumentError(
    ApplicationError
):
    """当前组织已经上传过内容完全相同的文档。"""

    error_code = "DUPLICATE_DOCUMENT"

    def __init__(
        self,
        existing_document_id: UUID,
    ) -> None:
        self.existing_document_id = (
            existing_document_id
        )

        super().__init__(
            "当前组织已经存在内容完全相同的文档，"
            f"已有文档ID为“{existing_document_id}”"
        )

# RustFS连接或文件操作失败
# 如：RustFS容器没有启动，地址或端口配置错误，账号或密码错误。。。。。
class ObjectStorageUnavailableError(
    ApplicationError
):
    """对象存储当前无法完成文件操作。"""

    error_code = "OBJECT_STORAGE_UNAVAILABLE"

    def __init__(self) -> None:
        # 不把底层连接地址、账号或SDK错误返回给客户端，
        # 防止泄露内部基础设施信息。
        super().__init__(
            "文件存储服务暂时不可用，请稍后重试"
        )


class AgentLimitExceededError(RuntimeError):
    """Agent超过允许的模型轮数或工具调用次数。"""


class AgentEmptyResponseError(RuntimeError):
    """模型重试后，仍没有返回文字或工具调用。"""


class AgentConversationNotFoundError(ApplicationError):
    """当前用户在当前组织中找不到指定会话。"""

    error_code = "AGENT_CONVERSATION_NOT_FOUND"

    def __init__(
        self,
        conversation_id: UUID,
    ) -> None:
        self.conversation_id = conversation_id

        # 不区分“会话不存在”和“属于别人”，
        # 避免向当前用户泄露他人的会话信息。
        super().__init__(
            "会话不存在或无法访问"
        )


class AgentConversationConflictError(ApplicationError):
    """会话正在执行，或存在尚未完成的任务。"""

    error_code = "AGENT_CONVERSATION_CONFLICT"


class DocumentProcessingJobNotFoundError(ApplicationError):
    """在当前组织中找不到指定的文档处理任务。"""

    # 前端可以根据这个错误编码识别错误类型。
    error_code = "DOCUMENT_PROCESSING_JOB_NOT_FOUND"

    def __init__(
        self,
        job_id: UUID,
    ) -> None:
        # 保存查询失败的任务ID。
        self.job_id = job_id

        # 将错误说明交给父类保存。
        super().__init__(
            f"文档处理任务不存在：{job_id}"
        )