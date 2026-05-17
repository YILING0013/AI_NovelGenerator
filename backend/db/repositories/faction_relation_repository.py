import logging
from typing import Any, Dict, List

import pymongo.errors
from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id

logger = logging.getLogger(__name__)


class FactionRelationRepository(BaseRepository):
    def __init__(self):
        """初始化阵营关系仓储，指定集合为'faction_relations'。"""
        super().__init__("faction_relations")

    async def _get_next_relation_id(
        self,
        novel_id: str | ObjectId,
        session: AsyncClientSession | None = None,
    ) -> str:
        """查询该小说下当前最大 active relation_id，返回下一个可用值。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            下一个可用业务关系 ID，格式为 fr_000001。
        """
        obj_id = novel_id if isinstance(novel_id, ObjectId) else to_object_id(novel_id)
        cursor = self.collection.find(
            {"novel_id": obj_id, "is_deleted": False},
            projection={"relation_id": 1},
            session=session,
        ).sort("relation_id", -1).limit(1)
        docs = await cursor.to_list(length=1)
        if docs and docs[0].get("relation_id"):
            # 只解析标准 fr_000001 形式，避免旧数据或人工 ID 阻塞自动编号。
            current_id = docs[0]["relation_id"]
            try:
                num = int(current_id.split("_")[1])
                return f"fr_{num + 1:06d}"
            except (IndexError, ValueError):
                pass
        return "fr_000001"

    async def create_relation(
        self,
        data: Dict[str, Any],
        session: AsyncClientSession | None = None,
    ) -> str:
        """创建一条阵营关系。

        Args:
            data: 阵营关系文档，必须包含 novel_id、relation_id、source_faction_id 和 target_faction_id。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            新关系文档的 ObjectId 字符串。
        """
        required_fields = ("novel_id", "relation_id", "source_faction_id", "target_faction_id", "relation_type")
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f"{field} is required")

        if data["source_faction_id"] == data["target_faction_id"]:
            raise ValueError("source_faction_id and target_faction_id cannot be the same")

        prepared = dict(data)
        prepared["novel_id"] = to_object_id(prepared["novel_id"])
        prepared.setdefault("current_state", "")
        prepared.setdefault("core_conflict", "")
        prepared.setdefault("hidden_tension", "")
        prepared.setdefault("possible_change", "")
        prepared.setdefault("intensity", 3)
        prepared.setdefault("is_active", True)

        try:
            return await self.insert_one(prepared, session=session)
        except pymongo.errors.DuplicateKeyError:
            raise DuplicateKeyError(
                f"同一小说下 relation_id={prepared['relation_id']} 已存在，请使用其他阵营关系ID"
            )

    async def get_relation(
        self,
        novel_id: str,
        relation_id: str,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """根据 novel_id + relation_id 获取单条阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 业务层阵营关系 ID。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营关系文档。
        """
        relation = await self.find_one(
            {"novel_id": to_object_id(novel_id), "relation_id": relation_id},
            session=session,
        )
        if not relation:
            raise NotFoundError(f"Faction relation '{relation_id}' not found in novel {novel_id}")
        return relation

    async def get_relations_by_novel(
        self,
        novel_id: str,
        active_only: bool = True,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """拉取指定小说下的阵营关系列表。

        Args:
            novel_id: 小说 ObjectId 字符串。
            active_only: 是否只返回当前启用关系。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营关系文档列表。
        """
        query: Dict[str, Any] = {"novel_id": to_object_id(novel_id)}
        if active_only:
            query["is_active"] = True
        return await self.find_many(
            query,
            sort=[("intensity", -1), ("relation_id", 1)],
            session=session,
        )

    async def get_relations_by_faction(
        self,
        novel_id: str,
        faction_id: str,
        active_only: bool = True,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """拉取指定阵营作为任一端点参与的关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            active_only: 是否只返回当前启用关系。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营关系文档列表。
        """
        query: Dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "$or": [
                {"source_faction_id": faction_id},
                {"target_faction_id": faction_id},
            ],
        }
        if active_only:
            query["is_active"] = True
        return await self.find_many(
            query,
            sort=[("intensity", -1), ("relation_id", 1)],
            session=session,
        )

    async def update_faction_name_references(
        self,
        novel_id: str,
        faction_id: str,
        name: str,
        session: AsyncClientSession | None = None,
    ) -> int:
        """同步关系文档中冗余保存的阵营显示名称。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            name: 阵营最新显示名称。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            被实际修改的关系文档数量。
        """
        obj_id = to_object_id(novel_id)
        now = get_utc_now()
        source_result = await self.collection.update_many(
            {"novel_id": obj_id, "is_deleted": False, "source_faction_id": faction_id},
            {"$set": {"source_faction_name": name, "updated_at": now}},
            session=session,
        )
        target_result = await self.collection.update_many(
            {"novel_id": obj_id, "is_deleted": False, "target_faction_id": faction_id},
            {"$set": {"target_faction_name": name, "updated_at": now}},
            session=session,
        )
        return source_result.modified_count + target_result.modified_count

    async def deactivate_relations_for_faction_delete(
        self,
        novel_id: str,
        faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> int:
        """软删除阵营时停用它参与的有效关系，并记录停用来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 被软删除的业务阵营 ID。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            被标记为受阵营删除影响的关系数量。
        """
        now = get_utc_now()
        result = await self.collection.update_many(
            {
                "novel_id": to_object_id(novel_id),
                "is_deleted": False,
                "$and": [
                    {
                        "$or": [
                            {"source_faction_id": faction_id},
                            {"target_faction_id": faction_id},
                        ],
                    },
                    {
                        # 只接管当前有效关系，或已经由其他阵营删除动作停用的关系。
                        "$or": [
                            {"is_active": True},
                            {"disabled_by_faction_delete_ids.0": {"$exists": True}},
                        ],
                    },
                ],
            },
            {
                "$set": {"is_active": False, "updated_at": now},
                "$addToSet": {"disabled_by_faction_delete_ids": faction_id},
            },
            session=session,
        )
        return result.modified_count

    async def restore_relations_for_faction(
        self,
        novel_id: str,
        faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> int:
        """恢复阵营时恢复仅因阵营删除而被停用的关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 被恢复的业务阵营 ID。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            被恢复为 active 的关系数量。
        """
        obj_id = to_object_id(novel_id)
        now = get_utc_now()
        scope_query = {
            "novel_id": obj_id,
            "is_deleted": False,
            "$or": [
                {"source_faction_id": faction_id},
                {"target_faction_id": faction_id},
            ],
        }
        await self.collection.update_many(
            scope_query,
            {
                "$pull": {"disabled_by_faction_delete_ids": faction_id},
                "$set": {"updated_at": now},
            },
            session=session,
        )
        restored = await self.collection.update_many(
            {
                **scope_query,
                "disabled_by_faction_delete_ids": {"$size": 0},
            },
            {
                "$set": {"is_active": True, "updated_at": now},
            },
            session=session,
        )
        return restored.modified_count

    async def hard_delete_relations_by_faction(
        self,
        novel_id: str,
        faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> int:
        """物理删除指向已彻底删除阵营的无效关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 已彻底删除的业务阵营 ID。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            被物理删除的关系文档数量。
        """
        result = await self.collection.delete_many(
            {
                "novel_id": to_object_id(novel_id),
                "$or": [
                    {"source_faction_id": faction_id},
                    {"target_faction_id": faction_id},
                ],
            },
            session=session,
        )
        return result.deleted_count


faction_relation_repo = FactionRelationRepository()
