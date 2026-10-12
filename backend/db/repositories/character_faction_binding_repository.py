"""全书级角色—势力绑定 MongoDB 仓储。"""

from __future__ import annotations

from typing import Any

import pymongo.errors
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.created_write_compensation import delete_created_documents_cas
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id


class CharacterFactionBindingRepository(BaseRepository):
    """封装角色—势力绑定的创建、查询与精确失败补偿。"""

    def __init__(self) -> None:
        """初始化角色—势力绑定仓储。

        Args:
            无。

        Returns:
            无。
        """
        super().__init__("character_faction_bindings")

    async def insert_bindings(
        self,
        documents: list[dict[str, Any]],
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按已分配业务 ID 批量插入角色—势力绑定。

        Args:
            documents: 已完成端点和唯一性校验的绑定文档。
            session: 可选 MongoDB 会话，用于纳入生成确认事务。

        Returns:
            按输入顺序返回刚写入的正式绑定文档。
        """
        if not documents:
            return []

        prepared_documents: list[dict[str, Any]] = []
        binding_ids: list[str] = []
        for document in documents:
            prepared = dict(document)
            required_fields = (
                "novel_id",
                "binding_id",
                "character_id",
                "faction_id",
                "membership_type",
            )
            missing_fields = [field for field in required_fields if not prepared.get(field)]
            if missing_fields:
                raise ValueError(f"角色—势力绑定缺少必填字段: {', '.join(missing_fields)}")

            prepared.pop("_id", None)
            # 预分配 Mongo _id，standalone 部分写入时可只删除本次文档。
            prepared["_id"] = ObjectId()
            prepared["novel_id"] = to_object_id(prepared["novel_id"])
            prepared.setdefault("role_title", None)
            prepared.setdefault("public_status", None)
            prepared.setdefault("loyalty_level", None)
            # 本轮只创建全书级初始绑定，不允许写入任何卷范围。
            prepared["joined_volume_id"] = None
            prepared["left_volume_id"] = None
            # 用户启停意图与角色/势力不可用造成的自动阻断分离，恢复实体时不得误启用用户停用绑定。
            prepared.setdefault("user_is_active", bool(prepared.get("is_active", True)))
            prepared.setdefault("disabled_by_character_ids", [])
            prepared.setdefault("disabled_by_faction_ids", [])
            prepared["is_active"] = bool(
                prepared["user_is_active"]
                and not prepared["disabled_by_character_ids"]
                and not prepared["disabled_by_faction_ids"]
                and not prepared.get("is_deleted", False)
            )
            prepared.setdefault("notes", None)
            prepared.setdefault("sort_order", 0)
            prepared.setdefault("version", 1)
            prepared.setdefault("is_deleted", False)
            prepared.setdefault("deleted_at", None)
            prepared.setdefault("deletion_sources", [])
            binding_ids.append(str(prepared["binding_id"]))
            prepared_documents.append(prepared)

        if len(binding_ids) != len(set(binding_ids)):
            raise DuplicateKeyError("同一批次不能重复使用 binding_id")

        try:
            await self.insert_many(prepared_documents, session=session)
            created = await self.get_bindings_by_ids(
                str(prepared_documents[0]["novel_id"]),
                binding_ids,
                session=session,
            )
            if len(created) != len(prepared_documents):
                raise RuntimeError("角色—势力绑定批量写入后未能完整回读")
            return created
        except (pymongo.errors.DuplicateKeyError, pymongo.errors.BulkWriteError) as exc:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared_documents,
                    business_key_field="binding_id",
                )
            raise DuplicateKeyError(
                "角色—势力绑定业务 ID、主归属或活动语义绑定已存在"
            ) from exc
        except Exception:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared_documents,
                    business_key_field="binding_id",
                )
            raise

    async def get_binding(
        self,
        novel_id: str,
        binding_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按小说与稳定业务 ID 获取一条未删除绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            include_deleted: 是否允许读取回收站中的绑定。
            session: 可选 MongoDB 会话。

        Returns:
            命中的角色—势力绑定文档。
        """
        binding = await self.find_one(
            {"novel_id": to_object_id(novel_id), "binding_id": binding_id},
            include_deleted=include_deleted,
            session=session,
        )
        if binding is None:
            raise NotFoundError(f"角色—势力绑定 '{binding_id}' 不存在于小说 {novel_id}")
        return binding

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与创建幂等键哈希读取原绑定结果。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            key_hash: 已校验原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            首次创建的绑定文档；尚未使用该键时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "creation_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            session=session,
        )

    async def find_by_core_batch_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取核心角色确认批次已经写入的绑定本地 ref 映射。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            按候选角色引用稳定排序的绑定文档。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "core_batch_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            sort=[("core_batch_local_ref", 1), ("binding_id", 1)],
            session=session,
        )

    async def list_bindings(
        self,
        novel_id: str,
        *,
        character_id: str | None = None,
        faction_id: str | None = None,
        membership_type: str | None = None,
        is_active: bool | None = True,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出小说内绑定，可按角色、势力、类型和有效状态过滤。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 可选角色业务 ID。
            faction_id: 可选势力业务 ID。
            membership_type: 可选成员类型。
            is_active: 是否按活动状态过滤；None 表示不筛选。
            session: 可选 MongoDB 会话。

        Returns:
            按 sort_order 与 binding_id 稳定排序的绑定文档列表。
        """
        query: dict[str, Any] = {"novel_id": to_object_id(novel_id)}
        if character_id:
            query["character_id"] = character_id
        if faction_id:
            query["faction_id"] = faction_id
        if membership_type:
            query["membership_type"] = membership_type
        if is_active is not None:
            query["is_active"] = is_active
        return await self.find_many(
            query,
            sort=[("sort_order", 1), ("binding_id", 1)],
            session=session,
        )

    async def list_deleted_bindings(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出小说回收站中的角色—势力绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间倒序、业务 ID 正序排列的软删除绑定。
        """
        return await self.find_many(
            {"novel_id": to_object_id(novel_id), "is_deleted": True},
            include_deleted=True,
            sort=[("deleted_at", -1), ("binding_id", 1)],
            session=session,
        )

    async def get_bindings_by_ids(
        self,
        novel_id: str,
        binding_ids: list[str] | tuple[str, ...],
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按显式业务 ID 集合读取未删除绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_ids: 需要读取的稳定绑定业务 ID。
            include_deleted: 是否允许返回回收站中的绑定。
            session: 可选 MongoDB 会话。

        Returns:
            按调用方 ID 顺序排列的绑定文档列表。
        """
        ordered_ids = list(dict.fromkeys(binding_ids))
        if not ordered_ids:
            return []
        documents = await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "binding_id": {"$in": ordered_ids},
            },
            include_deleted=include_deleted,
            session=session,
        )
        by_id = {str(document["binding_id"]): document for document in documents}
        return [by_id[binding_id] for binding_id in ordered_ids if binding_id in by_id]

    async def find_active_primary_bindings(
        self,
        novel_id: str,
        character_ids: list[str] | tuple[str, ...],
        *,
        exclude_binding_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """查询指定角色当前存在的活动主归属。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_ids: 需要检查的角色业务 ID。
            exclude_binding_id: 可选需要排除的当前绑定业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            命中的活动 primary 绑定文档。
        """
        unique_ids = list(dict.fromkeys(character_ids))
        if not unique_ids:
            return []
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "character_id": {"$in": unique_ids},
            "membership_type": "primary",
            "is_active": True,
        }
        if exclude_binding_id is not None:
            query["binding_id"] = {"$ne": exclude_binding_id}
        return await self.find_many(
            query,
            session=session,
        )

    async def list_primary_bindings_for_character(
        self,
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出角色全部未删除 primary 绑定，供切换并发护栏复核。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按业务 ID 稳定排序的未删除 primary 绑定。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
                "membership_type": "primary",
            },
            sort=[("binding_id", 1)],
            session=session,
        )

    async def find_active_semantic_bindings(
        self,
        novel_id: str,
        semantic_bindings: list[tuple[str, str, str]],
        *,
        exclude_binding_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """查找重复的活动角色—势力—成员类型组合。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            semantic_bindings: character_id、faction_id、membership_type 三元组。
            exclude_binding_id: 可选需要排除的当前绑定业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            与任一三元组匹配的活动绑定文档。
        """
        unique_bindings = list(dict.fromkeys(semantic_bindings))
        if not unique_bindings:
            return []
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "is_active": True,
            "$or": [
                {
                    "character_id": character_id,
                    "faction_id": faction_id,
                    "membership_type": membership_type,
                }
                for character_id, faction_id, membership_type in unique_bindings
            ],
        }
        if exclude_binding_id is not None:
            query["binding_id"] = {"$ne": exclude_binding_id}
        return await self.find_many(
            query,
            session=session,
        )

    async def find_by_primary_switch_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与主归属切换幂等键读取首次成功的目标绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            key_hash: 已校验原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            首次切换的目标绑定；尚未成功时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "primary_switch_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            session=session,
        )

    async def mark_primary_switch_claims_complete(
        self,
        novel_id: str,
        claims: list[tuple[str, int]],
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> None:
        """把本次已停用旧 primary 的内部切换声明标记为完成。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            claims: 旧 primary 业务 ID 与本次写后公开版本。
            key_hash: 当前主归属切换幂等键哈希。
            session: 可选 MongoDB 会话。

        Returns:
            无；任一精确声明已漂移时抛出 409 领域冲突。
        """
        for binding_id, version in claims:
            result = await self.collection.update_one(
                {
                    "novel_id": to_object_id(novel_id),
                    "binding_id": binding_id,
                    "version": version,
                    "is_deleted": False,
                    "replaced_by_primary_switch_key_hash": key_hash,
                },
                {"$set": {"replaced_by_primary_switch_completed": True}},
                session=session,
            )
            if result.matched_count != 1:
                raise DuplicateKeyError(
                    f"旧主归属绑定 '{binding_id}' 的切换完成声明已并发漂移"
                )

    async def _raise_cas_miss(
        self,
        novel_id: str,
        binding_id: str,
        expected_version: int,
        *,
        require_deleted: bool,
        session: AsyncClientSession | None,
    ) -> None:
        """把绑定条件写入未命中区分为不存在与版本冲突。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的版本。
            require_deleted: 当前命令是否只允许操作回收站记录。
            session: 可选 MongoDB 会话。

        Returns:
            无；该方法始终抛出领域异常。
        """
        current = await self.collection.find_one(
            {"novel_id": to_object_id(novel_id), "binding_id": binding_id},
            projection={"version": 1, "is_deleted": 1},
            session=session,
        )
        if current is None or bool(current.get("is_deleted")) is not require_deleted:
            state = "回收站中" if require_deleted else "未删除状态下"
            raise NotFoundError(f"角色—势力绑定 '{binding_id}' 在{state}不存在")
        actual_version = current["version"]
        raise DuplicateKeyError(
            f"角色—势力绑定 '{binding_id}' 版本冲突："
            f"expected={expected_version}, actual={actual_version}"
        )

    async def update_binding(
        self,
        novel_id: str,
        binding_id: str,
        update_data: dict[str, Any],
        expected_version: int,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 更新一条绑定并只递增一次公开版本。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            update_data: 已由领域服务过滤的更新字段。
            expected_version: 调用方持有的乐观锁版本。
            include_deleted: 是否要求更新回收站记录。
            session: 可选 MongoDB 会话。

        Returns:
            更新后的完整绑定文档。
        """
        try:
            updated = await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "binding_id": binding_id,
                    "version": expected_version,
                    "is_deleted": include_deleted,
                },
                {
                    "$set": {**update_data, "updated_at": get_utc_now()},
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("角色—势力活动绑定或主归属冲突") from exc
        if updated is None:
            await self._raise_cas_miss(
                novel_id,
                binding_id,
                expected_version,
                require_deleted=include_deleted,
                session=session,
            )
        return updated

    async def soft_delete_binding(
        self,
        novel_id: str,
        binding_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 将绑定移入回收站并保留用户启停意图。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。
            session: 可选 MongoDB 会话。

        Returns:
            软删除后的完整绑定文档。
        """
        now = get_utc_now()
        deleted = await self.collection.find_one_and_update(
            {
                "novel_id": to_object_id(novel_id),
                "binding_id": binding_id,
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
                binding_id,
                expected_version,
                require_deleted=False,
                session=session,
            )
        return deleted

    async def restore_binding(
        self,
        novel_id: str,
        binding_id: str,
        expected_version: int,
        *,
        effective_active: bool,
        disabled_by_character_ids: list[str],
        disabled_by_faction_ids: list[str],
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 恢复绑定并按用户意图和端点事实重算有效态。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。
            effective_active: 恢复后的实际有效态。
            disabled_by_character_ids: 当前角色端点阻断来源。
            disabled_by_faction_ids: 当前势力端点阻断来源。
            session: 可选 MongoDB 会话。

        Returns:
            恢复后的完整绑定文档。
        """
        try:
            restored = await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "binding_id": binding_id,
                    "version": expected_version,
                    "is_deleted": True,
                },
                {
                    "$set": {
                        "is_deleted": False,
                        "deleted_at": None,
                        "deletion_sources": [],
                        "disabled_by_character_ids": disabled_by_character_ids,
                        "disabled_by_faction_ids": disabled_by_faction_ids,
                        "is_active": effective_active,
                        "updated_at": get_utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("角色—势力绑定恢复后将与活动绑定冲突") from exc
        if restored is None:
            await self._raise_cas_miss(
                novel_id,
                binding_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        return restored

    async def hard_delete_binding(
        self,
        novel_id: str,
        binding_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """以 CAS 物理删除回收站中的一条绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。
            session: 可选 MongoDB 会话。

        Returns:
            删除成功时返回 True。
        """
        deleted = await self.collection.find_one_and_delete(
            {
                "novel_id": to_object_id(novel_id),
                "binding_id": binding_id,
                "version": expected_version,
                "is_deleted": True,
            },
            session=session,
        )
        if deleted is None:
            await self._raise_cas_miss(
                novel_id,
                binding_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        return True

    async def delete_bindings_exact(
        self,
        novel_id: str,
        binding_ids: list[str] | tuple[str, ...],
        session: AsyncClientSession | None = None,
    ) -> int:
        """物理删除本次命令明确创建的绑定 ID，用于失败补偿。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_ids: 本次命令分配并可能已写入的绑定业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            实际删除的文档数量。
        """
        exact_ids = list(dict.fromkeys(binding_ids))
        if not exact_ids:
            return 0
        obj_id = to_object_id(novel_id)
        documents = await self.collection.find(
            {"novel_id": obj_id, "binding_id": {"$in": exact_ids}},
            projection={"_id": 1, "novel_id": 1, "binding_id": 1, "version": 1},
            session=session,
        ).to_list(length=None)
        return await delete_created_documents_cas(
            self.collection,
            documents,
            business_key_field="binding_id",
            session=session,
        )


character_faction_binding_repo = CharacterFactionBindingRepository()
