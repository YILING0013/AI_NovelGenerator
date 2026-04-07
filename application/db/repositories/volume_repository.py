import logging
from typing import Any, Dict, List, Optional

import pymongo.errors

from application.db.base import BaseRepository
from application.db.utils import to_object_id, get_utc_now
from application.db.errors import NotFoundError, DuplicateKeyError

logger = logging.getLogger(__name__)


class VolumeRepository(BaseRepository):
    def __init__(self):
        """初始化卷仓储，指定集合为'volumes'"""
        super().__init__("volumes")

    # 辅助方法 

    async def _get_next_order_index(self, novel_id) -> int:
        """查询该小说下当前最大 order_index，返回下一个可用值。"""
        cursor = self.collection.find(
            {"novel_id": novel_id, "is_deleted": False},
            projection={"order_index": 1}
        ).sort("order_index", -1).limit(1)
        docs = await cursor.to_list(length=1)
        if docs:
            return docs[0].get("order_index", 0) + 1
        return 1

    # 创建 

    async def create_volume(self, data: Dict[str, Any]) -> str:
        """
        创建一个新卷。
        - novel_id（必填）：所属小说ID
        - title（必填）：卷标题
        - summary（选填）：卷概要
        - order_index（选填）：不传则自动递增
        """
        if "novel_id" not in data:
            raise ValueError("novel_id is required")
        if "title" not in data or not data["title"]:
            raise ValueError("Volume title cannot be empty")

        # 将 novel_id 转为 ObjectId 存储
        data["novel_id"] = to_object_id(data["novel_id"])

        # 若未传入 order_index，自动计算
        if "order_index" not in data or data["order_index"] is None:
            data["order_index"] = await self._get_next_order_index(data["novel_id"])

        # 默认字段
        data.setdefault("summary", "")
        data.setdefault("status", "draft")
        data.setdefault("arcs_count", 0)
        data.setdefault("word_count", 0)

        try:
            return await self.insert_one(data)
        except pymongo.errors.DuplicateKeyError:
            raise DuplicateKeyError(
                f"同一小说下 order_index={data['order_index']} 已存在，请使用其他序号"
            )

    # 查询 

    async def get_volumes_by_novel(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下所有未删除的卷，按 order_index 升序排列。"""
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id},
            sort=[("order_index", 1)]
        )

    async def get_volume_by_id(self, volume_id: str) -> Dict[str, Any]:
        """根据ID获取单个卷，不存在或已删除时抛出 NotFoundError。"""
        obj_id = to_object_id(volume_id)
        volume = await self.find_one({"_id": obj_id})
        if not volume:
            raise NotFoundError(f"Volume with id {volume_id} not found")
        return volume

    # 更新 

    async def update_volume_info(self, volume_id: str, update_data: Dict[str, Any]) -> bool:
        """
        更新卷基础信息（白名单模式）。
        允许字段：title, summary, status, order_index
        """
        allowed_fields = {"title", "summary", "status", "order_index"}
        filtered = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not filtered:
            return False

        obj_id = to_object_id(volume_id)

        # order_index 变更时需捕获唯一索引冲突
        try:
            return await self.update_one({"_id": obj_id}, filtered)
        except pymongo.errors.DuplicateKeyError:
            raise DuplicateKeyError(
                f"order_index={filtered.get('order_index')} 与同一小说下已有卷冲突"
            )

    async def update_volume_stats(
        self, volume_id: str,
        arcs_count_delta: int = 0,
        word_count_delta: int = 0
    ) -> bool:
        """原子增减卷的统计字段（arcs_count / word_count）。"""
        increments = {}
        if arcs_count_delta != 0:
            increments["arcs_count"] = arcs_count_delta
        if word_count_delta != 0:
            increments["word_count"] = word_count_delta

        if not increments:
            return False

        obj_id = to_object_id(volume_id)
        return await self.increment_one({"_id": obj_id}, increments)

    # 删除与恢复 

    async def soft_delete_volume(self, volume_id: str) -> bool:
        """软删除指定卷。"""
        obj_id = to_object_id(volume_id)
        return await self.soft_delete_one({"_id": obj_id})

    async def restore_volume(self, volume_id: str) -> bool:
        """恢复已软删除的指定卷。"""
        obj_id = to_object_id(volume_id)
        return await self.restore_one({"_id": obj_id})

    async def hard_delete_volume(self, volume_id: str) -> bool:
        """物理删除指定卷（不可恢复）。"""
        obj_id = to_object_id(volume_id)
        return await self.hard_delete_one({"_id": obj_id})


volume_repo = VolumeRepository()
