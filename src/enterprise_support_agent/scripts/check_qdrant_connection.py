"""
Qdrant连接检查脚本。

主要功能：

1. 使用项目统一的异步Qdrant客户端；
2. 请求Qdrant中的Collection列表；
3. 验证Python项目能否正常连接Qdrant；
4. 使用完成后关闭客户端连接。
"""

import asyncio

from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


async def main() -> None:
    """
    检查Qdrant连接。

    async表示这是一个异步方法，
    方法内部可以使用await等待Qdrant返回结果。
    """

    try:
        # get_collections()由AsyncQdrantClient提供。
        #
        # 它会向Qdrant发送请求，
        # 查询当前实例中已经存在的所有Collection。
        #
        # 这里执行时才会真正访问：
        # http://127.0.0.1:6333
        response = await qdrant_client.get_collections()

        print(
            "Qdrant连接成功"
        )

        # response.collections是Collection列表。
        #
        # 当前还没有创建Collection，
        # 所以数量应该是0。
        print(
            f"Collection数量："
            f"{len(response.collections)}"
        )

        # 依次打印已有Collection名称。
        #
        # 如果列表为空，for循环不会执行。
        for collection in response.collections:
            print(
                f"Collection：{collection.name}"
            )

    finally:
        # close()关闭Qdrant客户端使用的网络连接。
        #
        # finally表示：
        # 无论请求成功还是发生异常，
        # 都会执行关闭操作。
        await qdrant_client.close()


# asyncio.run()负责：
#
# 1. 创建异步事件循环；
# 2. 执行main()；
# 3. 等待main()完成；
# 4. 关闭事件循环。
#
# 普通Python脚本不能在最外层直接写await，
# 所以使用asyncio.run()启动异步方法。
if __name__ == "__main__":
    asyncio.run(
        main()
    )