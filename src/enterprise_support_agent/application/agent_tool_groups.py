"""从本次已经授权的工具中，挑选各Agent允许使用的工具。"""

from typing import Literal

from langchain_core.tools import BaseTool


def select_agent_tools(
    available_tools: list[BaseTool],
    role: Literal["knowledge", "ticket", "general"],
) -> list[BaseTool]:
    """
    根据角色筛选工具。

    available_tools：create_agent_tools已经创建好的工具，
    其中包含本次请求允许使用的工具。

    返回：当前角色可以使用的工具列表。
    """

    # 字典的key是角色，value是允许使用的工具名称集合。
    allowed_names = {
        "knowledge": {
            "search_knowledge",
        },
        "ticket": {
            "get_ticket",
            "create_ticket",
        },
        # 普通交流不需要业务工具。
        "general": set(),
    }

    # Literal只是类型提示，运行时仍主动检查角色是否合法。
    if role not in allowed_names:
        raise ValueError(
            f"不支持的Agent角色：{role}"
        )

    selected_tools: list[BaseTool] = []

    for tool in available_tools:
        # 只挑选当前角色允许使用的工具。
        if tool.name in allowed_names[role]:
            selected_tools.append(tool)

    return selected_tools