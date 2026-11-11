"""把用户问题对应的向量暂存在Redis中，减少重复Embedding调用。"""

import hashlib
import json
import logging
import math
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from enterprise_support_agent.config import settings


logger = logging.getLogger(__name__)


class QueryEmbeddingCache:
    """根据组织、模型和问题，保存或读取问题向量。"""

    def __init__(self, client: Redis) -> None:
        """复用已有的Redis客户端。"""

        self.client = client

    def build_key(
        self,
        organization_id: UUID,
        query: str,
    ) -> str:
        """生成缓存键，让不同组织、模型和问题使用不同缓存。"""

        # 同一个问题换了模型或维度，生成的向量也可能不同。
        # 所以这些信息都要参与区分缓存。
        cache_input = json.dumps(
            {
                "query": query.strip(),
                "model": settings.embed_model_name,
                "base_url": settings.embed_base_url,
                "dimensions": settings.qdrant_vector_size,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        # 把上面的信息转换成固定长度的SHA-256哈希值，
        # 避免把整段问题直接放进键名。
        digest = hashlib.sha256(
            cache_input.encode("utf-8")
        ).hexdigest()

        # 加上组织ID，让不同组织的缓存分开保存。
        return f"cache:query_embedding:v1:{organization_id}:{digest}"

    async def get_vector(
        self,
        key: str,
    ) -> list[float] | None:
        """
        读取缓存向量。

        返回向量：缓存可用。
        返回None：没有缓存，或者缓存不可用，需要重新生成。
        """

        try:
            cached_text = await self.client.get(key)

            if cached_text is None:
                return None

            # Redis里保存的是JSON文本，
            # json.loads()把它还原成Python列表。
            values = json.loads(cached_text)

            # 检查是不是列表，以及向量维度是否正确。
            if (
                not isinstance(values, list)
                or len(values) != settings.qdrant_vector_size
            ):
                return None

            vector = [float(value) for value in values]

            # 向量中的数值必须是有限数字，
            # 不能包含NaN或正负无穷。
            if not all(math.isfinite(value) for value in vector):
                return None

            return vector

        except (RedisError, ValueError, TypeError, OverflowError):
            # 缓存失败时，允许后面重新调用Embedding模型，
            # 不因为这份临时副本不可用就中断检索。
            logger.warning("读取问题向量缓存失败", exc_info=True)
            return None

    async def set_vector(
        self,
        key: str,
        vector: list[float],
    ) -> None:
        """将问题向量缓存10分钟，到期后自动删除。"""

        try:
            # 将Python浮点数列表转换成JSON文本，
            # 例如：[0.12, -0.35, ...]。
            # allow_nan=False禁止保存NaN或无穷值。
            cached_text = json.dumps(
                vector,
                allow_nan=False,
            )

            await self.client.set(
                key,
                cached_text,
                ex=600,
            )

        except (RedisError, ValueError, TypeError):
            # 缓存写入失败，不影响已经生成的向量继续用于检索。
            logger.warning("保存问题向量缓存失败", exc_info=True)