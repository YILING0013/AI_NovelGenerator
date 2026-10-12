"""全书级角色关系 MongoDB 仓储。"""

from __future__ import annotations

from typing import Any

import pymongo.errors
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.created_write_compensation import delete_created_documents_cas
from backend.db.errors import DuplicateKeyError, NotFoundError, VersionConflictError
from backend.db.utils import get_utc_now, to_object_id


class CharacterRelationRepository(BaseRepository):
    """封装全书级角色关系的精确读写与生成提交辅助操作。"""

    def __init__(self) -> None:
        """初始化角色关系仓储。

        Args:
            无。

        Returns:
            无。
        """
        super().__init__("character_relations")

    async def insert_relations(
        self,
        documents: list[dict[str, Any]],
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按给定业务 ID 批量插入角色关系并返回正式文档。

        Args:
            documents: 已完成业务校验且包含 novel_id、relation_id 与端点的关系文档。
            session: 可选 MongoDB 会话，用于纳入上层生成确认事务。

        Returns:
            按输入顺序返回刚写入的角色关系文档。
        """
        if not documents:
            return []

        prepared_documents: list[dict[str, Any]] = []
        relation_ids: list[str] = []
        for document in documents:
            prepared = dict(document)
            required_fields = (
                "novel_id",
                "relation_id",
                "source_character_id",
                "target_character_id",
                "normalized_source_character_id",
                "normalized_target_character_id",
                "relation_type",
            )
            missing_fields = [field for field in required_fields if not prepared.get(field)]
            if missing_fields:
                raise ValueError(f"角色关系缺少必填字段: {', '.join(missing_fields)}")

            prepared.pop("_id", None)
            # 预分配 Mongo _id，standalone 部分写入时可只删除本次文档。
            prepared["_id"] = ObjectId()
            prepared["novel_id"] = to_object_id(prepared["novel_id"])
            prepared.setdefault("current_state", "")
            prepared.setdefault("core_conflict", "")
            prepared.setdefault("hidden_tension", "")
            prepared.setdefault("possible_change", "")
            prepared.setdefault("story_value", "")
            prepared.setdefault("intensity", 3)
            prepared.setdefault("user_is_active", bool(prepared.get("is_active", True)))
            prepared.setdefault("disabled_by_character_ids", [])
            prepared["is_active"] = bool(
                prepared["user_is_active"]
                and not prepared["disabled_by_character_ids"]
                and not prepared.get("is_deleted", False)
            )
            prepared.setdefault("sort_order", 0)
            prepared.setdefault("version", 1)
            prepared.setdefault("is_deleted", False)
            prepared.setdefault("deleted_at", None)
            prepared.setdefault("deletion_sources", [])
            relation_ids.append(str(prepared["relation_id"]))
            prepared_documents.append(prepared)

        if len(relation_ids) != len(set(relation_ids)):
            raise DuplicateKeyError("同一批次不能重复使用 relation_id")

        try:
            await self.insert_many(prepared_documents, session=session)
            created = await self.get_relations_by_ids(
                str(prepared_documents[0]["novel_id"]),
                relation_ids,
                session=session,
            )
            if len(created) != len(prepared_documents):
                raise RuntimeError("角色关系批量写入后未能完整回读")
            return created
        except (pymongo.errors.DuplicateKeyError, pymongo.errors.BulkWriteError) as exc:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared_documents,
                    business_key_field="relation_id",
                )
            raise DuplicateKeyError("角色关系业务 ID 或活动语义边已存在") from exc
        except Exception:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared_documents,
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
    ) -> dict[str, Any]:
        """按小说与稳定业务 ID 获取一条未删除关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            include_deleted: 是否允许读取回收站中的关系。
            session: 可选 MongoDB 会话。

        Returns:
            命中的角色关系文档。
        """
        relation = await self.find_one(
            {"novel_id": to_object_id(novel_id), "relation_id": relation_id},
            include_deleted=include_deleted,
            session=session,
        )
        if relation is None:
            raise NotFoundError(f"角色关系 '{relation_id}' 不存在于小说 {novel_id}")
        return relation

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与创建幂等键哈希读取原关系结果。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            key_hash: 已校验原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            首次创建的关系文档；尚未使用该键时返回 None。
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
    ) -> list[dict[str, Any]]:
        """按批次幂等键读取已写入的角色关系 local ref 映射。

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

    async def list_relations(
        self,
        novel_id: str,
        *,
        character_id: str | None = None,
        relation_type: str | None = None,
        is_active: bool | None = True,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出小说内角色关系，可按端点、类型和有效状态过滤。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 可选角色端点业务 ID。
            relation_type: 可选关系类型。
            is_active: 是否只返回指定有效状态；None 表示不按该字段过滤。
            session: 可选 MongoDB 会话。

        Returns:
            按 sort_order 与 relation_id 稳定排序的关系文档列表。
        """
        query: dict[str, Any] = {"novel_id": to_object_id(novel_id)}
        if character_id:
            query["$or"] = [
                {"source_character_id": character_id},
                {"target_character_id": character_id},
            ]
        if relation_type:
            query["relation_type"] = relation_type
        if is_active is not None:
            query["is_active"] = is_active
        return await self.find_many(
            query,
            sort=[("sort_order", 1), ("relation_id", 1)],
            session=session,
        )

    async def get_relations_by_ids(
        self,
        novel_id: str,
        relation_ids: list[str] | tuple[str, ...],
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按显式业务 ID 集合读取未删除角色关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_ids: 需要读取的稳定关系业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按调用方 ID 顺序排列的关系文档列表。
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
        by_id = {str(document["relation_id"]): document for document in documents}
        return [by_id[relation_id] for relation_id in ordered_ids if relation_id in by_id]

    async def find_active_semantic_relations(
        self,
        novel_id: str,
        semantic_edges: list[tuple[str, str, str]],
        *,
        exclude_relation_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """查找与给定规范化语义边冲突的活动关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            semantic_edges: 规范化 source、target、relation_type 三元组列表。
            exclude_relation_id: 更新时需要排除的当前关系 ID。
            session: 可选 MongoDB 会话。

        Returns:
            与任一语义三元组匹配的活动关系文档。
        """
        unique_edges = list(dict.fromkeys(semantic_edges))
        if not unique_edges:
            return []
        edge_queries = [
            {
                "normalized_source_character_id": source_id,
                "normalized_target_character_id": target_id,
                "relation_type": relation_type,
            }
            for source_id, target_id, relation_type in unique_edges
        ]
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "is_active": True,
            "$or": edge_queries,
        }
        if exclude_relation_id is not None:
            query["relation_id"] = {"$ne": exclude_relation_id}
        return await self.find_many(
            query,
            session=session,
        )

    async def list_deleted_relations(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出小说回收站中的角色关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间倒序排列的已软删除关系。
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
        """把条件更新未命中区分为不存在和版本冲突。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的版本。
            require_deleted: 当前命令是否只允许操作回收站记录。
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
            raise NotFoundError(f"角色关系 '{relation_id}' 在{state}不存在")
        actual_version = current["version"]
        raise VersionConflictError(
            f"角色关系 '{relation_id}' 版本冲突：expected={expected_version}, actual={actual_version}"
        )

    async def update_relation(
        self,
        novel_id: str,
        relation_id: str,
        update_data: dict[str, Any],
        expected_version: int,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 更新一条角色关系并递增版本。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            update_data: 已由领域服务过滤的更新字段。
            expected_version: 调用方持有的乐观锁版本。
            include_deleted: 是否要求更新回收站记录。
            session: 可选 MongoDB 会话。

        Returns:
            更新后的完整关系文档。
        """
        query = {
            "novel_id": to_object_id(novel_id),
            "relation_id": relation_id,
            "version": expected_version,
            "is_deleted": include_deleted,
        }
        set_fields = {**update_data, "updated_at": get_utc_now()}
        try:
            updated = await self.collection.find_one_and_update(
                query,
                {"$set": set_fields, "$inc": {"version": 1}},
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("角色关系活动语义边已存在") from exc
        if updated is None:
            await self._raise_cas_miss(
                novel_id,
                relation_id,
                expected_version,
                require_deleted=include_deleted,
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
    ) -> dict[str, Any]:
        """以 CAS 将角色关系移入回收站并保留用户启停意图。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。
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
        disabled_by_character_ids: list[str],
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 恢复角色关系并按用户意图重算有效态。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。
            effective_active: 端点复核后计算出的实际有效态。
            disabled_by_character_ids: 按当前端点状态重算的阻断来源。
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
                        "disabled_by_character_ids": disabled_by_character_ids,
                        "is_active": effective_active,
                        "updated_at": get_utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("角色关系恢复后将与现有活动语义边冲突") from exc
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
        """以 CAS 物理删除回收站中的一条角色关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。
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

    async def block_relations_for_character(
        self,
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """记录角色失效阻断来源并停用其参与的关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 失效角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            本次新加阻断来源的关系数量。
        """
        now = get_utc_now()
        result = await self.collection.update_many(
            {
                "novel_id": to_object_id(novel_id),
                "is_deleted": False,
                "disabled_by_character_ids": {"$ne": character_id},
                "$or": [
                    {"source_character_id": character_id},
                    {"target_character_id": character_id},
                ],
            },
            {
                "$set": {"is_active": False, "updated_at": now},
                "$addToSet": {"disabled_by_character_ids": character_id},
                "$inc": {"version": 1},
            },
            session=session,
        )
        return result.modified_count

    async def unblock_relations_for_character(
        self,
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """移除角色阻断来源并按用户意图恢复关系有效态。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 已恢复角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            本次移除阻断来源的关系数量。
        """
        remaining_blockers = {
            "$setDifference": [
                "$disabled_by_character_ids",
                [character_id],
            ]
        }
        result = await self.collection.update_many(
            {
                "novel_id": to_object_id(novel_id),
                "is_deleted": False,
                "disabled_by_character_ids": character_id,
            },
            [
                {
                    "$set": {
                        "disabled_by_character_ids": remaining_blockers,
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
        return result.modified_count

    async def delete_relations_exact(
        self,
        novel_id: str,
        relation_ids: list[str] | tuple[str, ...],
        session: AsyncClientSession | None = None,
    ) -> int:
        """物理删除本次命令明确创建的关系 ID，用于失败补偿。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_ids: 本次命令分配并可能已写入的关系业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            实际删除的文档数量。
        """
        exact_ids = list(dict.fromkeys(relation_ids))
        if not exact_ids:
            return 0
        obj_id = to_object_id(novel_id)
        documents = await self.collection.find(
            {"novel_id": obj_id, "relation_id": {"$in": exact_ids}},
            projection={"_id": 1, "novel_id": 1, "relation_id": 1, "version": 1},
            session=session,
        ).to_list(length=None)
        return await delete_created_documents_cas(
            self.collection,
            documents,
            business_key_field="relation_id",
            session=session,
        )


character_relation_repo = CharacterRelationRepository()
