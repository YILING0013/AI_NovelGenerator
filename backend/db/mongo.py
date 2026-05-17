import logging
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConnectionFailure

from backend.config.config import get_config_value

logger = logging.getLogger(__name__)

client: AsyncMongoClient | None = None
_active_connection_settings: tuple[str, str, int] | None = None


def _get_connection_settings() -> tuple[str, str, int]:
    """读取当前 MongoDB 连接配置。

    Args:
        无。

    Returns:
        包含连接串、数据库名和服务选择超时时间的元组。
    """
    mongo_uri = str(get_config_value("mongodb_url", "mongodb://localhost:27017"))
    db_name = str(get_config_value("mongo_database_name", "novel_generator"))
    timeout_ms = int(get_config_value("mongo_timeout_ms", 5000))
    return mongo_uri, db_name, timeout_ms

async def connect_to_mongo():
    """初始化全局 MongoDB 异步客户端，并在启动期执行 ping 校验。

    Args:
        无。

    Returns:
        无。
    """
    global client, _active_connection_settings

    connection_settings = _get_connection_settings()

    if client is not None and _active_connection_settings == connection_settings:
        return

    if client is not None:
        await client.close()
        client = None
        logger.info("MongoDB config changed, reconnecting client.")

    mongo_uri, _, timeout_ms = connection_settings
    next_client = AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=timeout_ms)
    try:
        # 连接对象是惰性的，主动 ping 可以在启动期暴露配置或网络错误。
        await next_client.admin.command("ping")
    except Exception:
        await next_client.close()
        raise

    client = next_client
    _active_connection_settings = connection_settings

    from backend.db.transaction import reset_transaction_capability_cache

    reset_transaction_capability_cache()
    logger.info("Connected to MongoDB database '%s' using managed config", connection_settings[1])

def get_client() -> AsyncMongoClient:
    """返回已初始化的 MongoDB 异步客户端。

    Args:
        无。

    Returns:
        当前全局 AsyncMongoClient 实例。
    """
    if client is None:
        raise RuntimeError("MongoDB client is not initialized. Call connect_to_mongo() first.")
    return client

def get_database() -> AsyncDatabase:
    """返回当前配置指定的数据库实例。

    Args:
        无。

    Returns:
        PyMongo Async 数据库对象。
    """
    db_name = str(get_config_value("mongo_database_name", "novel_generator"))
    return get_client()[db_name]

async def close_mongo_connection():
    """关闭 MongoDB 异步客户端连接。

    Args:
        无。

    Returns:
        无。
    """
    global client, _active_connection_settings
    if client is not None:
        await client.close()
        client = None
        _active_connection_settings = None
        logger.info("Closed MongoDB connection.")

async def check_mongo_connection() -> bool:
    """通过 ping 检查 MongoDB 是否可达。

    Args:
        无。

    Returns:
        MongoDB 当前可达时返回 True，否则返回 False。
    """
    if client is None:
        return False
    try:
        await client.admin.command('ping')
        return True
    except ConnectionFailure:
        return False
    except Exception as e:
        logger.error(f"Mongo connection check failed: {e}")
        return False
