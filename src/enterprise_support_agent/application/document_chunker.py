"""
知识库文档文本切块器。

主要功能：

1. 接收PdfParser生成的ParsedPdfDocument；
2. 按页处理正文；
3. 把长正文切成多个较小文本块；
4. 在相邻文本块之间保留一部分重复内容；
5. 计算字符数、近似Token数和内容摘要。
"""

import hashlib
import math
import re
from dataclasses import dataclass

from enterprise_support_agent.infrastructure.parsing.pdf_parser import (
    ParsedPdfDocument,
)


@dataclass(
    frozen=True,
    slots=True,
)
class PreparedDocumentChunk:
    """
    准备写入数据库的一块正文。

    它还不是DocumentChunk ORM对象，
    只是文本切块器产生的普通数据对象。
    """

    # 这块正文来自PDF的第几页。
    page_number: int

    # 这块正文在整份文档中的编号。
    chunk_index: int

    # 文本块的正文。
    content: str

    # 正文字符数量。
    character_count: int

    # 近似Token数量。
    token_count: int

    # 正文的SHA-256摘要。
    content_hash: str


class DocumentChunker:
    """把解析后的文档正文切成多个较小文本块。"""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> None:
        """
        创建文本切块器。

        chunk_size：
            每个文本块最多包含多少个字符。

        chunk_overlap：
            相邻文本块之间重复保留多少个字符。

        例如：

            第一块：
                第0到第799个字符

            第二块：
                从第680个字符开始

        这样第680到第799个字符会同时出现在两块中，
        可以避免一句话正好被切断后丢失上下文。
        """

        # 每块字符数必须大于0。
        if chunk_size <= 0:
            raise ValueError(
                "chunk_size必须大于0"
            )

        # 重叠字符数不能是负数。
        if chunk_overlap < 0:
            raise ValueError(
                "chunk_overlap不能小于0"
            )

        # 重叠长度必须小于文本块长度。
        #
        # 否则下一块无法向后移动，
        # 可能导致无限循环。
        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap必须小于chunk_size"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_document(
        self,
        document: ParsedPdfDocument,
    ) -> list[PreparedDocumentChunk]:
        """
        把整份PDF的解析结果切成文本块。

        接收：
            ParsedPdfDocument对象。

        返回：
            PreparedDocumentChunk列表。
        """

        # 保存最终生成的所有文本块。
        prepared_chunks: list[
            PreparedDocumentChunk
        ] = []

        # 文本块编号从0开始。
        #
        # 它是整份文档的全局编号，
        # 不会在进入下一页后重新变成0。
        chunk_index = 0

        # 依次处理PDF中的每一页。
        for page in document.pages:
            # 清理这一页正文中的多余空白。
            normalized_text = self._normalize_text(
                page.text
            )

            # 页面没有正文时直接跳过。
            if not normalized_text:
                continue

            # 把当前页面切成多个字符串。
            page_chunks = self._split_text(
                normalized_text
            )

            for chunk_content in page_chunks:
                # 根据正文计算SHA-256摘要。
                #
                # encode("utf-8")先把字符串转换成bytes，
                # 因为sha256()只能处理bytes。
                content_hash = hashlib.sha256(
                    chunk_content.encode("utf-8")
                ).hexdigest()

                prepared_chunks.append(
                    PreparedDocumentChunk(
                        page_number=page.page_number,
                        chunk_index=chunk_index,
                        content=chunk_content,
                        character_count=len(
                            chunk_content
                        ),
                        token_count=(
                            self._estimate_token_count(
                                chunk_content
                            )
                        ),
                        content_hash=content_hash,
                    )
                )

                # 下一块编号加1。
                chunk_index += 1

        return prepared_chunks

    def _normalize_text(
        self,
        text: str,
    ) -> str:
        """
        清理正文中的多余空白。

        方法名前面的单下划线表示：
        这是类内部使用的辅助方法，
        外部代码一般不直接调用。
        """

        # splitlines()按换行符把正文拆成多行。
        #
        # line.strip()删除每行开头和结尾的空格。
        #
        # if line.strip()跳过完全空白的行。
        cleaned_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        # 使用一个换行符重新连接所有非空行。
        return "\n".join(
            cleaned_lines
        )

    def _split_text(
        self,
        text: str,
    ) -> list[str]:
        """把一页长文本切成多个字符串。"""

        chunks: list[str] = []

        # start表示当前文本块从哪个字符开始。
        start = 0

        # 只要start还没有到达正文末尾，
        # 就继续生成文本块。
        while start < len(text):
            # 当前块理论上的结束位置。
            end = min(
                start + self.chunk_size,
                len(text),
            )

            # 截取当前文本块。
            chunk_content = text[start:end].strip()

            # 空字符串不保存。
            if chunk_content:
                chunks.append(
                    chunk_content
                )

            # 已经到达正文末尾，结束循环。
            if end >= len(text):
                break

            # 下一块从“当前结束位置减去重叠长度”开始。
            #
            # 例如：
            # end = 800
            # chunk_overlap = 120
            #
            # 下一块从680开始。
            start = end - self.chunk_overlap

        return chunks

    def _estimate_token_count(
        self,
        text: str,
    ) -> int:
        """
        粗略估算文本的Token数量。

        当前还没有确定最终Embedding模型，
        不同模型使用的Tokenizer可能不同，
        所以这里暂时只做近似统计。

        后面接入Embedding模型时，
        再替换成对应模型的正式Tokenizer。
        """

        # 查找所有中文字符。
        #
        # findall()返回匹配到的中文字符列表。
        chinese_characters = re.findall(
            r"[\u4e00-\u9fff]",
            text,
        )

        chinese_count = len(
            chinese_characters
        )

        # 删除中文字符后，
        # 剩下英文、数字、标点和空格。
        non_chinese_text = re.sub(
            r"[\u4e00-\u9fff]",
            "",
            text,
        )

        # 英文通常大约每4个字符对应1个Token。
        #
        # math.ceil()表示向上取整，
        # 例如4.2会得到5。
        non_chinese_count = math.ceil(
            len(non_chinese_text) / 4
        )

        # 中文粗略按照一个汉字一个Token计算。
        #
        # max(1, ...)保证非空文本至少有一个Token。
        return max(
            1,
            chinese_count + non_chinese_count,
        )