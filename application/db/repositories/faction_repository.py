import logging
from typing import Any, Dict, List

import pymongo.errors
from bson import ObjectId

from application.db.base import BaseRepository
from application.db.utils import to_object_id, get_utc_now
from application.db.errors import NotFoundError, DuplicateKeyError

logger = logging.getLogger(__name__)


class FactionRepository(BaseRepository):
    def __init__(self):
        """初始化阵营仓储，指定集合为'factions'"""
        super().__init__("factions")

    # 辅助方法 

    async def _get_next_faction_id(self, novel_id) -> str:
        """查询该小说下当前最大 faction_id，返回下一个可用值（格式 fac_000001）。"""
        obj_id = to_object_id(novel_id) if not isinstance(novel_id, ObjectId) else novel_id
        cursor = self.collection.find(
            {"novel_id": obj_id},
            projection={"faction_id": 1}
        ).sort("faction_id", -1).limit(1)
        docs = await cursor.to_list(length=1)
        if docs and docs[0].get("faction_id"):
            # 解析 fac_000001 中的编号部分
            current_id = docs[0]["faction_id"]
            try:
                num = int(current_id.split("_")[1])
                return f"fac_{num + 1:06d}"
            except (IndexError, ValueError):
                pass
        return "fac_000001"

    # 创建 

    async def create_faction(self, data: Dict[str, Any]) -> str:
        """
        创建一个新阵营。
        - novel_id（必填）：所属小说ID
        - faction_id（必填）：业务层阵营ID
        - name（必填）：阵营正式名称
        """
        if "novel_id" not in data:
            raise ValueError("novel_id is required")
        if "faction_id" not in data or not data["faction_id"]:
            raise ValueError("faction_id is required")
        if "name" not in data or not data["name"]:
            raise ValueError("Faction name cannot be empty")

        # 将 novel_id 转为 ObjectId 存储
        data["novel_id"] = to_object_id(data["novel_id"])

        # 选填字段默认值
        data.setdefault("alias", [])
        data.setdefault("faction_type", "")
        data.setdefault("level_type", "core")
        data.setdefault("parent_faction_id", None)
        data.setdefault("positioning", "")
        data.setdefault("public_stance", "")
        data.setdefault("core_goal", "")
        data.setdefault("hidden_goal", "")
        data.setdefault("resources_and_advantages", [])
        data.setdefault("organization_style", "")
        data.setdefault("core_values", [])
        data.setdefault("conflict_with_mainline", "")
        data.setdefault("is_public", True)
        data.setdefault("influence_scope", "")
        data.setdefault("active_status", "active")
        data.setdefault("expandability", "")
        data.setdefault("tags", [])
        data.setdefault("first_appearance_volume_id", None)
        data.setdefault("first_appearance_chapter_id", None)
        data.setdefault("sort_order", 0)
        data.setdefault("extra", {})

        try:
            return await self.insert_one(data)
        except pymongo.errors.DuplicateKeyError:
            raise DuplicateKeyError(
                f"同一小说下 faction_id={data['faction_id']} 已存在，请使用其他阵营ID"
            )

    # 查询 

    async def get_factions_by_novel(self, novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下所有未软删除阵营，按 sort_order 升序排列。"""
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id},
            sort=[("sort_order", 1)]
        )

    async def get_faction_by_id(self, faction_id: str) -> Dict[str, Any]:
        """根据业务层 faction_id 获取单个阵营，不存在或已删除时抛出 NotFoundError。"""
        faction = await self.find_one({"faction_id": faction_id})
        if not faction:
            raise NotFoundError(f"Faction with faction_id '{faction_id}' not found")
        return faction

    async def get_faction_by_object_id(self, object_id: str) -> Dict[str, Any]:
        """根据 MongoDB _id 获取阵营（用于内部逻辑）。"""
        obj_id = to_object_id(object_id)
        faction = await self.find_one({"_id": obj_id})
        if not faction:
            raise NotFoundError(f"Faction with _id '{object_id}' not found")
        return faction

    async def get_factions_by_level_type(self, novel_id: str, level_type: str) -> List[Dict[str, Any]]:
        """拉取指定小说下特定 level_type 的阵营列表，按 sort_order 升序。"""
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id, "level_type": level_type},
            sort=[("sort_order", 1)]
        )

    async def get_child_factions(self, novel_id: str, parent_faction_id: str) -> List[Dict[str, Any]]:
        """拉取指定小说下某个父级阵营的所有直接子阵营，按 sort_order 升序。"""
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id, "parent_faction_id": parent_faction_id},
            sort=[("sort_order", 1)]
        )

    # 更新 

    async def update_faction_info(self, faction_id: str, update_data: Dict[str, Any]) -> bool:
        """
        更新阵营基础信息（白名单模式）。
        严格禁止修改 novel_id、faction_id、_id 及审计字段。
        """
        allowed_fields = {
            "name", "alias", "faction_type", "level_type", "parent_faction_id",
            "positioning", "public_stance", "core_goal", "hidden_goal",
            "resources_and_advantages", "organization_style", "core_values",
            "conflict_with_mainline", "is_public", "influence_scope",
            "active_status", "expandability", "tags",
            "first_appearance_volume_id", "first_appearance_chapter_id",
            "sort_order", "extra",
        }
        filtered = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not filtered:
            return False

        return await self.update_one({"faction_id": faction_id}, filtered)

    async def batch_update_sort_order(self, novel_id: str, sort_map: Dict[str, int]) -> int:
        """
        批量更新阵营排序权重。
        sort_map 格式: {faction_id: new_sort_order, ...}
        返回成功更新的条数。
        """
        obj_id = to_object_id(novel_id)
        updated = 0
        for fid, new_order in sort_map.items():
            success = await self.update_one(
                {"novel_id": obj_id, "faction_id": fid},
                {"sort_order": new_order}
            )
            if success:
                updated += 1
        return updated

    # 删除与恢复 

    async def soft_delete_faction(self, faction_id: str) -> bool:
        """
        软删除指定阵营，并将以该阵营为父级的子阵营解除挂靠（parent_faction_id 置为 null）。
        """
        # 软删除自身
        success = await self.soft_delete_one({"faction_id": faction_id})
        if not success:
            return False

        # 解除子阵营挂靠
        children_updated = await self.update_many(
            {"parent_faction_id": faction_id},
            {"parent_faction_id": None}
        )
        if children_updated > 0:
            logger.info(f"软删除阵营 {faction_id}，解除 {children_updated} 个子阵营挂靠")

        return True

    async def restore_faction(self, faction_id: str) -> bool:
        """恢复已软删除的指定阵营。"""
        return await self.restore_one({"faction_id": faction_id})

    async def hard_delete_faction(self, faction_id: str) -> bool:
        """
        物理删除指定阵营（不可恢复）。
        删除前将引用该阵营的子阵营 parent_faction_id 置为 null。
        仅允许已软删除的阵营被硬删除。
        """
        # 校验：仅允许删除已软删除的阵营
        faction = await self.find_one({"faction_id": faction_id}, include_deleted=True)
        if not faction:
            raise NotFoundError(f"Faction with faction_id '{faction_id}' not found")
        if not faction.get("is_deleted", False):
            raise ValueError("Only soft-deleted factions can be permanently deleted")

        # 解除子阵营挂靠
        children_updated = await self.update_many(
            {"parent_faction_id": faction_id},
            {"parent_faction_id": None}
        )
        if children_updated > 0:
            logger.info(f"硬删除阵营 {faction_id} 前，解除 {children_updated} 个子阵营挂靠")

        # 物理删除
        return await self.hard_delete_one({"faction_id": faction_id})


faction_repo = FactionRepository()
