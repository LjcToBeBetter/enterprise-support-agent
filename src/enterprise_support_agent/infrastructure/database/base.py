"""
base.py

主要功能：
    定义所有SQLAlchemy数据库模型共同继承的基类。

主要部件：
    Base：
        所有表模型的父类。
        User、Organization、Ticket等模型继承它以后，
        SQLAlchemy就能登记这些模型对应的表结构。
"""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """所有数据库表模型共同使用的父类."""

    pass