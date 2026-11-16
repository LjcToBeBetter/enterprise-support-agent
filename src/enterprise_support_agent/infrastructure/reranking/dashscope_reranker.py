"""
阿里云百炼Rerank客户端。

这个类负责：

1. 接收用户问题和候选文本；
2. 使用HTTP请求调用qwen3-rerank模型；
3. 读取模型返回的文本下标和相关性分数；
4. 转换成项目内部统一的RerankResult。
"""

import asyncio

import httpx

from enterprise_support_agent.application.knowledge.reranker import (
    Reranker,
    RerankResult,
)
from enterprise_support_agent.config import settings


class RerankServiceError(RuntimeError):
    """调用Rerank服务失败时抛出的异常。"""


class DashScopeReranker(Reranker):
    """使用阿里云百炼qwen3-rerank实现文本重排序。"""

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[RerankResult]:
        """调用Rerank模型，对候选文本重新排序。"""

        # 删除问题首尾多余的空格。
        # Rerank` 的 query 一般就是用户的原问题。
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Rerank查询问题不能为空")

        # 没有候选文本时，不需要调用模型。
        if not documents:
            return []

        if top_n <= 0:
            raise ValueError("top_n必须大于0")

        # 限制单次交给Rerank模型的候选数量，
        # 防止请求过大或者费用失控。
        limited_documents = documents[
            :settings.rerank_max_documents
        ]

        prepared_documents: list[str] = []

        for document in limited_documents:
            # 限制每条候选文本的长度。
            prepared_document = document[
                :settings.rerank_max_document_characters
            ]

            prepared_documents.append(
                prepared_document
            )

        # 最终返回数量不能超过实际候选数量。
        actual_top_n = min(
            top_n,
            len(prepared_documents),
        )

        # 这是要发送给阿里云百炼的JSON请求体。
        request_body = {
            "model": settings.rerank_model_name,
            "query": normalized_query,
            "documents": prepared_documents,
            "top_n": actual_top_n,

            # 不让接口重复返回文档正文，
            # 因为正文已经保存在prepared_documents中。
            "return_documents": False,
        }

        # 返回的是阿里云 Rerank 接口返回的 JSON 请求结果
        response_body = await self._post_with_retry(
            request_body
        )

        # 提炼出结果
        raw_results = self._extract_results(
            response_body
        )

        rerank_results: list[RerankResult] = []

        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                raise RerankServiceError(
                    "Rerank返回的结果格式不正确"
                )

            document_index = raw_result.get("index")
            relevance_score = raw_result.get(
                "relevance_score"
            )

            if not isinstance(document_index, int):
                raise RerankServiceError(
                    "Rerank结果缺少有效的index"
                )

            if not isinstance(
                relevance_score,
                (int, float),
            ):
                raise RerankServiceError(
                    "Rerank结果缺少有效的"
                    "relevance_score"
                )

            # index代表这条结果对应输入列表中的哪篇文本。
            #
            # 例如index=1表示：
            # prepared_documents[1]
            if (
                document_index < 0
                or document_index
                >= len(prepared_documents)
            ):
                raise RerankServiceError(
                    "Rerank返回了越界的文档下标"
                )

            rerank_results.append(
                RerankResult(
                    document_index=document_index,
                    relevance_score=float(
                        relevance_score
                    ),
                )
            )

        return rerank_results

    async def _post_with_retry(
        self,
        request_body: dict[str, object],
    ) -> dict[str, object]:
        """发送HTTP请求，临时失败时自动重试。"""

        request_headers = {
            # Bearer后面放的是阿里云百炼API Key。
            "Authorization": (
                f"Bearer {settings.rerank_api_key}"
            ),
            "Content-Type": "application/json",
        }

        # AsyncClient是httpx提供的异步HTTP客户端。
        #
        # async with结束后会自动关闭网络连接，
        # 不需要我们手动调用close。
        async with httpx.AsyncClient(
            timeout=(
                settings
                .rerank_request_timeout_seconds
            )
        ) as client:
            # 最大重试次数为2时，
            # 总共最多发送3次：第一次加两次重试。
            total_attempts = (
                settings.rerank_max_retries + 1
            )

            for attempt in range(total_attempts):
                try:
                    response = await client.post(
                        settings.rerank_api_url,
                        headers=request_headers,
                        json=request_body,
                    )

                    # 如果HTTP状态码是400、401、500等，
                    # 这里会抛出HTTPStatusError。
                    response.raise_for_status()

                    response_body = response.json()

                    if not isinstance(
                        response_body,
                        dict,
                    ):
                        raise RerankServiceError(
                            "Rerank接口返回的不是JSON对象"
                        )

                    return response_body

                except httpx.HTTPStatusError as error:
                    status_code = (
                        error.response.status_code
                    )

                    # 429表示请求过于频繁；
                    # 5xx通常表示服务端临时异常。
                    #
                    # 这些错误可以稍后重试。
                    retryable_status_codes = {
                        429,
                        500,
                        502,
                        503,
                        504,
                    }

                    if (
                        status_code
                        not in retryable_status_codes
                    ):
                        raise RerankServiceError(
                            "Rerank请求失败，"
                            f"HTTP状态码：{status_code}，"
                            "响应内容："
                            f"{error.response.text[:500]}"
                        ) from error

                    last_error = error

                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                ) as error:
                    # 超时或者临时网络故障允许重试。
                    last_error = error

                # 当前已经是最后一次尝试，
                # 不再等待，直接结束循环。
                if attempt == total_attempts - 1:
                    break

                # 第一次失败等待1秒，
                # 第二次失败等待2秒。
                wait_seconds = 2 ** attempt

                await asyncio.sleep(wait_seconds)

        raise RerankServiceError(
            "多次尝试后仍然无法调用Rerank服务"
        ) from last_error

    @staticmethod
    def _extract_results(
        response_body: dict[str, object],
    ) -> list[object]:
        """从百炼响应中取出真正的排序结果列表。"""

        # OpenAI兼容接口可能直接返回：
        #
        # {
        #     "results": [...]
        # }
        raw_results = response_body.get("results")

        if isinstance(raw_results, list):
            return raw_results

        # DashScope接口通常返回：
        #
        # {
        #     "output": {
        #         "results": [...]
        #     }
        # }
        output = response_body.get("output")

        if isinstance(output, dict):
            raw_results = output.get("results")

            if isinstance(raw_results, list):
                return raw_results

        raise RerankServiceError(
            "Rerank响应中没有找到results列表"
        )