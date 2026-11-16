"""
混合检索检查脚本。

测试流程：

1. 执行向量检索；
2. 执行BM25检索；
3. 使用加权RRF融合；
4. 打印两路排名和最终分数。
"""

import asyncio
from uuid import UUID

from enterprise_support_agent.application.knowledge.hybrid_retriever import (
    HybridRetriever,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


# 当前测试数据所属的组织ID。
TEST_ORGANIZATION_ID = UUID(
    "633b0933-507f-4e9d-8364-691a39b0d5cb"
)

# 同时包含错误码和故障描述，
# 方便观察BM25和向量检索的排名。
TEST_QUERY = "E1007数据库连接超时怎么处理？"


async def main() -> None:
    """执行一次混合检索并打印结果。"""

    try:
        retriever = HybridRetriever()

        results = await retriever.search(
            organization_id=(
                TEST_ORGANIZATION_ID
            ),
            query=TEST_QUERY,

            # 每一路最多召回多少条候选。
            candidate_top_k=2,

            # RRF融合后最终留下多少条。
            final_top_k=2,

            # 两路检索暂时使用相同权重。
            vector_weight=0.5,
            bm25_weight=0.5,

            # RRF排名平滑常数。
            rrf_k=60,
        )

        print(
            f"检索问题：{TEST_QUERY}"
        )
        print(
            f"最终结果数量：{len(results)}"
        )

        for rank, result in enumerate(
            results,
            start=1,
        ):
            print()
            print(
                f"最终排名：{rank}"
            )
            print(
                f"文本块ID：{result.chunk_id}"
            )
            print(
                f"RRF分数：{result.rrf_score}"
            )
            print(
                f"向量排名：{result.vector_rank}"
            )
            print(
                f"向量原始分数："
                f"{result.vector_score}"
            )
            print(
                f"BM25排名：{result.bm25_rank}"
            )
            print(
                f"BM25原始分数："
                f"{result.bm25_score}"
            )

    finally:
        # 关闭Qdrant客户端的网络连接。
        await qdrant_client.close()


if __name__ == "__main__":
    asyncio.run(
        main()
    )