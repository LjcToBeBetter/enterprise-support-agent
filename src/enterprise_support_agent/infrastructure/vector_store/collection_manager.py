"""
Qdrant Collection管理器。

主要负责：

1. 检查知识库Collection是否存在；
2. 不存在时创建Collection；
3. 已存在时检查向量维度；
4. 为常用Payload字段创建过滤索引。
"""

from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    TextIndexParams,
    TextIndexType,
    TextScoringParams,
    TextScoringType,
    TokenizerType,
    VectorParams,
)

from enterprise_support_agent.config import (
    settings,
)
from enterprise_support_agent.infrastructure.vector_store.qd_client import (
    qdrant_client,
)


class QdrantCollectionManager:
    """负责Qdrant Collection的创建和检查。"""

    async def ensure_document_chunks_collection(
        self,
    ) -> bool:
        """
        确保知识库文本块Collection存在。

        返回：
            True：
                本次创建了新Collection。

            False：
                Collection原本已经存在。
        """

        collection_name = (
            settings.qdrant_collection_name
        )

        # collection_exists()向Qdrant查询：
        # 指定名称的Collection是否已经存在。
        collection_exists = (
            await qdrant_client.collection_exists(
                collection_name=collection_name
            )
        )

        if collection_exists:
            # Collection已经存在时，
            # 读取它的实际配置信息。
            collection_info = (
                await qdrant_client.get_collection(
                    collection_name=collection_name
                )
            )

            # 当前使用的是“单向量配置”，
            # vectors中保存一个VectorParams对象:
            # 里面主要包含：
            # size
            # 规定每条向量必须有多少维
            #
            # distance
            # 规定使用什么方式计算向量相似度
            #
            # 其他可选配置
            # 向量是否写磁盘、数据类型等
            vector_config = (
                collection_info.config.params.vectors
            )

            # 如果现有Collection使用了其他结构，
            # 说明它不是我们当前期望的单向量Collection。
            if not isinstance(
                vector_config,
                VectorParams,
            ):
                raise RuntimeError(
                    "现有Qdrant Collection不是单向量配置"
                )

            # Collection已经创建后，
            # 向量维度不能随便改变。
            #
            # 如果模型输出1024维，
            # Collection也必须是1024维。
            if (
                vector_config.size
                != settings.qdrant_vector_size
            ):
                raise RuntimeError(
                    "Qdrant Collection向量维度不匹配："
                    f"实际为{vector_config.size}，"
                    f"配置为{settings.qdrant_vector_size}"
                )

            # 取得已经存在的Payload索引信息。
            payload_schema = (
                collection_info.payload_schema
            )

            created = False

        else:
            # Collection不存在时创建它。
            await qdrant_client.create_collection(
                collection_name=collection_name,

                # VectorParams规定向量的结构。
                vectors_config=VectorParams(
                    # 每个向量必须包含1024个数字。
                    size=settings.qdrant_vector_size,

                    # 使用余弦距离计算语义相似度。
                    distance=Distance.COSINE,
                ),
            )

            # 新Collection暂时没有Payload索引。
            payload_schema = {}

            created = True

        # 这些Payload字段会频繁用于数据过滤。
        #
        # 例如：
        # 只检索当前组织的向量；
        # 删除指定文档版本的向量。
        required_payload_indexes = {
            "organization_id": (
                PayloadSchemaType.UUID
            ),
            "document_id": (
                PayloadSchemaType.UUID
            ),
            "document_version": (
                PayloadSchemaType.INTEGER
            ),
            "page_number": (
                PayloadSchemaType.INTEGER
            ),
            "chunk_index": (
                PayloadSchemaType.INTEGER
            ),
        }

        # 只创建当前还不存在的Payload索引。
        for (
            field_name,
            field_schema,
        ) in required_payload_indexes.items():
            if field_name in payload_schema:
                continue

            await qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,

                # wait=True表示等待索引创建完成后
                # 再继续执行后面的代码。
                wait=True,
            )

        # content保存文本块正文的检索副本。
        #
        # 普通Payload索引只能用于过滤；
        # 这里创建的是“全文索引”，还开启了BM25评分，
        # 因此后面可以按照关键词相关性给文本块排名。
        if "content" not in payload_schema:
            await qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name="content",
                field_schema=TextIndexParams(
                    # 表示这是一个全文文本索引。
                    # 全文索引：把长文本拆成关键词，并建立“关键词对应哪些 Point”的目录。
                    type=TextIndexType.TEXT,

                    # multilingual专门处理多语言文本，
                    # 比普通word分词器更适合当前中文知识库。
                    # 给 content 建全文索引时，使用多语言分词器拆分文本。
                    # 不用像之前一样手写jieba分词
                    tokenizer=(
                        TokenizerType.MULTILINGUAL
                    ),

                    # 英文检索时不区分大小写。
                    lowercase=True,

                    # 开启BM25相关性评分。
                    scoring=TextScoringParams(
                        type=TextScoringType.BM25
                    ),
                ),

                # 等全文索引创建完成后再继续。
                wait=True,
            )

        return created
