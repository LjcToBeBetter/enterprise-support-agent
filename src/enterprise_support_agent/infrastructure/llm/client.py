"""
项目统一使用的聊天模型客户端。

这个对象负责连接阿里云百炼，
并调用大语言模型生成文本答案。
"""

from langchain_openai import (
    ChatOpenAI,
)

from enterprise_support_agent.config import (
    settings,
)


def create_chat_model() -> ChatOpenAI:
    """根据项目配置创建聊天模型对象。"""

    # ChatOpenAI不只能调用OpenAI官方模型。
    #
    # 只要模型服务实现了OpenAI兼容协议，
    # 就可以通过base_url连接。
    return ChatOpenAI(
        # 阿里云百炼API Key。
        api_key=settings.llm_api_key,

        # 阿里云百炼OpenAI兼容接口地址。
        base_url=settings.llm_base_url,

        # 实际使用的聊天模型。
        model=settings.llm_model_name,

        # 控制回答的随机程度。
        #
        # 数值越低，回答越稳定。
        temperature=settings.llm_temperature,

        # 单次模型请求的超时时间。
        timeout=(
            settings.llm_request_timeout_seconds
        ),

        # 请求临时失败后的最大重试次数。
        max_retries=settings.llm_max_retries,
    )


# 创建项目统一使用的聊天模型对象。
#
# 后面的RAG Service可以直接导入chat_model，
# 不需要每次回答问题时都重新创建配置。
chat_model = create_chat_model()