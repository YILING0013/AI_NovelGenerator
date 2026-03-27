import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure

from application.config.config import get_config_value

logger = logging.getLogger(__name__)

# Global mongo client
client: AsyncIOMotorClient = None
_active_connection_settings: tuple[str, str, int] | None = None


def _get_connection_settings() -> tuple[str, str, int]:
    mongo_uri = str(get_config_value("mongodb_url", "mongodb://localhost:27017"))
    db_name = str(get_config_value("mongo_database_name", "novel_generator"))
    timeout_ms = int(get_config_value("mongo_timeout_ms", 5000))
    return mongo_uri, db_name, timeout_ms

async def connect_to_mongo():
    """初始化全局MongoDB客户端连接。"""
    global client, _active_connection_settings

    connection_settings = _get_connection_settings()

    if client is not None and _active_connection_settings == connection_settings:
        return

    if client is not None:
        client.close()
        client = None
        logger.info("MongoDB config changed, reconnecting client.")

    mongo_uri, _, timeout_ms = connection_settings
    client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=timeout_ms)
    _active_connection_settings = connection_settings
    logger.info("Connected to MongoDB using managed config")

def get_database():
    """返回数据库实例。"""
    if client is None:
        raise RuntimeError("MongoDB client is not initialized. Call connect_to_mongo() first.")
    db_name = str(get_config_value("mongo_database_name", "novel_generator"))
    return client[db_name]

async def close_mongo_connection():
    """关闭MongoDB客户端连接。"""
    global client, _active_connection_settings
    if client is not None:
        client.close()
        client = None
        _active_connection_settings = None
        logger.info("Closed MongoDB connection.")

async def check_mongo_connection() -> bool:
    """通过ping检查MongoDB是否可达。"""
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
