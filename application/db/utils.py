from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from .errors import InvalidIdError

def get_utc_now() -> datetime:
    """返回当前的UTC时间。"""
    return datetime.now(timezone.utc)

def to_object_id(id_val: str | ObjectId) -> ObjectId:
    """将字符串转换为ObjectId，如果无效则抛出InvalidIdError。"""
    if isinstance(id_val, ObjectId):
        return id_val
    try:
        return ObjectId(id_val)
    except (InvalidId, TypeError):
        raise InvalidIdError(f"'{id_val}' is not a valid ObjectId.")

def to_str_id(id_val: ObjectId | str) -> str:
    """安全地将ObjectId转换为字符串。"""
    if id_val is None:
        return None
    return str(id_val)
