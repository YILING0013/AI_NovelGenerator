"""Mongo 格式检查与当前索引初始化，不搬动服务文件或改写小说。"""
from . import MigrationError

DATABASE_FORMAT_VERSION = 1


def database_setup_error(exc: Exception) -> dict[str, str] | None:
    """只把可在设置中修正的连接失败归为设置问题。

    Args: exc: 启动连接检查抛出的原异常。
    Returns: 不含连接凭据的错误说明；格式、索引等安全阻塞返回 None。
    """
    from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure
    if isinstance(exc, OperationFailure) and exc.code == 18:
        return {"code": "DATABASE_AUTHENTICATION_FAILED", "message": "数据库认证失败，请在设置中检查认证信息。"}
    if isinstance(exc, (ConfigurationError, ConnectionFailure)):
        return {"code": "DATABASE_CONNECTION_UNAVAILABLE", "message": "数据库连接不可用，请在设置中检查地址、服务状态和认证信息。"}
    return None


async def prepare_database(client, database_name: str) -> None:
    """检查待使用的库，全部通过后才能发布连接。

    Args: client: 待切换客户端。database_name: 用户指定库名。
    Returns: 无；检查失败抛错，调用者保留旧连接。
    """
    from backend.db.indexes import init_all_indexes
    db = client[database_name]
    marker = await db["_app_metadata"].find_one({"_id": "storage_format"})
    if marker is not None and (type(marker.get("version")) is not int or marker["version"] != DATABASE_FORMAT_VERSION):
        raise MigrationError("Định dạng cơ sở dữ liệu không được phiên bản này hỗ trợ, hãy dùng chương trình tương ứng, không được khởi động theo kiểu hạ cấp.")
    hello = await client.admin.command("hello")
    if not (hello.get("setName") or hello.get("msg") == "isdbgrid") or hello.get("logicalSessionTimeoutMinutes") is None:
        raise MigrationError("MongoDB phải hỗ trợ transaction, hãy nhập chuỗi kết nối replica set khả dụng trong phần Cài đặt.")
    # 真正发出事务内读取，不能只靠 hello 推测权限和可用性。
    async with client.start_session() as session:
        async with await session.start_transaction():
            await db["_app_metadata"].find_one({"_id": "storage_format"}, session=session)
    if marker is None:
        # 当前 Dev 的小说始终具有 version。旧 old 分支不能靠建索引变成新版。
        incompatible = await db["novels"].find_one({"$or": [{"version": {"$exists": False}}, {"version": {"$not": {"$gte": 1}}}]}, {"_id": 1})
        if incompatible:
            raise MigrationError("Thư viện dữ liệu này chứa định dạng tiểu thuyết cũ không nhận dạng được, hãy giữ nguyên thư viện cũ và dùng một thư viện mới riêng biệt.")
    await init_all_indexes(db)
    # 仅登记当前基线，不虚构逐记录升级；失败时原小说完全保留。
    if marker is None:
        await db["_app_metadata"].update_one({"_id": "storage_format"}, {"$setOnInsert": {"version": DATABASE_FORMAT_VERSION}}, upsert=True)
    current = await db["_app_metadata"].find_one({"_id": "storage_format"})
    if (type(current.get("version")) is not int or current["version"] != DATABASE_FORMAT_VERSION):
        raise MigrationError("Phiên bản cơ sở dữ liệu đã thay đổi trong lúc kiểm tra, hãy đóng các instance khác rồi thử lại.")
