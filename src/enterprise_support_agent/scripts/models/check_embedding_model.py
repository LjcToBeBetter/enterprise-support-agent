"""
Embedding模型连接测试。

主要功能：

1. 向Embedding服务发送一段测试文字；
2. 取得返回的向量；
3. 打印向量维度；
4. 为创建Qdrant Collection提供真实维度。
"""

import asyncio

from enterprise_support_agent.infrastructure.embeddings.client import (
    embedding_model,
)


async def main() -> None:
    """生成一个测试向量并打印维度。"""

    test_text = (
        "数据库连接超时，请检查数据库地址和端口。"
    )

    # aembed_query()由OpenAIEmbeddings提供。
    #
    # 方法名开头的a表示async异步版本。
    #
    # 它接收一个字符串，
    # 返回这个字符串对应的一维浮点数列表。
    test_vector = await embedding_model.aembed_query(
        test_text
    )

    print(
        "Embedding调用成功"
    )

    # len()取得向量包含多少个数字，
    # 这个数量就是向量维度。
    print(
        f"向量维度：{len(test_vector)}"
    )

    # 只打印前5个数字，
    # 避免把整个向量全部输出到控制台。
    print(
        f"向量前5项：{test_vector[:5]}"
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )