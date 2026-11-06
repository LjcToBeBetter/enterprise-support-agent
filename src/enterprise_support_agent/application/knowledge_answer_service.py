"""
企业知识库RAG回答服务。

完整流程：

1. 根据用户问题执行混合检索；
2. 使用RRF和Rerank筛选文本块；
3. 把文本块整理成带编号的知识库资料；
4. 调用聊天模型生成答案；
5. 返回答案和引用来源。
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_support_agent.application.knowledge_search_service import (
    KnowledgeSearchService,
)
from enterprise_support_agent.application.rag_prompt import (
    build_rag_messages,
)
from enterprise_support_agent.infrastructure.llm.client import (
    chat_model,
)
from enterprise_support_agent.config import (
    settings,
)
import logging

from enterprise_support_agent.application.citation_validator import (
    InvalidCitationError,
    validate_answer_citations,
)
from collections.abc import AsyncIterator
from typing import Literal

from enterprise_support_agent.infrastructure.llm.streaming import (
    stream_chat_text,
)

logger = logging.getLogger(__name__)


@dataclass(
    frozen=True,
    slots=True,
)
class KnowledgeAnswerSource:
    """生成答案时使用的一条知识库来源。"""

    # 对应回答中的[资料1]、[资料2]。
    source_number: int

    chunk_id: UUID
    document_id: UUID
    document_version: int
    page_number: int
    chunk_index: int

    # 交给大模型的文本块正文。
    content: str

    # Rerank计算的相关性分数。
    #
    # 如果Rerank服务失败并使用RRF降级结果，
    # 这里就是None。
    rerank_score: float | None


@dataclass(
    frozen=True,
    slots=True,
)
class KnowledgeAnswerResult:
    """一次RAG问答的完整结果。"""

    query: str

    # 大模型根据知识库生成的最终回答。
    answer: str

    # 生成答案时使用了哪些知识库文本块。
    sources: list[KnowledgeAnswerSource]

    # 是否因为没有检索到资料而直接返回无法回答。
    no_answer: bool

@dataclass(
    frozen=True,
    slots=True,
)
class KnowledgeAnswerEvent:
    """流式问答过程中交给上层的一条消息。"""

    # Literal表示这里只允许使用这两个字符串。
    event: Literal["delta", "done"]

    # delta消息携带的新文字。
    text: str | None = None

    # done消息携带的完整问答结果。
    result: KnowledgeAnswerResult | None = None

class KnowledgeAnswerService:
    """负责执行检索并生成最终知识库答案。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """创建RAG回答服务。"""

        # 复用已经完成的混合检索和Rerank能力。
        self.search_service = KnowledgeSearchService(
            session=session
        )

    # “准备知识库资料”
    async def _prepare_context(
        self,
        organization_id: UUID,
        query: str,
        candidate_top_k: int,
        rrf_top_k: int,
        final_top_k: int,
    ) -> tuple[str, list[KnowledgeAnswerSource]]:
        """
        检索资料并整理成模型需要的上下文。

        返回两个值：

        第一个：带[资料N]编号的正文字符串。
        第二个：对应的来源对象列表。

        这个方法只准备资料，不调用聊天模型。
        """

        search_results = await self.search_service.search(
            organization_id=organization_id,
            query=query,
            candidate_top_k=candidate_top_k,
            rrf_top_k=rrf_top_k,
            final_top_k=final_top_k,
        )

        context_parts: list[str] = []
        sources: list[KnowledgeAnswerSource] = []

        for result in search_results:
            # 有Rerank分数且分数过低时，跳过。
            #
            # None表示使用RRF降级结果，
            # 沿用当前逻辑，暂时保留。
            if (
                result.rerank_score is not None
                and result.rerank_score
                < settings.rag_min_rerank_score
            ):
                continue

            # 只对保留下来的资料编号。
            #
            # 已有0条时，下一条编号为1；
            # 已有1条时，下一条编号为2。
            source_number = len(sources) + 1

            context_parts.append(
                f"[资料{source_number}]\n"
                f"文档ID：{result.document_id}\n"
                f"文档版本：{result.document_version}\n"
                f"页码：{result.page_number}\n"
                f"正文：\n{result.content}"
            )

            sources.append(
                KnowledgeAnswerSource(
                    source_number=source_number,
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    document_version=(
                        result.document_version
                    ),
                    page_number=result.page_number,
                    chunk_index=result.chunk_index,
                    content=result.content,
                    rerank_score=result.rerank_score,
                )
            )

        # 把不同资料连接成一个字符串。
        #
        # 没有合格资料时：
        # context是空字符串，sources是空列表。
        context = "\n\n".join(context_parts)

        # 返回一个包含两个值的元组。
        return context, sources

    async def answer(
        self,
        organization_id: UUID,
        query: str,
        candidate_top_k: int = 20,
        rrf_top_k: int = 20,
        final_top_k: int = 5,
    ) -> KnowledgeAnswerResult:
        """根据当前组织知识库生成答案。"""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "知识库问题不能为空"
            )

        # 调用公共方法准备资料。
        #
        # await等待方法完成后，
        # 将返回的两个值分别赋给context和sources。
        context, sources = await self._prepare_context(
            organization_id=organization_id,
            query=normalized_query,
            candidate_top_k=candidate_top_k,
            rrf_top_k=rrf_top_k,
            final_top_k=final_top_k,
        )

        # 没有合格资料时直接拒答，
        # 不调用聊天模型。
        if not sources:
            return KnowledgeAnswerResult(
                query=normalized_query,
                answer=(
                    "根据当前知识库内容，无法确定。"
                ),
                sources=[],
                no_answer=True,
            )

        # 第三步：
        # 创建system消息和user消息。
        messages = build_rag_messages(
            query=normalized_query,
            context=context,
        )

        # 第四步：
        # 保存本次允许引用的资料编号。
        #
        # 例如只有两条资料时：
        # allowed_source_numbers就是{1, 2}。
        allowed_source_numbers: set[int] = set()

        # 保存“资料编号 → 来源对象”的对应关系，
        # 后面根据引用编号找到真正的来源。
        sources_by_number: dict[
            int,
            KnowledgeAnswerSource,
        ] = {}

        for source in sources:
            allowed_source_numbers.add(
                source.source_number
            )

            sources_by_number[
                source.source_number
            ] = source

        # 预先准备两个变量。
        answer_text = ""
        cited_numbers: list[int] = []

        # 最多生成两次答案：
        #
        # 第一次正常生成；
        # 如果引用编号不正确，再生成一次。
        for attempt in range(2):
            model_response = await chat_model.ainvoke(
                messages
            )

            answer_content = model_response.content

            if not isinstance(answer_content, str):
                raise RuntimeError(
                    "聊天模型返回了无法识别的内容格式"
                )

            answer_text = answer_content.strip()

            if not answer_text:
                raise RuntimeError(
                    "聊天模型返回了空答案"
                )

            # 只有答案完整等于这个固定句子，
            # 才认为模型明确拒答。
            #
            # 不能只判断答案是否“包含”这句话，
            # 否则其他内容可能绕过引用检查。
            if answer_text == (
                    "根据当前知识库内容，无法确定。"
            ):
                return KnowledgeAnswerResult(
                    query=normalized_query,
                    answer=answer_text,
                    sources=[],
                    no_answer=True,
                )

            try:
                # 检查引用是否存在，
                # 并取得去重后的实际引用编号。
                cited_numbers = (
                    validate_answer_citations(
                        answer=answer_text,
                        allowed_source_numbers=(
                            allowed_source_numbers
                        ),
                    )
                )

            except InvalidCitationError as error:
                # 只记录错误原因，
                # 不把完整答案和资料写入日志。
                logger.warning(
                    "RAG引用校验失败："
                    "organization_id=%s "
                    "attempt=%s reason=%s",
                    organization_id,
                    attempt + 1,
                    str(error),
                )

                if attempt == 1:
                    # 第二次仍然失败，
                    # 把异常交给统一异常处理器。
                    raise

                # append()向消息列表末尾增加一条消息。
                #
                # 第二次调用模型时，
                # 会带上这条更加明确的要求。
                #
                # 不传入有问题的旧答案，
                # 让模型重新根据原资料生成。
                messages.append(
                    (
                        "user",
                        "请重新生成答案。"
                        "每条事实和建议都要使用"
                        "本次提供的[资料N]编号引用。"
                        "不得引用不存在的编号。"
                        "资料不足时，只返回："
                        "根据当前知识库内容，无法确定。",
                    )
                )

            else:
                # else表示try中的校验没有抛出异常。
                #
                # break结束整个for循环，
                # 不再调用第二次模型。
                break

        # 只返回答案实际引用的资料。
        #
        # 例如给模型提供了资料1、2、3，
        # 答案只引用资料2，
        # 那么sources中只返回资料2。
        cited_sources: list[
            KnowledgeAnswerSource
        ] = []

        for source_number in cited_numbers:
            cited_sources.append(
                sources_by_number[source_number]
            )

        return KnowledgeAnswerResult(
            query=normalized_query,
            answer=answer_text,
            sources=cited_sources,
            no_answer=False,
        )

    async def stream_answer(
        self,
        organization_id: UUID,
        query: str,
        candidate_top_k: int = 20,
        rrf_top_k: int = 20,
        final_top_k: int = 5,
    ) -> AsyncIterator[KnowledgeAnswerEvent]:
        """
        执行流式RAG问答。

        生成过程中提供delta消息；
        生成结束并通过引用校验后提供done消息。

        如果引用检查失败，抛出InvalidCitationError，
        后面由流式Router转换成error消息。
        """

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "知识库问题不能为空"
            )

        # 复用公共方法：
        # 检索、过滤、编号并拼接资料。
        context, sources = await self._prepare_context(
            organization_id=organization_id,
            query=normalized_query,
            candidate_top_k=candidate_top_k,
            rrf_top_k=rrf_top_k,
            final_top_k=final_top_k,
        )

        # 没有资料时，不调用模型。
        # 直接提供一个已完成的拒答结果。
        if not sources:
            yield KnowledgeAnswerEvent(
                event="done",
                result=KnowledgeAnswerResult(
                    query=normalized_query,
                    answer=(
                        "根据当前知识库内容，无法确定。"
                    ),
                    sources=[],
                    no_answer=True,
                ),
            )

            # yield只暂停函数，
            # return才会在这里提前结束，
            # 防止继续执行后面的模型调用。
            return

        messages = build_rag_messages(
            query=normalized_query,
            context=context,
        )

        text_parts: list[str] = []

        # 模型每生成一段，就交给上层一段。
        async for text in stream_chat_text(messages):
            # 保存副本，结束后需要检查完整答案。
            text_parts.append(text)

            yield KnowledgeAnswerEvent(
                event="delta",
                text=text,
            )

        # 模型生成结束，把片段拼成完整答案。
        answer_text = "".join(text_parts).strip()

        if not answer_text:
            raise RuntimeError(
                "聊天模型返回了空答案"
            )

        # 模型认为资料不足，明确拒答。
        if answer_text == (
            "根据当前知识库内容，无法确定。"
        ):
            yield KnowledgeAnswerEvent(
                event="done",
                result=KnowledgeAnswerResult(
                    query=normalized_query,
                    answer=answer_text,
                    sources=[],
                    no_answer=True,
                ),
            )

            return

        allowed_source_numbers: set[int] = set()

        sources_by_number: dict[
            int,
            KnowledgeAnswerSource,
        ] = {}

        for source in sources:
            allowed_source_numbers.add(
                source.source_number
            )

            sources_by_number[
                source.source_number
            ] = source

        # 这里检查完整答案中的引用。
        #
        # 如果检查失败，会直接抛出异常，
        # 后面的done消息不会发出。
        cited_numbers = validate_answer_citations(
            answer=answer_text,
            allowed_source_numbers=(
                allowed_source_numbers
            ),
        )

        # 只保留答案实际引用的来源。
        cited_sources: list[
            KnowledgeAnswerSource
        ] = []

        for source_number in cited_numbers:
            cited_sources.append(
                sources_by_number[source_number]
            )

        # 只有通过引用检查，
        # 才提供正式完成的问答结果。
        yield KnowledgeAnswerEvent(
            event="done",
            result=KnowledgeAnswerResult(
                query=normalized_query,
                answer=answer_text,
                sources=cited_sources,
                no_answer=False,
            ),
        )