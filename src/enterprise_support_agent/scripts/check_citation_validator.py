"""
测试答案引用编号检查器。

检查四种情况：

1. 正常引用；
2. 重复引用；
3. 引用不存在的资料；
4. 答案没有引用。
"""

from enterprise_support_agent.application.citation_validator import (
    InvalidCitationError,
    validate_answer_citations,
)


def check_invalid_answer(
    answer: str,
) -> None:
    """检查有问题的答案是否确实会被拦截。"""

    try:
        validate_answer_citations(
            answer=answer,
            allowed_source_numbers={1, 2},
        )

    except InvalidCitationError as error:
        # 这种答案本来就应该报错，
        # 所以捕获到异常说明测试通过。
        print(f"成功拦截：{error}")

    else:
        # else表示没有抛出异常。
        #
        # 有问题的答案居然通过了检查，
        # 说明检查器没有正常工作。
        raise AssertionError(
            "测试失败：错误答案没有被拦截"
        )


def main() -> None:
    """依次执行引用检查测试。"""

    # 第一种：正常引用。
    numbers = validate_answer_citations(
        answer="请检查数据库端口。[资料2]",
        allowed_source_numbers={1, 2},
    )

    # assert是Python自带的断言语句。
    #
    # 条件正确：继续执行。
    # 条件错误：抛出AssertionError，停止测试。
    assert numbers == [2]
    print("正常引用：通过")

    # 第二种：允许同一资料被引用多次，
    # 返回的编号清单按首次出现顺序去重。
    numbers = validate_answer_citations(
        answer=(
            "检查端口。[资料2]"
            "检查网络。[资料2]"
            "核对地址。[资料1]"
        ),
        allowed_source_numbers={1, 2},
    )

    assert numbers == [2, 1]
    print("重复引用去重：通过")

    # 第三种：只有资料1和2，
    # 却引用了资料9，应该被拦截。
    check_invalid_answer(
        "请检查数据库端口。[资料9]"
    )

    # 第四种：回答没有引用，应该被拦截。
    check_invalid_answer(
        "请检查数据库端口。"
    )

    print("全部测试通过")


if __name__ == "__main__":
    main()