"""根据正确资料的位置，为检索结果评分。"""


def score_retrieval(
    retrieved_sources: list[tuple[str, int]],
    relevant_sources: list[tuple[str, int]],
    top_k: int,
) -> dict[str, float]:
    """
    检查前K条检索结果，返回这一道题的评分。

    retrieved_sources：
        系统实际返回的资料，必须按检索排名排列。

    relevant_sources：
        题集中人工标注的正确资料。

    两者都用“文档ID、页码”组成的二元组表示一条资料。
    例如：
        [("文档ID", 1), ("文档ID", 2)]

    top_k：
        只检查排名最靠前的多少条结果。
    """

    if top_k < 1:
        raise ValueError("top_k必须大于0")

    # set()把正确资料变成集合，去掉重复标注，
    # 同时方便判断某条检索结果是否属于正确资料。
    relevant_set = set(relevant_sources)

    if not relevant_set:
        raise ValueError("本评分方法要求题目至少有一条正确资料")

    # 只保留前K条，后面的结果不参与本次评分。
    top_sources = retrieved_sources[:top_k]

    # 集合的&运算取得两边共同拥有的资料，
    # 也就是“系统找到了，而且确实正确”的资料。
    # 同一页被多个文本块命中时，召回数量只算一次。
    matched_sources = set(top_sources) & relevant_set

    # 找到的正确资料数量 ÷ 全部正确资料数量。
    recall_at_k = len(matched_sources) / len(relevant_set)

    # 默认没有找到正确资料，排名得分为0。
    reciprocal_rank = 0.0

    # enumerate(..., start=1)同时取得排名和资料，
    # 排名从1开始。
    for rank, source in enumerate(top_sources, start=1):
        if source in relevant_set:
            # 只看第一个正确结果。
            # 第1名得1分，第2名得0.5分，第3名得约0.333分。
            reciprocal_rank = 1.0 / rank
            break

    return {
        "recall_at_k": recall_at_k,
        "rr_at_k": reciprocal_rank,
    }