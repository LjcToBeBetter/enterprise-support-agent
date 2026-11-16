"""
手动测试知识库检索工具。

本次不让聊天模型选择工具，
直接调用工具对象的ainvoke()方法。
"""

import asyncio
from uuid import UUID

from enterprise_support_agent.application.agent.agent_context import (
    AgentContext,
)
from enterprise_support_agent.application.agent.tools.agent_tools import (
    create_knowledge_search_tool,
)
from enterprise_support_agent.infrastructure.database.session import (
    async_session_factory,
    engine,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


async def main() -> None:
    """创建工具，执行检索并打印结果。"""

    try:
        # 这里只是本地测试，手动输入身份。
        #
        # 正式接口中，身份必须由后端验证后提供，
        # 不能让模型或前端随意指定当前用户。
        organization_id = UUID(
            input("请输入组织ID：").strip()
        )

        user_id = UUID(
            input("请输入该组织内的用户ID：").strip()
        )

        context = AgentContext(
            organization_id=organization_id,
            current_user_id=user_id,
        )

        # 创建数据库会话。
        # 离开async with代码块时，自动关闭会话。
        async with async_session_factory() as session:
            # 创建绑定当前身份和Session的工具。
            # 这一步还没有执行检索。
            knowledge_tool = create_knowledge_search_tool(
                session=session,
                context=context,
            )

            # name和description是工具对象的属性，
            # 后面模型会通过这些信息认识工具。
            print("工具名称：", knowledge_tool.name)
            print("工具说明：", knowledge_tool.description)

            # ainvoke()是LangChain工具提供的
            # 异步执行方法。
            #
            # 这次调用的是“工具”，不是聊天模型。
            #
            # 它先用KnowledgeSearchToolInput校验参数，
            # 再执行工具内部的异步检索函数。
            result = await knowledge_tool.ainvoke(
                {
                    "query": "E1007数据库连接超时怎么处理？",
                    "top_k": 2,
                }
            )

            # 工具函数返回字典，
            # 所以这里通过字典key读取结果。
            print()
            print("查询问题：", result["query"])
            print("返回数量：", result["returned_count"])

            for item in result["items"]:
                print()
                print("文档ID：", item["document_id"])
                print("页码：", item["page_number"])
                print("正文：", item["content"])

    finally:
        # 测试脚本结束时释放外部连接。
        #
        # 即使Qdrant关闭失败，
        # 也要继续清理数据库连接池。
        try:
            await qdrant_client.close()
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())