"""
文档文本块Repository。

主要负责document_chunks表的数据库操作：

1. 删除指定文档版本的旧文本块；
2. 批量加入新的文本块；
3. 保证重新处理文档时不会残留旧数据。
"""

from uuid import UUID

from sqlalchemy import (
    delete,
    select
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from enterprise_support_agent.infrastructure.database.models.document_chunk import (
    DocumentChunk,
)


class DocumentChunkRepository:
    """负责document_chunks表的数据库操作。"""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """
        创建文本块Repository。

        session：
            当前业务操作使用的异步数据库会话。
        """

        self.session = session

    async def replace_document_version_chunks(
        self,
        document_id: UUID,
        document_version: int,
        chunks: list[DocumentChunk],
    ) -> list[DocumentChunk]:
        """
        替换指定文档版本的全部文本块。

        处理过程：

        1. 删除这个文档版本原来的文本块；
        2. 批量加入新生成的文本块；
        3. flush到PostgreSQL；
        4. 不在这里commit，由Service统一提交。

        为什么先删除旧块：

            同一份文档可能因为切块参数发生变化，
            被重新解析和重新切块。

            如果直接插入，新旧文本块会同时存在，
            还可能违反联合唯一约束。
        """

        # 如果传入空列表，直接拒绝操作。
        #
        # 这样可以避免因为上层代码错误，
        # 意外删除数据库中原有的全部文本块。
        if not chunks:
            raise ValueError(
                "不能使用空文本块列表替换文档内容"
            )

        # delete()由SQLAlchemy提供，
        # 用来创建DELETE SQL语句。
        #
        # 这里只删除：
        # 1. 指定document_id；
        # 2. 指定document_version；
        #
        # 对应的文本块。
        delete_statement = delete(
            DocumentChunk
        ).where(
            DocumentChunk.document_id
            == document_id,

            DocumentChunk.document_version
            == document_version,
        )

        # execute()把DELETE语句发送给PostgreSQL执行。
        #
        # 当前还没有commit，
        # 所以如果后面的批量插入失败，
        # 整个事务仍然可以rollback，
        # 原来的文本块也不会真的丢失。
        await self.session.execute(
            delete_statement
        )

        # add_all()是Session提供的批量添加方法。
        #
        # add()一次加入一个ORM对象；
        # add_all()一次加入多个ORM对象。
        #
        # 它现在只是把这些对象交给Session管理，
        # 还没有永久写入数据库。
        self.session.add_all(
            chunks
        )

        # flush()把所有INSERT语句发送给PostgreSQL。
        #
        # 此时可以提前发现：
        # 唯一约束冲突、外键错误、字段为空等问题。
        #
        # 但事务仍然没有永久提交。
        await self.session.flush()

        return chunks

    async def list_by_document_version(
            self,
            document_id: UUID,
            document_version: int,
    ) -> list[DocumentChunk]:
        """
        查询指定文档版本的所有文本块。

        接收：
            document_id：
                需要查询的文档ID。

            document_version：
                需要查询的文档版本号。

        返回：
            按照chunk_index从小到大排列的
            DocumentChunk ORM对象列表。
        """

        # select(DocumentChunk)表示查询
        # document_chunks表中的完整记录。
        statement = (
            select(DocumentChunk)

            # 只查询指定文档的文本块。
            .where(
                DocumentChunk.document_id
                == document_id,

                # 同时限制文档版本，
                # 防止不同版本的文本块混在一起。
                DocumentChunk.document_version
                == document_version,
            )

            # 按照文本块编号升序排列：
            # 0、1、2、3……
            .order_by(
                DocumentChunk.chunk_index.asc()
            )
        )

        # execute()把SELECT发送给PostgreSQL。
        result = await self.session.execute(
            statement
        )

        # scalars()从查询结果中取出
        # DocumentChunk ORM对象。
        #
        # all()取得全部结果，
        # 返回一个Sequence。
        #
        # list()将它转换成普通Python列表。
        return list(
            result.scalars().all()
        )

    async def list_by_ids_and_organization(
        self,
        organization_id: UUID,
        chunk_ids: list[UUID],
    ) -> list[DocumentChunk]:
        """
        根据一批文本块ID查询当前组织的文本块。

        这个方法主要用于向量检索：

        1. Qdrant返回命中的文本块ID；
        2. 使用这些ID查询PostgreSQL；
        3. 取得真正的文本块正文。

        同时检查organization_id，避免读取到其他组织的数据。
        """

        # 没有任何文本块ID时，不需要访问数据库。
        if not chunk_ids:
            return []

        statement = (
            select(DocumentChunk)

            # 只允许查询当前组织的文本块。
            .where(
                DocumentChunk.organization_id
                == organization_id,

                # in_()会生成SQL中的IN条件。
                #
                # 例如chunk_ids中有id1和id2时，
                # 对应的意思是：
                # WHERE id IN (id1, id2)
                #
                # 也就是一次查询多条指定ID的记录。
                DocumentChunk.id.in_(
                    chunk_ids
                ),
            )
        )

        # 把SELECT语句发送给PostgreSQL执行。
        result = await self.session.execute(
            statement
        )

        # 返回查询到的DocumentChunk ORM对象列表。
        #
        # 数据库不保证这里的顺序和chunk_ids一致，
        # 下一步会在Service中按照Qdrant分数重新排序。
        return list(
            result.scalars().all()
        )
