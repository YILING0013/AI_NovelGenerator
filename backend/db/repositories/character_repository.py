"""角色主档 MongoDB 仓储。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError, DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.created_write_compensation import delete_created_documents_cas
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import ensure_initial_version


class CharacterRepository(BaseRepository):
    """封装小说作用域内角色主档的持久化与精确查询。"""

    def __init__(self) -> None:
        """初始化角色仓储。

        Args:
            无。

        Returns:
            无。
        """
        super().__init__("characters")

    async def create_character(
        self,
        data: Mapping[str, Any],
        session: AsyncClientSession | None = None,
    ) -> str:
        """创建单个角色主档。

        Args:
            data: 已完成业务校验且包含小说 ID、业务角色 ID 与名称的文档。
            session: 可选 MongoDB 会话，用于聚合写入。

        Returns:
            新角色 MongoDB ObjectId 的字符串形式。
        """
        prepared = ensure_initial_version(data)
        if not prepared.get("novel_id"):
            raise ValueError("novel_id is required")
        if not prepared.get("character_id"):
            raise ValueError("character_id is required")
        if not str(prepared.get("name") or "").strip():
            raise ValueError("角色名称不能为空")
        if not str(prepared.get("normalized_name") or "").strip():
            # 所有写入必须经过领域规范化，避免旁路调用再次制造无法建立唯一索引的数据。
            raise ValueError("normalized_name is required")

        prepared["novel_id"] = to_object_id(prepared["novel_id"])
        # 新端点从严格整数 0 开始累计依赖写贡献，避免缺失字段具有双重语义。
        prepared.setdefault("dependency_guard_revision", 0)
        try:
            return await self.insert_one(prepared, session=session)
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("同一小说下角色 ID 或活动角色名称已存在") from exc

    async def create_characters(
        self,
        documents: Sequence[Mapping[str, Any]],
        session: AsyncClientSession | None = None,
    ) -> list[str]:
        """按顺序批量创建角色主档。

        Args:
            documents: 已完成整体校验的角色文档序列。
            session: 可选 MongoDB 会话，用于聚合写入。

        Returns:
            新角色 MongoDB ObjectId 字符串列表。
        """
        prepared_documents: list[dict[str, Any]] = []
        for document in documents:
            prepared = ensure_initial_version(document)
            if not prepared.get("novel_id") or not prepared.get("character_id"):
                raise ValueError("批量角色文档缺少 novel_id 或 character_id")
            if not str(prepared.get("name") or "").strip():
                raise ValueError("批量角色文档缺少有效 name")
            if not str(prepared.get("normalized_name") or "").strip():
                # 批量生成链路与单条写入使用同一规范键不变量。
                raise ValueError("批量角色文档缺少 normalized_name")
            # 预分配 Mongo _id，使 standalone 的部分写入也能精确补偿而不依赖业务批次字段。
            prepared.setdefault("_id", ObjectId())
            prepared["novel_id"] = to_object_id(prepared["novel_id"])
            # 批量创建与单条创建共享相同的端点 guard 初始状态。
            prepared.setdefault("dependency_guard_revision", 0)
            prepared_documents.append(prepared)

        try:
            return await self.insert_many(prepared_documents, session=session)
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared_documents,
                    business_key_field="character_id",
                    expected_dependency_guard_revision=0,
                )
            raise DuplicateKeyError("同一小说下角色 ID 或活动角色名称已存在") from exc
        except Exception:
            if session is None:
                await delete_created_documents_cas(
                    self.collection,
                    prepared_documents,
                    business_key_field="character_id",
                    expected_dependency_guard_revision=0,
                )
            raise

    async def get_character(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按小说作用域和稳定业务 ID 获取角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 小说内稳定角色业务 ID。
            include_deleted: 是否允许返回已软删除角色。
            session: 可选 MongoDB 会话，用于聚合读取。

        Returns:
            匹配的角色 BSON 文档。
        """
        character = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
            },
            include_deleted=include_deleted,
            session=session,
        )
        if character is None:
            raise NotFoundError(f"角色 {character_id} 不存在于小说 {novel_id}")
        return character

    async def find_by_creation_idempotency(
        self,
        novel_id: str | ObjectId,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与创建幂等键哈希读取原角色结果。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            key_hash: 已校验原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            首次创建的角色文档；尚未使用该键时返回 None。
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
        novel_id: str | ObjectId,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取核心角色确认批次已经写入的本地 ref 映射。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            按候选局部引用稳定排序的角色文档。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "core_batch_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            sort=[("core_batch_local_ref", 1), ("character_id", 1)],
            session=session,
        )

    async def get_characters_by_novel(
        self,
        novel_id: str | ObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """获取小说内全部未删除角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            session: 可选 MongoDB 会话，用于聚合读取。

        Returns:
            按排序权重和业务 ID 稳定排序的角色文档列表。
        """
        return await self.find_many(
            {"novel_id": to_object_id(novel_id)},
            sort=[("sort_order", 1), ("character_id", 1)],
            session=session,
        )

    async def count_active_protagonists(
        self,
        novel_id: str | ObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """统计小说内活动且未删除的主角。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            session: 可选 MongoDB 会话。

        Returns:
            ``role_type=protagonist`` 且 ``status=active`` 的未删除角色数量。
        """
        return await self.count_documents(
            {
                "novel_id": to_object_id(novel_id),
                "role_type": "protagonist",
                "status": "active",
            },
            session=session,
        )

    async def get_deleted_characters_by_novel(
        self,
        novel_id: str | ObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """获取小说回收站内的全部角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间和业务 ID 稳定排序的软删除角色。
        """
        return await self.find_many(
            {"novel_id": to_object_id(novel_id), "is_deleted": True},
            include_deleted=True,
            sort=[("deleted_at", -1), ("character_id", 1)],
            session=session,
        )

    async def get_deleted_character(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """读取小说回收站内的指定角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的软删除角色文档。
        """
        character = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
                "is_deleted": True,
            },
            include_deleted=True,
            session=session,
        )
        if character is None:
            raise NotFoundError(f"角色 {character_id} 不存在于小说 {novel_id} 的回收站")
        return character

    async def get_characters_by_ids(
        self,
        novel_id: str | ObjectId,
        character_ids: Sequence[str],
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按输入顺序批量获取小说内未删除角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_ids: 待解析的稳定角色业务 ID 序列。
            session: 可选 MongoDB 会话，用于聚合读取。

        Returns:
            已找到的角色文档；结果顺序与去重后的输入 ID 顺序一致。
        """
        ordered_ids = list(dict.fromkeys(character_ids))
        if not ordered_ids:
            return []

        documents = await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": {"$in": ordered_ids},
            },
            session=session,
        )
        documents_by_id = {str(item.get("character_id")): item for item in documents}
        return [documents_by_id[item_id] for item_id in ordered_ids if item_id in documents_by_id]

    async def get_active_by_normalized_name(
        self,
        novel_id: str | ObjectId,
        normalized_name: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """查询小说内同规范化名称的未删除角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            normalized_name: 已执行 NFKC 与 casefold 的角色名称。
            session: 可选 MongoDB 会话，用于聚合读取。

        Returns:
            命中的角色文档；不存在时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "normalized_name": normalized_name,
            },
            session=session,
        )

    async def get_active_by_normalized_names(
        self,
        novel_id: str | ObjectId,
        normalized_names: Sequence[str],
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """批量查询小说内同规范化名称的未删除角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            normalized_names: 已执行 NFKC 与 casefold 的名称序列。
            session: 可选 MongoDB 会话，用于聚合读取。

        Returns:
            命中的角色文档列表。
        """
        names = list(dict.fromkeys(normalized_names))
        if not names:
            return []
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "normalized_name": {"$in": names},
            },
            session=session,
        )

    async def get_max_sort_order(
        self,
        novel_id: str | ObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """读取小说内未删除角色的最大排序权重。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            session: 可选 MongoDB 会话，用于聚合读取。

        Returns:
            当前最大非负排序权重；无角色时返回 0。
        """
        document = await self.collection.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "is_deleted": False,
            },
            projection={"sort_order": 1},
            sort=[("sort_order", -1)],
            session=session,
        )
        if document is None:
            return 0
        try:
            return max(0, int(document.get("sort_order") or 0))
        except (TypeError, ValueError):
            return 0

    async def update_character(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        update_data: Mapping[str, Any],
        *,
        expected_version: int,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按版本原子更新未删除角色的可编辑档案字段。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            update_data: 已经过领域白名单过滤的更新字段。
            expected_version: 客户端基于的角色版本。
            session: 可选 MongoDB 会话。

        Returns:
            更新后的角色；作用域或版本不匹配时返回 None。
        """
        allowed_fields = {
            "name",
            "normalized_name",
            "aliases",
            "role_type",
            "importance_level",
            "gender",
            "age_group",
            "race",
            "identity",
            "appearance",
            "personality",
            "core_desire",
            "core_fear",
            "strengths",
            "weaknesses",
            "abilities",
            "conflict_with_mainline",
            "relationship_with_protagonist",
            "initial_state",
            "growth_direction",
            "story_function",
            "arc_seed",
            "tags",
            "extra",
        }
        filtered = {key: value for key, value in update_data.items() if key in allowed_fields}
        if not filtered:
            raise ValueError("角色更新缺少可写字段")

        now = get_utc_now()
        query = {
            "novel_id": to_object_id(novel_id),
            "character_id": character_id,
            "is_deleted": False,
            "version": expected_version,
        }
        try:
            return await self.collection.find_one_and_update(
                query,
                {
                    "$set": {
                        **filtered,
                        "version": expected_version + 1,
                        "updated_at": now,
                    }
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("同一小说下已存在同名活动角色") from exc

    async def update_character_status(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        status: str,
        *,
        expected_version: int,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按版本原子切换未删除角色状态。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            status: active 或 inactive。
            expected_version: 客户端基于的角色版本。
            session: 可选 MongoDB 会话。

        Returns:
            更新后的角色；作用域或版本不匹配时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
                "is_deleted": False,
                "version": expected_version,
            },
            {
                "$set": {
                    "status": status,
                    "version": expected_version + 1,
                    "updated_at": get_utc_now(),
                }
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def soft_delete_character(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        *,
        expected_version: int,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按版本把角色移入回收站。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            expected_version: 客户端基于的角色版本。
            session: 可选 MongoDB 会话。

        Returns:
            软删除后的角色；作用域或版本不匹配时返回 None。
        """
        now = get_utc_now()
        return await self.collection.find_one_and_update(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
                "is_deleted": False,
                "version": expected_version,
            },
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now,
                    "version": expected_version + 1,
                    "updated_at": now,
                },
                "$addToSet": {"deletion_sources": "manual"},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def restore_character(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        *,
        expected_version: int,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按版本从回收站恢复角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            expected_version: 客户端基于的角色版本。
            session: 可选 MongoDB 会话。

        Returns:
            恢复后的角色；作用域或版本不匹配时返回 None。
        """
        try:
            return await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "character_id": character_id,
                    "is_deleted": True,
                    "version": expected_version,
                },
                {
                    "$set": {
                        "is_deleted": False,
                        "deleted_at": None,
                        "deletion_sources": [],
                        "version": expected_version + 1,
                        "updated_at": get_utc_now(),
                    }
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("同一小说下已存在同名活动角色，无法恢复") from exc

    async def hard_delete_character(
        self,
        novel_id: str | ObjectId,
        character_id: str,
        *,
        expected_version: int,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按版本物理删除一条回收站角色。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            expected_version: 客户端基于的角色版本。
            session: 可选 MongoDB 会话。

        Returns:
            被删除的角色预镜像；作用域或版本不匹配时返回 None。
        """
        return await self.collection.find_one_and_delete(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
                "is_deleted": True,
                "version": expected_version,
            },
            session=session,
        )

    async def delete_characters_exact(
        self,
        novel_id: str | ObjectId,
        character_ids: Sequence[str],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """按明确业务 ID 精确删除本次写入的角色，用于失败补偿。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            character_ids: 本次写入已分配的角色业务 ID。
            session: 可选 MongoDB 会话，用于聚合写入。

        Returns:
            实际删除的角色数量。
        """
        exact_ids = list(dict.fromkeys(character_ids))
        if not exact_ids:
            return 0

        obj_id = to_object_id(novel_id)
        documents = await self.collection.find(
            {"novel_id": obj_id, "character_id": {"$in": exact_ids}},
            projection={"_id": 1, "novel_id": 1, "character_id": 1, "version": 1},
            session=session,
        ).to_list(length=None)
        return await delete_created_documents_cas(
            self.collection,
            documents,
            business_key_field="character_id",
            expected_dependency_guard_revision=0,
            session=session,
        )


character_repo = CharacterRepository()
