"""
PDF文档解析器。

负责把从RustFS读取到的PDF二进制内容，
转换成后续可以切块和检索的正文文本。
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfParsingError(Exception):
    """PDF内容无法正常解析时抛出的异常。"""

# frozen=True
# 表示对象创建完成后，不允许修改属性：
# slots=True
# 表示这个对象只能拥有类中声明过的属性：
@dataclass(
    frozen=True,
    slots=True,
)
class ParsedPdfPage:
    """PDF中一页的解析结果。"""

    # PDF页码，从1开始。
    page_number: int

    # 从这一页提取出来的正文。
    text: str


@dataclass(
    frozen=True,
    slots=True,
)
class ParsedPdfDocument:
    """整个PDF的解析结果。"""

    # PDF总页数。
    page_count: int

    # 每一页的解析结果。
    pages: tuple[ParsedPdfPage, ...]

    # 整个PDF合并后的正文。
    full_text: str


class PdfParser:
    """把PDF二进制内容解析成文本。"""

    def parse(
        self,
        file_content: bytes,
    ) -> ParsedPdfDocument:
        """
        解析PDF文件。

        接收：
            file_content：
                从RustFS下载得到的PDF二进制内容。

        返回：
            PDF总页数、每页正文和完整正文。

        异常：
            PDF损坏、格式错误或加密无法读取时，
            抛出PdfParsingError。
        """

        try:
            # BytesIO把内存中的bytes包装成类似文件的对象。
            #
            # PdfReader通常需要接收一个文件，
            # 但我们的PDF目前只存在file_content变量里，
            # 所以使用BytesIO让它可以像读取文件一样读取bytes。
            pdf_stream = BytesIO(
                file_content
            )

            # 读取PDF结构。
            # reader 是一个 PdfReader 对象-可以操作PDF的读取器对象
            # ，它代表“已经被打开并且能够读取的 PDF”
            reader = PdfReader(
                pdf_stream
            )

            # 暂时保存每一页的解析结果。
            parsed_pages: list[ParsedPdfPage] = []

            # enumerate(..., start=1)表示页码从1开始。
            for page_number, page in enumerate(
                # pages是PDF 中所有页面组成的集合
                # 大概类似：
                # [
                #     第1页对象,
                #     第2页对象,
                #     第3页对象,
                # ]
                reader.pages,
                start=1,
            ):
                # extract_text()提取这一页中的文字。
                #
                # 如果这一页只有图片，没有可提取文字，
                # extract_text()可能返回None。
                page_text = (
                    page.extract_text()
                    or ""
                ).strip()

                parsed_pages.append(
                    ParsedPdfPage(
                        page_number=page_number,
                        text=page_text,
                    )
                )

            # 把每一页正文合并成完整正文。
            #
            # 两页之间使用两个换行符隔开，
            # 避免上一页结尾和下一页开头粘在一起。
            full_text = "\n\n".join(
                page.text
                for page in parsed_pages
                if page.text
            )

            return ParsedPdfDocument(
                page_count=len(reader.pages),
                pages=tuple(parsed_pages),
                full_text=full_text,
            )

        except (
            PdfReadError,
            OSError,
            ValueError,
        ) as error:
            # 保留底层异常作为原因，
            # 同时向上层提供统一的PDF解析异常。
            raise PdfParsingError(
                "PDF文件无法正常解析"
            ) from error