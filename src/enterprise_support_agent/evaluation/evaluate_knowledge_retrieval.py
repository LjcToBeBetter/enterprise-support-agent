"""逐题运行知识库检索，统计召回比例、排名得分和耗时。"""

import asyncio
from time import perf_counter
from uuid import UUID

from enterprise_support_agent.config import PROJECT_ROOT
from enterprise_support_agent.application.knowledge.knowledge_search_service import (
    KnowledgeSearchService,
)
from enterprise_support_agent.evaluation.retrieval_dataset import (
    load_retrieval_cases,
)
from enterprise_support_agent.evaluation.retrieval_metrics import (
    score_retrieval,
)
from enterprise_support_agent.infrastructure.database.session import (
    async_session_factory,
    engine,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)
from enterprise_support_agent.evaluation.retrieval_baselines import (
    retrieve_baseline_sources,
)

async def main() -> None:
    """读取题集，执行检索，并汇总每道题的评分。"""

    try:
        # 使用项目根目录定位题集，
        # 避免从不同目录运行时找错文件。
        dataset_path = (
            PROJECT_ROOT
            / "evals"
            / "knowledge_retrieval_cases.json"
        )

        cases = load_retrieval_cases(dataset_path)

        # 指定本次检索哪个组织的知识库。
        # 使用已有真实组织ID，不要填Swagger示例UUID。
        organization_id = UUID(
            input("请输入评估使用的组织ID：").strip()
        )

        # 每次运行选择一种方案。
        # vector：仅向量检索。
        # hybrid：向量＋BM25＋RRF。
        # rerank：混合检索之后，再用Rerank排序。
        strategy = input(
            "请选择方案（vector / hybrid / rerank）："
        ).strip().lower()

        if strategy not in {"vector", "hybrid", "rerank"}:
            raise ValueError("方案必须是vector、hybrid或rerank")

        print(f"本次评估方案：{strategy}")


        # 累计所有题目的得分和耗时，最后计算平均值。
        total_recall_1 = 0.0
        total_recall_5 = 0.0
        total_rr_5 = 0.0
        total_seconds = 0.0
        fallback_count = 0

        async with async_session_factory() as session:
            # 本轮不传问题向量缓存，让每道题正常生成向量。
            # 便于后面按同样条件对比其他检索方案。
            service = KnowledgeSearchService(
                session=session,
            )

            for case in cases:
                # perf_counter()用于测量一段代码实际花了多久。
                started_at = perf_counter()

                # 每道题开始时，先将降级标记重置。
                rerank_fallback = False

                if strategy == "rerank":
                    # 完整方案：向量＋BM25＋RRF＋Rerank。
                    hits = await service.search(
                        organization_id=organization_id,
                        query=case.query,
                        candidate_top_k=20,
                        rrf_top_k=20,
                        final_top_k=5,
                    )

                    # 完整服务已返回文档ID和页码，
                    # 直接转成评分方法需要的格式。
                    retrieved_sources = [
                        (str(hit.document_id), hit.page_number)
                        for hit in hits
                    ]

                    # 有结果却没有Rerank排名，
                    # 表示服务使用了备用的RRF结果。
                    rerank_fallback = bool(hits) and any(
                        hit.rerank_rank is None
                        for hit in hits
                    )

                else:
                    # vector和hybrid使用上一步写的对照方法。
                    # 它返回的已经是“文档ID、页码”列表。
                    retrieved_sources = await retrieve_baseline_sources(
                        session=session,
                        organization_id=organization_id,
                        query=case.query,
                        strategy=strategy,
                        top_k=5,
                    )

                # 三个方案都测量到取得资料位置为止，
                # 评分和打印不计入检索耗时。
                elapsed_seconds = perf_counter() - started_at

                # 把题集标注的正确资料转成同样的格式。
                relevant_sources = [
                    (str(source.document_id), source.page_number)
                    for source in case.relevant_sources
                ]

                # 前1条是否找到正确资料，能反映第一名是否准确。
                scores_1 = score_retrieval(
                    retrieved_sources=retrieved_sources,
                    relevant_sources=relevant_sources,
                    top_k=1,
                )

                # 再检查前5条的召回比例，以及第一个正确结果的排名。
                scores_5 = score_retrieval(
                    retrieved_sources=retrieved_sources,
                    relevant_sources=relevant_sources,
                    top_k=5,
                )


                if rerank_fallback:
                    fallback_count += 1

                total_recall_1 += scores_1["recall_at_k"]
                total_recall_5 += scores_5["recall_at_k"]
                total_rr_5 += scores_5["rr_at_k"]
                total_seconds += elapsed_seconds

                print(f"\n题号：{case.id}")
                print(f"问题：{case.query}")
                print(f"Recall@1：{scores_1['recall_at_k']:.3f}")
                print(f"Recall@5：{scores_5['recall_at_k']:.3f}")
                print(f"RR@5：{scores_5['rr_at_k']:.3f}")
                print(f"耗时：{elapsed_seconds:.3f}秒")
                if strategy == "rerank":
                    print(f"Rerank是否降级：{rerank_fallback}")

        # 题集读取方法已经保证题目数量不为0。
        case_count = len(cases)

        print("\n评估汇总")
        print(f"题目数量：{case_count}")
        print(f"平均Recall@1：{total_recall_1 / case_count:.3f}")
        print(f"平均Recall@5：{total_recall_5 / case_count:.3f}")

        # 每道题RR的平均值，就是MRR。
        print(f"MRR@5：{total_rr_5 / case_count:.3f}")
        print(f"平均耗时：{total_seconds / case_count:.3f}秒")
        # 只有使用Rerank的方案，才需要统计降级次数。
        if strategy == "rerank":
            print(f"Rerank降级题数：{fallback_count}")

    finally:
        # 脚本运行结束或报错时，释放数据库和Qdrant连接。
        try:
            await engine.dispose()
        finally:
            await qdrant_client.close()


if __name__ == "__main__":
    print("开始知识库检索评估……", flush=True)
    asyncio.run(main())