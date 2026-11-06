"""
检查模型答案中的资料引用编号。

例如：

实际提供了资料1和资料2，
答案却出现[资料9]，就说明引用编号有问题。
"""

import re


class InvalidCitationError(ValueError):
    """答案缺少引用，或者引用了不存在的资料。"""


def validate_answer_citations(
    answer: str,
    allowed_source_numbers: set[int],
) -> list[int]:
    """
    检查答案引用，并返回实际引用的资料编号。

    answer：
        大模型生成的答案。

    allowed_source_numbers：
        本次真正提供给模型的资料编号。
        例如：{1, 2}。

    返回：
        按出现顺序去重后的引用编号。
        例如：[2, 1]。

    异常：
        答案没有引用，或者出现不存在的编号。
    """

    # re.findall()是Python标准库re提供的方法，
    # 用来找出字符串中所有符合规则的内容。
    #
    # 这个规则用于匹配：
    # [资料1]、[资料2]、[资料12]。
    #
    # \[ 和 \]：匹配真正的方括号。
    # [0-9]+：匹配一个或多个数字。
    # (...)：只取括号里的数字部分。
    #
    # 例如答案是：
    # "检查端口[资料2]，检查网络[资料1]"
    #
    # 得到：
    # ["2", "1"]
    matched_numbers = re.findall(
        r"\[资料([0-9]+)\]",
        answer,
    )

    if not matched_numbers:
        raise InvalidCitationError(
            "答案没有提供资料引用"
        )

    # 保存去重后的引用编号，并保留首次出现的顺序。
    cited_numbers: list[int] = []

    # set用于快速判断某个编号是否已经保存。
    seen_numbers: set[int] = set()

    for matched_number in matched_numbers:
        # 正则提取到的是字符串，
        #         # 例如"2"，这里转换成整数2。
        source_number = int(matched_number)

        if source_number not in allowed_source_numbers:
            raise InvalidCitationError(
                f"答案引用了不存在的资料："
                f"[资料{source_number}]"
            )

        # 同一份资料可以在答案中引用多次，
        # 但返回的编号列表只保存一次。
        if source_number not in seen_numbers:
            seen_numbers.add(source_number)
            cited_numbers.append(source_number)

    return cited_numbers