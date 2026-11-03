"""
passwords.py

主要功能：
    对用户密码进行安全哈希；
    验证明文密码是否与数据库中的哈希匹配。

主要部件：
    hash_password：
        把明文密码转换成不可逆的哈希字符串。

    verify_password：
        检查用户输入的密码是否正确。

数据库中只保存密码哈希，绝不保存明文密码。
"""

from anyio import to_thread
from pwdlib import PasswordHash


# recommended()创建使用推荐安全配置的密码哈希对象。
# 当前会使用Argon2算法。
password_hasher = PasswordHash.recommended()


async def hash_password(
    plain_password: str,
) -> str:
    """将明文密码转换成密码哈希。"""

    # Argon2计算会消耗一定CPU时间。
    # to_thread.run_sync()把同步哈希计算交给工作线程，
    # 避免阻塞FastAPI的事件循环。
    return await to_thread.run_sync(
        password_hasher.hash,
        plain_password,
    )


async def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """验证明文密码是否匹配已有哈希。"""

    # verify()不会解密密码，
    # 而是重新计算并比较哈希结果。
    return await to_thread.run_sync(
        password_hasher.verify,
        plain_password,
        password_hash,
    )