class DatabaseError(Exception):
    """所有数据库错误的基类。"""
    pass

class NotFoundError(DatabaseError):
    """请求的资源未找到时抛出。"""
    pass

class InvalidIdError(DatabaseError):
    """提供的ID不是有效的ObjectId时抛出。"""
    pass

class DuplicateKeyError(DatabaseError):
    """插入违反唯一约束时抛出。"""
    pass
