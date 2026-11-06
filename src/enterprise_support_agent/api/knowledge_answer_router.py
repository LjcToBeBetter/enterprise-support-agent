"""
企业知识库RAG问答接口。

当前提供：

POST /organizations/{organization_id}/knowledge/answer

组织成员提交问题后，系统会：

1. 检索当前组织的知识库；
2. 使用RRF和Rerank筛选资料；
3. 调用大模型生成答案；
4. 返回答案和引用来源。
"""

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.api.knowledge_answer_schemas import (
    KnowledgeAnswerRequest,
    KnowledgeAnswerResponse,
    KnowledgeAnswerSourceResponse,
)
from enterprise_support_agent.api.organization_dependencies import (
    require_organization_member,
)
from enterprise_support_agent.application.knowledge_answer_service import (
    KnowledgeAnswerService,
)
from enterprise_support_agent.infrastructure.database.models.organization_membership import (
    OrganizationMembership,
)
from enterprise_support_agent.infrastructure.database.session import (
    get_db_session,
)
# logging是Python自带的日志模块。
# 用来记录流式回答失败的原因和异常堆栈，
# 方便我们在后端控制台排查问题。
import logging

# AsyncIterator是Python提供的类型标注。
#
# AsyncIterator[str]表示：
# 调用者可以通过async for，
# 逐段取得这个方法提供的字符串。
#
# 它只是说明类型，
# 真正交出数据的是方法内部的yield。
from collections.abc import AsyncIterator

# aclosing是Python提供的异步资源清理工具。
#
# 配合async with使用：
# 离开代码块时，自动调用异步生成器的aclose()，
# 让生成器结束并执行其中的清理逻辑。
#
# 正常完成、提前return或发生异常时，
# 都会尝试执行关闭操作。
from contextlib import aclosing


# Request由FastAPI提供，表示当前这一次HTTP请求。
#
# 接口声明request: Request后，
# FastAPI会自动传入这个请求对象。
#
# 这里用它读取：
# request.state.request_id
from fastapi import Request

# StreamingResponse是FastAPI提供的流式响应类。
#
# 普通响应通常一次返回完整内容；
# 它可以不断读取生成器yield的内容，
# 并逐段通过网络发送给前端。
from fastapi.responses import StreamingResponse

from fastapi.encoders import jsonable_encoder

from enterprise_support_agent.api.sse import (
    build_sse_event,
)

from enterprise_support_agent.application.citation_validator import (
    InvalidCitationError,
)


# getLogger()取得当前模块使用的日志记录器。
#
# __name__是Python自动提供的当前模块名称，
# 这里通常是：
# enterprise_support_agent.api.knowledge_answer_router
#
# 后面调用logger.exception(...)时，
# 会记录错误消息和异常堆栈，
# 并通过模块名称标明日志来自哪个文件。
#
# 这一行只是取得日志记录器，
# 不会立刻打印日志。
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=(
        "/organizations/"
        "{organization_id}/knowledge"
    ),
    tags=["knowledge-answer"],
)


@router.post(
    "/answer",
    response_model=KnowledgeAnswerResponse,
)
async def answer_knowledge_question(
    # FastAPI从URL路径中读取组织ID。
    organization_id: UUID,

    # FastAPI从JSON请求体中读取问题和检索参数。
    request_data: KnowledgeAnswerRequest,

    # 当前请求使用的数据库Session。
    session: AsyncSession = Depends(
        get_db_session
    ),

    # 接口执行前验证：
    #
    # 1. 用户是否已经登录；
    # 2. 用户是否属于当前组织。
    #
    # 验证失败会直接返回401或403，
    # 不会继续执行RAG问答。
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> KnowledgeAnswerResponse:
    """根据当前组织知识库生成问题答案。"""

    service = KnowledgeAnswerService(
        session=session
    )

    # 执行检索、Rerank和大模型回答生成。
    answer_result = await service.answer(
        organization_id=organization_id,
        query=request_data.query,
        candidate_top_k=(
            request_data.candidate_top_k
        ),
        rrf_top_k=request_data.rrf_top_k,
        final_top_k=request_data.final_top_k,
    )

    response_sources: list[
        KnowledgeAnswerSourceResponse
    ] = []

    # 把Service返回的普通Python对象，
    # 转换成接口规定的Pydantic响应对象。
    for source in answer_result.sources:
        response_sources.append(
            KnowledgeAnswerSourceResponse(
                source_number=(
                    source.source_number
                ),
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                document_version=(
                    source.document_version
                ),
                page_number=source.page_number,
                chunk_index=source.chunk_index,
                content=source.content,
                rerank_score=source.rerank_score,
            )
        )

    return KnowledgeAnswerResponse(
        query=answer_result.query,
        answer=answer_result.answer,
        sources=response_sources,
        used_source_count=len(
            response_sources
        ),
        no_answer=answer_result.no_answer,
    )


@router.post(
    "/answer/stream",
    response_class=StreamingResponse,
    response_model=None,
    summary="流式知识库问答",
)
async def stream_knowledge_answer(
    # 当前HTTP请求，用来读取request_id。
    request: Request,

    # 从URL读取组织ID。
    organization_id: UUID,

    # 与普通问答使用同一套请求参数。
    request_data: KnowledgeAnswerRequest,

    session: AsyncSession = Depends(
        get_db_session
    ),

    # 开始发送流之前，先检查登录和组织身份。
    # 验证失败时仍然正常返回401或403。
    _membership: OrganizationMembership = Depends(
        require_organization_member
    ),
) -> StreamingResponse:
    """逐段返回答案，完成后返回引用校验结果。"""

    service = KnowledgeAnswerService(
        session=session
    )

    request_id = getattr(
        request.state,
        "request_id",
        "unknown",
    )

    async def generate_events() -> AsyncIterator[str]:
        """
        读取Service消息，转换成SSE字符串。

        StreamingResponse会不断读取这里yield的字符串，
        并发送给客户端。
        """

        try:
            event_stream = service.stream_answer(
                organization_id=organization_id,
                query=request_data.query,
                candidate_top_k=(
                    request_data.candidate_top_k
                ),
                rrf_top_k=request_data.rrf_top_k,
                final_top_k=request_data.final_top_k,
            )

            # aclosing由Python标准库提供。
            #
            # 无论正常结束还是中途退出，
            # 离开这个代码块时都会调用生成器的aclose()，
            # 让它有机会结束并清理资源。
            async with aclosing(event_stream):
                async for event in event_stream:
                    if event.event == "delta":
                        yield build_sse_event(
                            event="delta",
                            data={
                                "text": event.text,
                            },
                        )

                    elif event.event == "done":
                        if event.result is None:
                            raise RuntimeError(
                                "完成消息缺少问答结果"
                            )

                        # jsonable_encoder由FastAPI提供。
                        #
                        # 把dataclass转换成字典，
                        # 同时将UUID等对象转换成JSON支持的值。
                        payload = jsonable_encoder(
                            event.result
                        )

                        payload["used_source_count"] = len(
                            event.result.sources
                        )

                        # 沿用普通问答的响应模型，
                        # 检查最终结果格式是否正确。
                        final_response = (
                            KnowledgeAnswerResponse
                            .model_validate(payload)
                        )

                        yield build_sse_event(
                            event="done",

                            # mode="json"确保字典里的值
                            # 都可以直接进行JSON序列化。
                            data=final_response.model_dump(
                                mode="json"
                            ),
                        )

                        return

            # 如果生成器结束了，却没有发出done，
            # 不能让前端误以为答案已经成功完成。
            raise RuntimeError(
                "流式问答结束，但没有完成消息"
            )

        except Exception as error:
            logger.exception(
                "流式知识库问答失败："
                "request_id=%s organization_id=%s",
                request_id,
                organization_id,
            )

            if isinstance(
                error,
                InvalidCitationError,
            ):
                code = "INVALID_ANSWER_CITATION"
                message = (
                    "答案引用校验失败，"
                    "请丢弃临时答案后重试"
                )
            else:
                code = "ANSWER_STREAM_FAILED"
                message = (
                    "答案生成失败，"
                    "请丢弃临时答案后重试"
                )

            # 流开始发送后，HTTP状态码已经发出，
            # 不能再改成502或500。
            #
            # 因此通过error消息告诉前端本次失败，
            # 不再返回done消息。
            yield build_sse_event(
                event="error",
                data={
                    "code": code,
                    "message": message,
                    "request_id": request_id,
                },
            )

    # StreamingResponse由FastAPI提供。
    #
    # 它逐段读取generate_events()提供的字符串，
    # 不需要等整个答案生成完才发送。
    return StreamingResponse(
        content=generate_events(),

        # 告诉客户端：响应内容是SSE事件流。
        media_type="text/event-stream",

        headers={
            # 不要缓存本次问答结果。
            "Cache-Control": "no-cache",

            # 如果经过Nginx，要求它不要攒够数据再发送。
            "X-Accel-Buffering": "no",
        },
    )