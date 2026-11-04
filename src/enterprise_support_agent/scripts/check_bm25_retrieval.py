"""
Qdrant BM25检索检查脚本。

运行后会：

1. 使用测试问题查询content全文索引；
2. 只查询指定组织的数据；
3. 打印命中的文本块ID和BM25分数；
4. 验证BM25全文检索能否正常工作。
"""

import asyncio
from uuid import UUID

from enterprise_support_agent.infrastructure.vector_store.document_chunk_bm25_retriever import (
    DocumentChunkBm25Retriever,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


# 当前本地测试数据所属的组织ID。
# # 这里只用于检查脚本，不参与正式业务接口。
TEST_ORGANIZATION_ID = UUID(
    "633b0933-507f-4e9d-8364-691a39b0d5cb"
)

# 使用包含错误码和故障描述的查询，
# 检查BM25是否能够匹配精确关键词。
TEST_QUERY = "E1007 数据库连接超时"


async def main() -> None:
    """执行一次BM25关键词检索并打印结果。"""

    try:
        retriever = (
            DocumentChunkBm25Retriever()
        )

        results = await retriever.search(
            organization_id=(
                TEST_ORGANIZATION_ID
            ),
            query=TEST_QUERY,
            top_k=5,
        )

        print(
            f"检索问题：{TEST_QUERY}"
        )
        print(
            f"命中数量：{len(results)}"
        )

        # enumerate()在遍历结果时同时生成排名。
        # start=1表示排名从1开始，而不是从0开始。
        for rank, result in enumerate(
            results,
            start=1,
        ):
            print()
            print(
                f"排名：{rank}"
            )
            print(
                f"文本块ID：{result.chunk_id}"
            )
            print(
                f"BM25分数：{result.score}"
            )

    finally:
        # 无论检索成功还是失败，
        # 都关闭Qdrant客户端的网络连接。
        await qdrant_client.close()


if __name__ == "__main__":
    # 普通Python脚本不能直接在最外层使用await，
    # 因此通过asyncio.run()执行异步main()。
    asyncio.run(
        main()
    )
