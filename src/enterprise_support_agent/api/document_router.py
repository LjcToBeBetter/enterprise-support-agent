"""
document_router.py

主要功能：
    定义企业知识库文档相关的HTTP接口。

主要部件：
    router：
        保存知识库文档接口。

    upload_document：
        接收客户端上传的文件；
        读取文件二进制内容；
        调用DocumentService完成上传；
        返回文档元数据。
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.auth_dependencies import (
    get_current_user,
)
from enterprise_support_agent.api.document_schemas import (
    DocumentResponse,
    DocumentListResponse,
)
from enterprise_support_agent.application.document_service import (
    DocumentService,
)
from enterprise_support_agent.infrastructure.database.models.user import (
    User,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
from enterprise_support_agent.api.organization_dependencies import (
    require_organization_admin,
)
from enterprise_support_agent.application.document_processing_service import (
    DocumentProcessingService,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)

# 把中文、空格等特殊字符转换成适合放进 URL或HTTP响应头的编码格式
from urllib.parse import quote


# 当前文件中所有接口的公共路径前缀。
router = APIRouter(
    prefix=(
        "/organizations/"
        "{organization_id}/documents"
    ),
    tags=["documents"],
)


@router.post(
    "",
    response_model=DocumentResponse,

    # 201表示成功创建了一份新的知识库文档。
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    # 从URL路径中读取组织ID。
    organization_id: UUID,

    # UploadFile由FastAPI提供，
    # 用来接收multipart/form-data上传的文件。
    #
    # File(...)表示这是一个必填的文件字段。
    # 这行代码是在告诉 FastAPI：
    # 这个接口需要客户端上传一个必填文件，文件字段名叫 file。即前端上传的文件
    # file: UploadFile = File(...)
    # 表示从 multipart/form-data 请求中读取一个名为 file 的必填上传文件，
    # 并把它包装成 UploadFile 对象。
    file: UploadFile = File(...),

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> DocumentResponse:
    """
    向指定组织的知识库上传文档。

    只有support和admin可以上传。
    """

    try:
        # read()异步读取上传文件的全部内容，
        # 返回bytes类型。
        file_content = await file.read()

        service = DocumentService(
            session=session
        )

        # filename可能为空，
        # 因此使用一个备用文件名。
        original_filename = (
            file.filename
            or "unnamed"
        )

        # content_type可能为空，
        # 因此使用通用二进制类型作为备用值。
        content_type = (
            file.content_type
            or "application/octet-stream"
        )

        document = await service.upload_document(
            organization_id=organization_id,
            uploaded_by_user_id=current_user.id,
            original_filename=original_filename,
            content_type=content_type,
            file_content=file_content,
        )

        return DocumentResponse.model_validate(
            document
        )

    finally:
        # 无论上传成功还是失败，
        # 都关闭UploadFile使用的临时文件资源。
        await file.close()



@router.get(
    "",
    response_model=DocumentListResponse,
)
async def list_documents(
    # 当前需要查询哪个组织的文档。
    organization_id: UUID,

    # 当前页码，默认第1页。
    page: int = Query(
        default=1,
        ge=1,
    ),

    # 每页默认20条，最多100条。
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> DocumentListResponse:
    """
    分页查询当前组织的知识库文档。

    当前用户只要属于该组织就可以查询。
    """

    service = DocumentService(
        session=session
    )

    documents, total, total_pages = (
        await service.list_documents(
            organization_id=organization_id,
            current_user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    )

    # 将ORM对象列表转换成响应模型列表。
    items: list[DocumentResponse] = []

    for document in documents:
        response_item = (
            DocumentResponse.model_validate(
                document
            )
        )

        items.append(
            response_item
        )

    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
async def get_document(
    # 当前文档所属组织。
    organization_id: UUID,

    # 需要查询的文档ID。
    document_id: UUID,

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> DocumentResponse:
    """
    根据文档ID查询单条文档元数据。

    这里只返回文档信息，不返回文件内容。
    """

    service = DocumentService(
        session=session
    )

    document = await service.get_document(
        organization_id=organization_id,
        document_id=document_id,
        current_user_id=current_user.id,
    )

    return DocumentResponse.model_validate(
        document
    )

@router.get(
    "/{document_id}/download",
)
async def download_document(
    # 当前文档所属组织。
    organization_id: UUID,

    # 需要下载的文档ID。
    document_id: UUID,

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> Response:
    """
    下载指定知识库文档。

    当前用户只要属于该组织就可以下载。
    """

    service = DocumentService(
        session=session
    )

    # Service返回：
    # 文件bytes、原始文件名、MIME类型。
    (
        file_content,
        filename,
        content_type,
    ) = await service.download_document(
        organization_id=organization_id,
        document_id=document_id,
        current_user_id=current_user.id,
    )

    # quote()对文件名进行URL编码，
    # 避免中文、空格等字符破坏响应头格式。
    encoded_filename = quote(
        filename
    )

    # Response把文件bytes直接放入HTTP响应体。
    return Response(
        content=file_content,

        # 告诉浏览器文件类型。
        media_type=content_type,

        headers={
            # attachment表示让浏览器下载文件，
            # 而不是直接把内容当作网页显示。
            #
            # filename*=UTF-8''表示文件名使用UTF-8编码。
            "Content-Disposition": (
                "attachment; "
                f"filename*=UTF-8''{encoded_filename}"
            ),
        },
    )


@router.delete(
    "/{document_id}",

    # 204表示删除成功，
    # 并且响应体中没有返回内容。
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    # 当前文档所属组织。
    organization_id: UUID,

    # 需要删除的文档ID。
    document_id: UUID,

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 验证JWT并取得当前登录用户。
    current_user: User = Depends(
        get_current_user
    ),
) -> Response:
    """
    删除指定知识库文档。

    只有组织admin可以删除。
    """

    service = DocumentService(
        session=session
    )

    # Service负责：
    # 权限检查；
    # 查询文档；
    # 删除RustFS文件；
    # 删除PostgreSQL元数据；
    # 提交或回滚事务。
    await service.delete_document(
        organization_id=organization_id,
        document_id=document_id,
        current_user_id=current_user.id,
    )

    # 204响应不包含JSON或其他响应体。
    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )

@router.post(
    "/{document_id}/process",

    # 204表示处理成功，
    # 但接口不返回响应体。
    status_code=status.HTTP_204_NO_CONTENT,
)
async def process_document(
    # FastAPI从URL路径中读取组织ID。
    organization_id: UUID,

    # FastAPI从URL路径中读取文档ID。
    document_id: UUID,

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 在执行接口之前，
    # FastAPI会先调用require_organization_admin。
    #
    # 它会：
    # 1. 验证JWT；
    # 2. 查询当前用户的组织成员关系；
    # 3. 确认当前用户是admin；
    # 4. 验证失败时直接返回401或403。
    #
    # 变量名前面的下划线表示：
    # 这个接口只需要完成权限检查，
    # 后面的业务代码不会直接使用这个对象。
    _admin_membership: OrganizationMembership = Depends(
        require_organization_admin
    ),
) -> Response:
    """
    手动触发知识库文档处理。

    当前只用于开发和测试。

    正式生产环境后面会改成：
    上传成功后向RabbitMQ发送处理任务，
    再由后台Worker执行文档处理。
    """

    # 创建文档处理Service。
    service = DocumentProcessingService(
        session=session
    )

    # 执行完整处理流程：
    #
    # 1. 查询文档元数据；
    # 2. status修改为processing；
    # 3. 从RustFS读取PDF；
    # 4. 提取PDF正文；
    # 5. status修改为parsed；
    # 6. 切分文本块；
    # 7. 保存到document_chunks表；
    # 8. status修改为chunked。
    await service.process_document(
        organization_id=organization_id,
        document_id=document_id,
    )

    # 处理成功后返回204，
    # 不需要额外返回JSON。
    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )