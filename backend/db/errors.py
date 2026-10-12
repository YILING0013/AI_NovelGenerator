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


class VersionConflictError(DuplicateKeyError):
    """可变正式聚合的 expected_version 与当前版本不一致。"""


class IdempotencyConflictError(DuplicateKeyError):
    """同一领域幂等键被用于不同的规范请求载荷。"""

class TransactionNotSupportedError(DatabaseError):
    """当前 MongoDB 部署不支持所要求的事务模式时抛出。"""
    pass
