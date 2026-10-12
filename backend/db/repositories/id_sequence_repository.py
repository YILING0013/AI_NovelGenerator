"""小说作用域业务 ID 的原子序列仓储。"""

from __future__ import annotations

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.utils import get_utc_now, to_object_id


class IdSequenceRepository(BaseRepository):
    """集中分配角色域使用的稳定业务 ID。"""

    def __init__(self) -> None:
        """初始化业务 ID 序列仓储。

        Args:
            无。

        Returns:
            无。
        """
        super().__init__("id_sequences")

    async def allocate_many(
        self,
        novel_id: str | ObjectId,
        entity_type: str,
        prefix: str,
        count: int,
        session: AsyncClientSession | None = None,
    ) -> list[str]:
        """原子预留一段小说内业务 ID。

        Args:
            novel_id: 小说 ObjectId 或其字符串形式。
            entity_type: 固定实体类型，用于隔离不同序列。
            prefix: 业务 ID 前缀，例如 ``char``。
            count: 需要一次预留的 ID 数量。
            session: 可选 MongoDB 会话。

        Returns:
            按升序排列的业务 ID 列表。
        """
        if count < 0:
            raise ValueError("ID 预留数量不能为负数")
        if count == 0:
            return []
        if not entity_type.strip() or not prefix.strip():
            raise ValueError("entity_type 和 prefix 不能为空")

        now = get_utc_now()
        # 单条 findOneAndUpdate 保证并发请求不会拿到重叠区间；回滚时允许保留空号。
        sequence = await self.collection.find_one_and_update(
            {
                "novel_id": to_object_id(novel_id),
                "entity_type": entity_type.strip(),
            },
            {
                "$inc": {"value": count},
                "$set": {"updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if not sequence:
            raise RuntimeError("业务 ID 序列分配失败")

        last_value = int(sequence["value"])
        first_value = last_value - count + 1
        return [f"{prefix}_{value:06d}" for value in range(first_value, last_value + 1)]


id_sequence_repo = IdSequenceRepository()
