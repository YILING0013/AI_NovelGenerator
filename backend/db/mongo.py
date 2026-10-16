import logging
import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from backend.config.config import get_config_value
from backend.db.confirmation_timing import confirmation_commands

logger = logging.getLogger(__name__)

client: AsyncMongoClient | None = None
setup_error: dict[str, str] | None = None
_active_connection_settings: tuple[str, str, int] | None = None
MONGODB_URL_ENV_VAR = "NOVEL_GENERATOR_MONGODB_URL"
MONGO_DATABASE_NAME_ENV_VAR = "NOVEL_GENERATOR_MONGO_DATABASE_NAME"


def _get_runtime_setting(env_name: str, config_key: str, default: str) -> str:
    """优先读取进程级覆盖值，未设置时回退到托管配置。

    Args:
        env_name: 仅作用于当前进程的环境变量名。
        config_key: YAML 托管配置中的字段名。
        default: 两处均未提供有效值时使用的默认值。

    Returns:
        去除首尾空白后的运行时配置值。
    """
    override = os.getenv(env_name)
    if override is not None and override.strip():
        return override.strip()
    return str(get_config_value(config_key, default)).strip() or default


def _get_database_name() -> str:
    """读取当前进程实际使用的 MongoDB 数据库名。

    Args:
        无。

    Returns:
        测试进程覆盖值或托管配置中的数据库名。
    """
    return _get_runtime_setting(
        MONGO_DATABASE_NAME_ENV_VAR,
        "mongo_database_name",
        "",
    )


def _get_connection_settings() -> tuple[str, str, int]:
    """读取当前 MongoDB 连接配置。

    Args:
        无。

    Returns:
        包含连接串、数据库名和服务选择超时时间的元组。
    """
    # 进程级覆盖只用于隔离测试/临时运行，不会回写用户的 config.yaml。
    mongo_uri = _get_runtime_setting(
        MONGODB_URL_ENV_VAR,
        "mongodb_url",
        "",
    )
    db_name = _get_database_name()
    timeout_ms = int(get_config_value("mongo_timeout_ms", 5000))
    return mongo_uri, db_name, timeout_ms

async def connect_to_mongo():
    """初始化全局 MongoDB 异步客户端，并在启动期执行 ping 校验。

    Args:
        无。

    Returns:
        无。
    """
    global client, _active_connection_settings, setup_error

    connection_settings = _get_connection_settings()

    if client is not None and _active_connection_settings == connection_settings:
        setup_error = None
        return

    mongo_uri, database_name, timeout_ms = connection_settings
    if not mongo_uri or not database_name:
        await close_mongo_connection()
        setup_error = None
        return
    next_client = AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=timeout_ms, event_listeners=[confirmation_commands])
    try:
        # 连接对象是惰性的，主动 ping 可以在启动期暴露配置或网络错误。
        await next_client.admin.command("ping")
        from backend.migrations.database import prepare_database
        await prepare_database(next_client, database_name)
    except Exception:
        await next_client.close()
        raise

    previous_client = client
    client = next_client
    _active_connection_settings = connection_settings
    setup_error = None

    # 新连接已经通过 ping 后才切换全局引用；失败时旧连接始终可继续服务。
    if previous_client is not None:
        try:
            await previous_client.close()
        except Exception:
            # 新连接已经生效；旧客户端清理失败只记录，不回滚到未知状态。
            logger.exception("MongoDB previous client cleanup failed after connection swap")
        logger.info("MongoDB config changed, replaced previous client after successful ping.")

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
    active_client = get_client()
    return active_client[_active_connection_settings[1]]

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
