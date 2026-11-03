"""
创建或检查Qdrant知识库Collection。

运行这个脚本会：

1. 连接Qdrant；
2. 检查Collection是否存在；
3. 不存在时创建Collection；
4. 创建缺失的Payload索引；
5. 打印检查结果；
6. 关闭Qdrant客户端。
"""

import asyncio

from enterprise_support_agent.config import (
    settings,
)
from enterprise_support_agent.infrastructure.vector_store.collection_manager import (
    QdrantCollectionManager,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


async def main() -> None:
    """创建或检查知识库文本块Collection。"""

    try:
        # 创建Collection管理器。
        manager = QdrantCollectionManager()

        # ensure表示“确保它存在”。
        #
        # 不存在：
        #     创建Collection并返回True。
        #
        # 已经存在：
        #     检查配置并返回False。
        created = (
            await manager
            .ensure_document_chunks_collection()
        )

        if created:
            print(
                "Qdrant Collection创建成功"
            )
        else:
            print(
                "Qdrant Collection已经存在，"
                "配置检查通过"
            )

        print(
            f"Collection名称："
            f"{settings.qdrant_collection_name}"
        )

        print(
            f"向量维度："
            f"{settings.qdrant_vector_size}"
        )

        print(
            "距离算法：Cosine"
        )

    finally:
        # 无论创建成功还是出现异常，
        # 都关闭客户端使用的网络连接。
        await qdrant_client.close()


# 普通Python脚本不能直接在最外层使用await，
# 因此使用asyncio.run()启动异步main()。
if __name__ == "__main__":
    asyncio.run(
        main()
    )