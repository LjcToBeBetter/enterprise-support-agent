"""
Rerank重排序的统一接口。

业务层只依赖这里定义的Reranker，
不直接依赖阿里云百炼。

以后更换成本地模型或其他服务时，
只需要增加新的实现类。
"""

from abc import (
    ABC,
    abstractmethod,
)
from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class RerankResult:
    """Rerank模型返回的一条重排序结果。"""

    # 候选文本在原始documents列表中的下标。
    #
    # 例如document_index=1，
    # 表示命中的是documents[1]。
    document_index: int

    # Rerank模型计算出的相关性分数。
    #
    # 分数越高，表示候选文本越能回答用户问题。
    relevance_score: float


class Reranker(ABC):
    """所有Rerank模型客户端都必须实现的统一接口。"""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[RerankResult]:
        """
        对候选文本重新打分并排序。

        query：
            用户问题。

        documents：
            RRF召回的候选文本列表。

        top_n：
            Rerank后最终返回多少条。

        返回：
            按相关性从高到低排列的RerankResult列表。
        """

        # abstractmethod表示这是抽象方法。
        #
        # 当前类只规定方法长什么样，
        # 真正调用哪个模型由子类实现。
        raise NotImplementedError