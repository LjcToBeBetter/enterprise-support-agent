"""
项目统一使用的Embedding客户端。

主要功能：

1. 读取Settings中的Embedding配置；
2. 创建OpenAI兼容的Embedding调用对象；
3. 为文本块和用户问题生成向量。
"""

from langchain_openai import (
    OpenAIEmbeddings,
)

from enterprise_support_agent.config import (
    settings,
)


def create_embedding_model() -> OpenAIEmbeddings:
    """根据项目配置创建Embedding调用对象。"""

    # OpenAIEmbeddings不只可以调用OpenAI官方接口，
    # 也可以调用实现了OpenAI兼容协议的Embedding服务。
    return OpenAIEmbeddings(
        # Embedding服务的API密钥。
        api_key=settings.embed_api_key,

        # OpenAI兼容接口地址。
        base_url=settings.embed_base_url,

        # 使用哪个Embedding模型。
        model=settings.embed_model_name,

        # 单次请求超时时间。
        request_timeout=(
            settings.embed_request_timeout_seconds
        ),

        # 请求失败后的最大重试次数。
        max_retries=settings.embed_max_retries,

        # 一次最多发送多少条文本。
        chunk_size=settings.embed_batch_size,

        # 不让LangChain使用本地Tokenizer
        # 自动检查文本长度。
        #
        # 当前使用的是OpenAI兼容服务，
        # 本地Tokenizer不一定认识这个模型。
        check_embedding_ctx_length=False,
    )


# 创建项目统一使用的Embedding对象。
embedding_model = create_embedding_model()