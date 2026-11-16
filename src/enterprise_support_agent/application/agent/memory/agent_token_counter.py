"""
估算Agent输入上下文的Token数量。

统计内容包括：
对话消息、工具调用参数、工具返回结果、
工具名称、说明和参数格式。

这里只做估算，不调用模型，也不修改消息。
"""

from langchain_core.messages import BaseMessage

# LangChain提供的近似Token计数方法。
#
# approximately表示“大约、近似”。
# 它通过字符数量等信息估算Token，
# 不会请求模型API，不产生模型调用费用。
from langchain_core.messages.utils import (
    count_tokens_approximately,
)

from langchain_core.tools import BaseTool


def estimate_context_tokens(
    messages: list[BaseMessage],
    tools: list[BaseTool] | None = None,
) -> int:
    """
    估算本次发送给模型的输入Token数。

    messages：
        准备发送的对话消息。

    tools：
        准备提供给模型的工具。
        不传时，只统计消息。

    返回：
        估算的Token数量，整数。
    """

    return count_tokens_approximately(
        messages,

        # 默认值是约4个字符对应1个Token，
        # 更适用于常见英文文本。
        #
        # 当前主要是中文，先按1个字符对应1个Token
        # 做更保守的估算，后续通过实际usage数据校准。
        chars_per_token=1.0,

        # 每条消息除了正文，还有角色和格式开销。
        # 这里额外预留6个Token，仍然是估算值。
        extra_tokens_per_message=6.0,

        # 工具说明和参数定义也会发送给模型，
        # 不能只计算聊天正文。
        # 传入本次提供给模型的所有工具，这些工具说明也消耗输入 Token。
        # 模型收到的不是 Python 函数代码，而是：
        # - 工具名称；
        # - Docstring 工具说明；
        # - 参数名称、类型和 Field(description=...)。
        tools=tools,
    )