import logging
from typing import Any, Dict, List

import pymongo.errors
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.created_write_compensation import delete_created_documents_cas
from backend.db.errors import DuplicateKeyError, NotFoundError, VersionConflictError
from backend.db.utils import get_utc_now, to_object_id

logger = logging.getLogger(__name__)


class FactionRelationRepository(BaseRepository):
    def __init__(self):
        """初始化阵营关系仓储，指定集合为'faction_relations'。"""
        super().__init__("faction_relations")

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
        created = await self.insert_relations([data], session=session)
        return str(created[0]["_id"])

    def _prepare_relation_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """补齐阵营关系持久化默认值并预分配 MongoDB ID。

        Args:
            data: 已通过领域校验的阵营关系字段。

        Returns:
            可直接批量插入的独立 BSON 文档。
        """
        required_fields = (
            "novel_id",
            "relation_id",
            "source_faction_id",
            "target_faction_id",
            "normalized_source_faction_id",
            "normalized_target_faction_id",
            "relation_type",
        )
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            raise ValueError(f"阵营关系缺少必填字段: {', '.join(missing_fields)}")
        if data["source_faction_id"] == data["target_faction_id"]:
            raise ValueError("阵营关系不能指向自身")

        prepared = dict(data)
        prepared.pop("_id", None)
        prepared["_id"] = ObjectId()
        prepared["novel_id"] = to_object_id(prepared["novel_id"])
        prepared.setdefault("current_state", "")
        prepared.setdefault("core_conflict", "")
        prepared.setdefault("hidden_tension", "")
        prepared.setdefault("possible_change", "")
        prepared.setdefault("intensity", 3)
        prepared.setdefault("user_is_active", bool(prepared.get("is_active", True)))
        prepared.setdefault("disabled_by_faction_ids", [])
        prepared.setdefault("version", 1)
        prepared.setdefault("sort_order", 0)
        prepared.setdefault("deletion_sources", [])
        prepared.setdefault("is_deleted", False)
        prepared.setdefault("deleted_at", None)
        prepared["is_active"] = bool(
            prepared["user_is_active"]
            and not prepared["disabled_by_faction_ids"]
            and not prepared["is_deleted"]
        )
        return prepared

    async def insert_relations(
        self,
        documents: List[Dict[str, Any]],
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """批量插入已校验关系，并在 standalone 失败时精确补偿本批文档。

        Args:
            documents: 已分配稳定业务 ID 的关系文档列表。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            按输入顺序返回刚写入的完整关系文档。
        """
        if not documents:
            return []
        prepared = [self._prepare_relation_document(document) for document in documents]
        relation_ids = [str(document["relation_id"]) for document in prepared]
        if len(relation_ids) != len(set(relation_ids)):
            raise DuplicateKeyError("同一批次不能重复使用阵营关系 relation_id")
        try:
            await self.insert_many(prepared, session=session)
            created = await self.get_relations_by_ids(
                str(prepared[0]["novel_id"]),
                relation_ids,
                session=session,
            )
            if len(created) != len(prepared):
                raise RuntimeError("阵营关系批量写入后未能完整回读")
            return created
        except (pymongo.errors.DuplicateKeyError, pymongo.errors.BulkWriteError) as exc:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared,
                    business_key_field="relation_id",
                )
            raise DuplicateKeyError("阵营关系业务 ID 或活动语义边已存在") from exc
        except Exception:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared,
                    business_key_field="relation_id",
                )
            raise

    async def get_relation(
        self,
        novel_id: str,
        relation_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """根据 novel_id + relation_id 获取单条阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 业务层阵营关系 ID。
            include_deleted: 是否允许读取回收站记录。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营关系文档。
        """
        relation = await self.find_one(
            {"novel_id": to_object_id(novel_id), "relation_id": relation_id},
            include_deleted=include_deleted,
            session=session,
        )
        if not relation:
            raise NotFoundError(f"Faction relation '{relation_id}' not found in novel {novel_id}")
        return relation

    async def get_relations_by_novel(
        self,
        novel_id: str,
        active_only: bool | None = True,
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
        if active_only is not None:
            query["is_active"] = active_only
        return await self.find_many(
            query,
            sort=[("intensity", -1), ("relation_id", 1)],
            session=session,
        )

    async def get_relations_by_faction(
        self,
        novel_id: str,
        faction_id: str,
        active_only: bool | None = True,
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
        if active_only is not None:
            query["is_active"] = active_only
        return await self.find_many(
            query,
            sort=[("intensity", -1), ("relation_id", 1)],
            session=session,
        )

    async def get_relations_by_ids(
        self,
        novel_id: str,
        relation_ids: List[str],
        *,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """按显式业务 ID 集合读取未删除阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_ids: 稳定阵营关系业务 ID 列表。
            session: 可选 MongoDB 会话。

        Returns:
            按调用方 ID 顺序排列的关系文档。
        """
        ordered_ids = list(dict.fromkeys(relation_ids))
        if not ordered_ids:
            return []
        documents = await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "relation_id": {"$in": ordered_ids},
            },
            session=session,
        )
        documents_by_id = {str(item["relation_id"]): item for item in documents}
        return [documents_by_id[item_id] for item_id in ordered_ids if item_id in documents_by_id]

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any] | None:
        """按创建幂等键哈希读取首次阵营关系结果。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            首次创建的关系；尚未使用该键时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "creation_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            session=session,
        )

    async def find_by_batch_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """按批次幂等键读取已写入的阵营关系 local ref 映射。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            按 batch_local_ref 稳定排序的当前批次关系文档。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "batch_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            sort=[("batch_local_ref", 1), ("relation_id", 1)],
            session=session,
        )

    async def find_active_semantic_relations(
        self,
        novel_id: str,
        semantic_edges: List[tuple[str, str, str]],
        *,
        exclude_relation_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """查找与给定规范化语义边冲突的活动阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            semantic_edges: 规范化 source、target、relation_type 三元组。
            exclude_relation_id: 更新时排除的当前关系 ID。
            session: 可选 MongoDB 会话。

        Returns:
            与任一语义边匹配的活动关系。
        """
        edges = list(dict.fromkeys(semantic_edges))
        if not edges:
            return []
        query: Dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "is_active": True,
            "$or": [
                {
                    "normalized_source_faction_id": source_id,
                    "normalized_target_faction_id": target_id,
                    "relation_type": relation_type,
                }
                for source_id, target_id, relation_type in edges
            ],
        }
        if exclude_relation_id is not None:
            query["relation_id"] = {"$ne": exclude_relation_id}
        return await self.find_many(query, session=session)

    async def list_deleted_relations(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """列出小说回收站中的阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间倒序排列的关系。
        """
        return await self.find_many(
            {"novel_id": to_object_id(novel_id), "is_deleted": True},
            include_deleted=True,
            sort=[("deleted_at", -1), ("relation_id", 1)],
            session=session,
        )

    async def _raise_cas_miss(
        self,
        novel_id: str,
        relation_id: str,
        expected_version: int,
        *,
        require_deleted: bool,
        session: AsyncClientSession | None,
    ) -> None:
        """把阵营关系条件写入未命中区分为不存在和版本冲突。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。
            require_deleted: 当前命令是否要求目标位于回收站。
            session: 可选 MongoDB 会话。

        Returns:
            无；该方法始终抛出领域异常。
        """
        current = await self.collection.find_one(
            {"novel_id": to_object_id(novel_id), "relation_id": relation_id},
            projection={"version": 1, "is_deleted": 1},
            session=session,
        )
        if current is None or bool(current.get("is_deleted")) is not require_deleted:
            state = "回收站中" if require_deleted else "未删除状态下"
            raise NotFoundError(f"阵营关系 '{relation_id}' 在{state}不存在")
        actual_version = current["version"]
        raise VersionConflictError(
            f"阵营关系 '{relation_id}' 版本冲突：expected={expected_version}, actual={actual_version}"
        )

    async def update_relation(
        self,
        novel_id: str,
        relation_id: str,
        update_data: Dict[str, Any],
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """以 CAS 更新一条未删除阵营关系并递增版本。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            update_data: 已由领域服务过滤的更新字段。
            expected_version: 调用方持有的乐观锁版本。
            session: 可选 MongoDB 会话。

        Returns:
            更新后的完整关系文档。
        """
        try:
            updated = await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "relation_id": relation_id,
                    "version": expected_version,
                    "is_deleted": False,
                },
                {
                    "$set": {**update_data, "updated_at": get_utc_now()},
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("阵营关系活动语义边已存在") from exc
        if updated is None:
            await self._raise_cas_miss(
                novel_id,
                relation_id,
                expected_version,
                require_deleted=False,
                session=session,
            )
        return updated

    async def soft_delete_relation(
        self,
        novel_id: str,
        relation_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """以 CAS 将阵营关系移入回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。
            session: 可选 MongoDB 会话。

        Returns:
            软删除后的完整关系文档。
        """
        now = get_utc_now()
        deleted = await self.collection.find_one_and_update(
            {
                "novel_id": to_object_id(novel_id),
                "relation_id": relation_id,
                "version": expected_version,
                "is_deleted": False,
            },
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now,
                    "is_active": False,
                    "updated_at": now,
                },
                "$addToSet": {"deletion_sources": "user"},
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if deleted is None:
            await self._raise_cas_miss(
                novel_id,
                relation_id,
                expected_version,
                require_deleted=False,
                session=session,
            )
        return deleted

    async def restore_relation(
        self,
        novel_id: str,
        relation_id: str,
        expected_version: int,
        *,
        effective_active: bool,
        disabled_by_faction_ids: List[str],
        source_faction_name: str,
        target_faction_name: str,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """以 CAS 恢复阵营关系并写入重算后的有效态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。
            effective_active: 按用户意图与端点状态计算的有效态。
            disabled_by_faction_ids: 按当前端点状态重算的阻断来源。
            source_faction_name: 恢复时重新投影的来源阵营名称。
            target_faction_name: 恢复时重新投影的目标阵营名称。
            session: 可选 MongoDB 会话。

        Returns:
            恢复后的完整关系文档。
        """
        try:
            restored = await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "relation_id": relation_id,
                    "version": expected_version,
                    "is_deleted": True,
                },
                {
                    "$set": {
                        "is_deleted": False,
                        "deleted_at": None,
                        "deletion_sources": [],
                        "disabled_by_faction_ids": disabled_by_faction_ids,
                        "is_active": effective_active,
                        "source_faction_name": source_faction_name,
                        "target_faction_name": target_faction_name,
                        "updated_at": get_utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("阵营关系恢复后将与现有活动语义边冲突") from exc
        if restored is None:
            await self._raise_cas_miss(
                novel_id,
                relation_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        return restored

    async def hard_delete_relation(
        self,
        novel_id: str,
        relation_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """以 CAS 物理删除回收站中的一条阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。
            session: 可选 MongoDB 会话。

        Returns:
            删除成功时返回 True。
        """
        deleted = await self.collection.find_one_and_delete(
            {
                "novel_id": to_object_id(novel_id),
                "relation_id": relation_id,
                "version": expected_version,
                "is_deleted": True,
            },
            session=session,
        )
        if deleted is None:
            await self._raise_cas_miss(
                novel_id,
                relation_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        return True

    async def delete_relations_exact(
        self,
        novel_id: str,
        relation_ids: List[str],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """按明确业务 ID 精确删除本批新建关系，用于失败补偿。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_ids: 本次调用新分配的关系 ID。
            session: 可选 MongoDB 会话。

        Returns:
            实际删除的关系数量。
        """
        ids = list(dict.fromkeys(relation_ids))
        if not ids:
            return 0
        obj_id = to_object_id(novel_id)
        documents = await self.collection.find(
            {"novel_id": obj_id, "relation_id": {"$in": ids}},
            projection={"_id": 1, "novel_id": 1, "relation_id": 1, "version": 1},
            session=session,
        ).to_list(length=None)
        return await delete_created_documents_cas(
            self.collection,
            documents,
            business_key_field="relation_id",
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
            {
                "novel_id": obj_id,
                "source_faction_id": faction_id,
                "source_faction_name": {"$ne": name},
            },
            {
                "$set": {"source_faction_name": name, "updated_at": now},
                "$inc": {"version": 1},
            },
            session=session,
        )
        target_result = await self.collection.update_many(
            {
                "novel_id": obj_id,
                "target_faction_id": faction_id,
                "target_faction_name": {"$ne": name},
            },
            {
                "$set": {"target_faction_name": name, "updated_at": now},
                "$inc": {"version": 1},
            },
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
                "disabled_by_faction_ids": {"$ne": faction_id},
                "$or": [
                    {"source_faction_id": faction_id},
                    {"target_faction_id": faction_id},
                ],
            },
            {
                "$set": {"is_active": False, "updated_at": now},
                "$addToSet": {"disabled_by_faction_ids": faction_id},
                "$inc": {"version": 1},
            },
            session=session,
        )
        return result.modified_count

    async def block_relations_for_faction(
        self,
        novel_id: str,
        faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> int:
        """因阵营删除或非 active 状态阻断其参与的关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 当前不可用的阵营业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            本次新加阻断来源的关系数量。
        """
        return await self.deactivate_relations_for_faction_delete(
            novel_id,
            faction_id,
            session=session,
        )

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
        remaining_blockers = {
            "$setDifference": [
                "$disabled_by_faction_ids",
                [faction_id],
            ]
        }
        restored = await self.collection.update_many(
            {
                "novel_id": to_object_id(novel_id),
                "is_deleted": False,
                "disabled_by_faction_ids": faction_id,
            },
            [
                {
                    "$set": {
                        "disabled_by_faction_ids": remaining_blockers,
                        "is_active": {
                            "$and": [
                                "$user_is_active",
                                {"$eq": [{"$size": remaining_blockers}, 0]},
                            ]
                        },
                        "updated_at": get_utc_now(),
                        "version": {"$add": ["$version", 1]},
                    }
                }
            ],
            session=session,
        )
        return restored.modified_count

    async def unblock_relations_for_faction(
        self,
        novel_id: str,
        faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> int:
        """阵营恢复 active 后移除其关系阻断来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 已恢复 active 的阵营业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            本次移除阻断来源的关系数量。
        """
        return await self.restore_relations_for_faction(
            novel_id,
            faction_id,
            session=session,
        )

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
