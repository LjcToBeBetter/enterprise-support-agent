"""
PDF解析器测试脚本。

这个脚本只用于测试PdfParser能不能正常工作。

它会完成下面几步：

1. 从运行命令中取得PDF文件路径；
2. 读取PDF文件，得到bytes；
3. 调用PdfParser解析PDF；
4. 打印PDF页数和每一页的正文。

运行示例：

uv run python `
  -m enterprise_support_agent.scripts.check_pdf_parser `
  "D:\\test.pdf"
"""

# argparse是Python标准库提供的命令行参数处理工具。
#
# 它可以读取运行命令后面传入的内容。
#
# 例如运行：
# python check_pdf_parser.py "D:\\test.pdf"
#
# argparse可以帮助我们取得后面的"D:\\test.pdf"。
import argparse

# Path由Python标准库pathlib提供。
#
# 它用一个Python对象表示文件路径，
# 并且提供了很多操作文件的方法，例如：
#
# is_file()：判断文件是否存在；
# read_bytes()：读取文件的二进制内容；
# name：取得文件名。
from pathlib import Path

# 导入我们刚才定义的PDF解析器。
from enterprise_support_agent.infrastructure.parsing.pdf_parser import (
    PdfParser,
    PdfParsingError,
)


def main() -> None:
    """
    测试PDF解析功能。

    -> None表示这个方法没有返回值，
    它只负责读取PDF并打印解析结果。
    """

    # ArgumentParser由argparse模块提供。
    #
    # 它表示一个“命令行参数解析器”，
    # 专门负责规定和读取程序运行时传入的参数。
    # argparse用于读取运行命令后面传入的参数。
    #
    # 例如：
    # uv run python ... "D:\\test.pdf"
    #
    # 后面的PDF路径就会被argparse读取。
    # argument_parser是负责读取参数的工具对象
    argument_parser = argparse.ArgumentParser(
        # description是这个脚本的功能说明。
        #
        # 执行下面命令时可以看到这段说明：
        # python check_pdf_parser.py --help

        description="测试PDF正文解析功能",
    )

    # add_argument()用于规定：
    # 这个脚本运行时需要接收什么参数。
    #
    # 注意：
    # add_argument()现在只是“制定参数规则”，
    # 还没有真正读取运行命令中的参数。
    argument_parser.add_argument(
        # 参数名称。
        #
        # 因为pdf_path前面没有"--"，
        # 所以它是一个必须填写的位置参数。
        #
        # 运行时需要这样传入：
        # python check_pdf_parser.py "D:\\test.pdf"
        "pdf_path",

        # 命令行中传入的内容原本都是字符串。
        #
        # type=Path表示：
        # 自动把传入的路径字符串转换成Path对象。
        #
        # 转换后才能方便地调用：
        # pdf_path.is_file()
        # pdf_path.read_bytes()
        type=Path,

        # help是这个参数的说明文字。
        #
        # 执行--help时会显示，
        # 不参与实际的PDF处理。
        help="需要解析的PDF文件路径",
    )

    # parse_args()才会真正读取运行命令中的参数。
    #
    # 假设运行命令是：
    # python check_pdf_parser.py "D:\\test.pdf"
    #
    # 那么arguments.pdf_path就是：
    # Path("D:\\test.pdf")
    arguments = argument_parser.parse_args()

    # 从arguments中取得用户传入的PDF路径。
    #
    # 因为上面设置了type=Path，
    # 所以这里得到的是Path对象，不是普通字符串。
    pdf_path: Path = arguments.pdf_path

    # is_file()用于判断：
    #
    # 1. 这个路径是否存在；
    # 2. 这个路径是不是一个文件。
    #
    # 如果路径不存在，或者它是一个文件夹，
    # is_file()都会返回False。
    if not pdf_path.is_file():
        raise FileNotFoundError(
            f"没有找到PDF文件：{pdf_path}"
        )

    # read_bytes()读取整个PDF文件。
    #
    # 返回值是bytes，也就是文件的二进制内容。
    #
    # 它不会解析PDF正文，
    # 只是把硬盘上的PDF读取到内存中。
    file_content: bytes = pdf_path.read_bytes()

    # 创建我们自己定义的PDF解析器对象。
    pdf_parser = PdfParser()

    try:
        # 调用PdfParser的parse()方法解析PDF。
        #
        # 传入：
        #     PDF文件的bytes。
        #
        # 返回：
        #     ParsedPdfDocument对象。
        #
        # 这个对象里面保存了：
        #     page_count：PDF总页数；
        #     pages：每一页的解析结果；
        #     full_text：合并后的完整正文。
        parsed_document = pdf_parser.parse(
            file_content
        )

    except PdfParsingError as error:
        # 如果PDF损坏、格式错误或者无法解析，
        # PdfParser会抛出PdfParsingError。
        #
        # 这里捕获异常并打印错误信息，
        # 避免直接显示一大串异常堆栈。
        print(
            f"PDF解析失败：{error}"
        )

        # return表示结束main()方法，
        # 后面的正文打印代码不再继续执行。
        return

    print(
        "========== PDF解析结果 =========="
    )

    # pdf_path.name表示只取得文件名，
    # 不包含前面的文件夹路径。
    #
    # 例如：
    # D:\test\manual.pdf
    #
    # pdf_path.name得到：
    # manual.pdf
    print(
        f"文件名：{pdf_path.name}"
    )

    # page_count是PdfParser解析后得到的PDF总页数。
    print(
        f"总页数：{parsed_document.page_count}"
    )

    # full_text是所有页面正文合并后的字符串。
    #
    # len()计算字符串中包含多少个字符。
    print(
        f"正文字符数："
        f"{len(parsed_document.full_text)}"
    )

    # parsed_document.pages保存了所有页面的解析结果。
    #
    # for循环会依次取出每一个ParsedPdfPage对象。
    for page in parsed_document.pages:
        print()

        # page.page_number是当前页码。
        print(
            f"========== "
            f"第{page.page_number}页 "
            f"=========="
        )

        # page.text是这一页提取出来的正文。
        #
        # 如果page.text是空字符串，
        # 就打印“这一页没有提取到文字”。
        print(
            page.text
            or "[这一页没有提取到文字]"
        )


# __name__是Python自动提供的变量。
#
# 当我们直接运行这个文件时：
# __name__的值就是"__main__"，
# 因此会调用main()。
#
# 当这个文件被其他模块导入时：
# __name__不是"__main__"，
# 因此不会自动执行测试代码。
if __name__ == "__main__":
    main()