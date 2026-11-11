"""检查Redis连接，以及基本的键值读写功能。"""

import asyncio
from uuid import uuid4

from enterprise_support_agent.infrastructure.cache.redis_connection import (
    open_redis_connection,
)


async def main() -> None:
    """写入一条临时测试数据，读取验证后删除。"""

    # 生成独立的测试键，避免覆盖其他数据。
    # 键中的冒号只是命名习惯，方便区分用途。
    test_key = f"enterprise-support:check:redis:{uuid4()}"
    test_value = "Redis连接测试成功"

    # 进入时创建客户端并检查连接；
    # 离开时自动关闭客户端和连接池。
    async with open_redis_connection() as client:
        print("Redis连接成功")

        try:
            # set()：保存一组键和值。
            # ex=60：有效期为60秒，到期后自动删除。
            await client.set(
                test_key,
                test_value,
                ex=60,
            )
            print("测试数据已写入")

            # get()：根据键读取对应的值。
            # 因为开启了decode_responses，
            # 这里读取的文本是str，而不是bytes。
            stored_value = await client.get(test_key)
            print("读取结果：", stored_value)

            if stored_value != test_value:
                raise RuntimeError("读取结果与写入内容不一致")

            # ttl()：查看这个键还剩多少秒过期。
            # 返回-1表示没有设置有效期；
            # 返回-2表示键不存在。
            remaining_seconds = await client.ttl(test_key)
            print("剩余有效期：", remaining_seconds, "秒")

        finally:
            # 无论验证成功还是发生异常，
            # 都尝试删除本次生成的测试数据。
            await client.delete(test_key)
            print("测试数据已删除")

    print("Redis客户端已关闭")


if __name__ == "__main__":
    # asyncio.run()启动事件循环，执行异步入口main()。
    print("正在检查Redis连接……", flush=True)
    asyncio.run(main())