"""
应用日志配置模块。

主要功能：
    统一设置应用日志的输出级别和格式。

主要部件：
    configure_logging：初始化日志配置。
    logging.basicConfig：Python 提供的日志配置方法。
"""

import logging


def configure_logging() -> None:
    """配置应用日志，默认输出到控制台。"""
    logging.basicConfig(
        # 输出 INFO 及更严重的日志：
        # INFO、WARNING、ERROR、CRITICAL。
        level=logging.INFO,

        # asctime：时间
        # levelname：日志级别
        # name：日志记录器名称，用于标识来源
        # message：具体消息
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
