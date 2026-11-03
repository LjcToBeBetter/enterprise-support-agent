"""
项目统一使用的Qdrant客户端。

主要功能：

1. 根据Settings中的配置连接Qdrant；
2. 为项目其他模块提供同一个异步客户端；
3. 后续用于创建Collection、写入向量和执行检索。
"""

from qdrant_client import (
    AsyncQdrantClient,
)

from enterprise_support_agent.config import (
    settings,
)


def create_qdrant_client() -> AsyncQdrantClient:
    """
    根据项目配置创建异步Qdrant客户端。

    这里只创建客户端对象。

    真正连接Qdrant通常发生在调用：
    get_collections()、upsert()、query_points()
    等方法时。
    """

    # AsyncQdrantClient由qdrant-client提供。
    #
    # 它的方法可以使用await调用，
    # 适合当前FastAPI异步项目。
    return AsyncQdrantClient(
        # Qdrant REST接口地址。
        #
        # 本地开发环境为：
        # http://127.0.0.1:6333
        url=settings.qdrant_url,

        # 是否优先使用gRPC。
        #
        # false使用REST；
        # true优先使用gRPC。
        prefer_grpc=(
            settings.qdrant_prefer_grpc
        ),

        # Qdrant请求超时时间。
        timeout=(
            settings.qdrant_timeout_seconds
        ),

        # 本地Qdrant没有开启认证，
        # 所以当前值为None。
        #
        # 将来连接Qdrant Cloud时，
        # 可以通过.env提供API Key。
        api_key=settings.qdrant_api_key,
    )


# 创建项目统一使用的Qdrant客户端。
#
# 其他模块不需要反复创建客户端，
# 直接导入这个对象即可。
qdrant_client = create_qdrant_client()
