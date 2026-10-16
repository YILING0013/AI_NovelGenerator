"""启动器调用的独立预检入口。"""
import asyncio
import sys
from . import MigrationError, prepare_files


async def check_database():
    """按用户配置检查数据库，空白配置直接进入设置。Returns: 可修正的连接错误说明或 None。"""
    from backend.db.mongo import connect_to_mongo, close_mongo_connection
    try:
        await connect_to_mongo()
    except Exception as exc:
        from .database import database_setup_error
        issue = database_setup_error(exc)
        if issue is None: raise
        return issue
    finally:
        await close_mongo_connection()


def main() -> int:
    """检查完成返回 0；连接失败仅允许设置返回 2；安全阻塞返回 1。

    Returns: 不含密钥的提示及退出码，2 不能当作数据库检查成功。
    """
    try:
        print("[stage] 正在检查用户文件和任务方案…", flush=True)
        for notice in prepare_files():
            print(notice)
        print("[stage] 正在检查数据库连接、格式和索引…", flush=True)
        issue = asyncio.run(check_database())
        if issue:
            print(issue["message"] + "将进入设置页，业务功能仍不可用。", flush=True)
            return 2
    except Exception as exc:
        print(str(exc) if isinstance(exc, MigrationError) else "启动检查失败，请检查文件权限、数据库连接及索引冲突；原数据已保留。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
