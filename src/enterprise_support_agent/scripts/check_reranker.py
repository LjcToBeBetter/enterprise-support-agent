"""
Rerank模型连接测试脚本。

这个脚本只测试：

1. 能否连接阿里云百炼；
2. qwen3-rerank能否正常处理候选文本；
3. 返回的index和relevance_score是否正确。
"""

import asyncio

from enterprise_support_agent.infrastructure.reranking.dashscope_reranker import (
    DashScopeReranker,
)


async def main() -> None:
    """调用Rerank模型并打印重排序结果。"""

    query = "E1007数据库连接超时怎么处理？"

    # 模拟混合检索和RRF返回的候选文本。
    documents = [
        "机械键盘适合长时间编程，青轴声音较大。",
        (
            "错误码E1007表示数据库连接超时，"
            "请检查数据库地址、端口和网络连接。"
        ),
        (
            "错误码E2003表示用户没有访问权限，"
            "请检查用户角色和权限配置。"
        ),
    ]

    # 创建阿里云百炼Rerank客户端对象。
    reranker = DashScopeReranker()

    # 把用户问题和候选文本交给Rerank模型。
    #
    # top_n=2表示最终只返回最相关的两条结果。
    results = await reranker.rerank(
        query=query,
        documents=documents,
        top_n=2,
    )

    print(f"检索问题：{query}")
    print(f"Rerank结果数量：{len(results)}")

    for rank, result in enumerate(
        results,
        start=1,
    ):
        # document_index是模型返回的原始文本下标。
        #
        # 使用这个下标，就能重新找到完整候选文本。
        original_document = documents[
            result.document_index
        ]

        print()
        print(f"最终排名：{rank}")
        print(
            f"原始文本下标："
            f"{result.document_index}"
        )
        print(
            f"相关性分数："
            f"{result.relevance_score}"
        )
        print(f"候选文本：{original_document}")


# 普通脚本不能在最外层直接使用await，
# 所以使用asyncio.run()启动异步main()。
if __name__ == "__main__":
    asyncio.run(
        main()
    )