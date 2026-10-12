import unicodedata
from typing import Any, Dict, List

import pymongo.errors
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.created_write_compensation import delete_created_documents_cas
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.utils import get_utc_now, to_object_id

def normalize_faction_name(value: str) -> tuple[str, str]:
    """规范化势力显示名并生成活动唯一键。

    Args:
        value: 用户、AI 或历史文档提供的势力名称。

    Returns:
        NFKC 与首尾空白清理后的显示名，以及 casefold 唯一键。
    """
    if not isinstance(value, str):
        raise TypeError("势力名称必须是字符串")
    display_name = unicodedata.normalize("NFKC", value).strip()
    if not display_name:
        raise ValueError("势力名称不能为空")
    if len(display_name) > 80:
        raise ValueError("势力名称不能超过 80 个字符")
    return display_name, display_name.casefold()


class FactionRepository(BaseRepository):
    def __init__(self):
        """初始化阵营仓储，指定集合为'factions'。"""
        super().__init__("factions")

    async def _get_next_faction_id(
        self,
        novel_id: str | ObjectId,
        session: AsyncClientSession | None = None,
    ) -> str:
        """通过原子序列预留下一个阵营业务 ID。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            下一个可用业务阵营 ID，格式为 fac_000001。
        """
        allocated = await id_sequence_repo.allocate_many(
            novel_id,
            "faction",
            "fac",
            1,
            session=session,
        )
        return allocated[0]

    async def create_faction(
        self,
        data: Dict[str, Any],
        session: AsyncClientSession | None = None,
    ) -> str:
        """创建一个新阵营。

        Args:
            data: 阵营文档数据，必须包含 novel_id、faction_id 和 name。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            新阵营文档的 ObjectId 字符串。
        """
        if "novel_id" not in data:
            raise ValueError("novel_id is required")
        if "faction_id" not in data or not data["faction_id"]:
            raise ValueError("faction_id is required")
        if "name" not in data or not str(data["name"]).strip():
            raise ValueError("Faction name cannot be empty")

        prepared = dict(data)
        prepared["novel_id"] = to_object_id(prepared["novel_id"])
        prepared["name"], prepared["normalized_name"] = normalize_faction_name(
            prepared["name"]
        )

        prepared["alias"] = list(prepared.get("alias") or [])
        prepared["faction_type"] = prepared.get("faction_type") or ""
        prepared["level_type"] = prepared.get("level_type") or "core"
        prepared["parent_faction_id"] = prepared.get("parent_faction_id")
        prepared["volume_id"] = (
            to_object_id(prepared["volume_id"])
            if prepared.get("volume_id") is not None
            else None
        )
        prepared["positioning"] = prepared.get("positioning") or ""
        prepared["public_stance"] = prepared.get("public_stance") or ""
        prepared["core_goal"] = prepared.get("core_goal") or ""
        prepared["hidden_goal"] = prepared.get("hidden_goal") or ""
        prepared["resources_and_advantages"] = list(
            prepared.get("resources_and_advantages") or []
        )
        prepared["organization_style"] = prepared.get("organization_style") or ""
        prepared["core_values"] = list(prepared.get("core_values") or [])
        prepared["conflict_with_mainline"] = (
            prepared.get("conflict_with_mainline") or ""
        )
        prepared["is_public"] = bool(prepared.get("is_public", True))
        prepared["influence_scope"] = prepared.get("influence_scope") or ""
        prepared["active_status"] = "active"
        prepared["expandability"] = prepared.get("expandability") or ""
        prepared["tags"] = list(prepared.get("tags") or [])
        prepared.setdefault("first_appearance_volume_id", None)
        prepared.setdefault("first_appearance_chapter_id", None)
        prepared.setdefault("sort_order", 0)
        prepared["extra"] = dict(prepared.get("extra") or {})
        # 势力生命周期跨集合补偿使用内部版本做 CAS，不改变现有公开表单契约。
        prepared.setdefault("version", 1)
        # 势力作为依赖端点时，以严格整数 0 初始化贡献计数。
        prepared.setdefault("dependency_guard_revision", 0)
        prepared.setdefault("deletion_sources", [])

        try:
            return await self.insert_one(prepared, session=session)
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError(
                "同一小说下势力业务 ID、活动规范名或创建幂等键冲突"
            ) from exc

    async def find_by_creation_idempotency(
        self,
        novel_id: str | ObjectId,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与创建幂等键哈希读取首次势力创建结果。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            key_hash: 已校验原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            首次创建的势力文档；尚未使用该键时返回 None。
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
        """按核心势力确认幂等键读取已保存的本地 ref 映射。

        Args:
            novel_id: 小说 ObjectId 或可转换字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            同一确认批次已写入的全部势力文档。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "core_batch_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            sort=[("core_batch_local_ref", 1)],
            session=session,
        )

    async def delete_factions_created_exact(
        self,
        documents: list[dict[str, Any]],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """逐文档补偿仍停留在 v1 的本批新建势力。

        Args:
            documents: 带 Mongo `_id`、小说 ID、势力业务 ID 和版本的本批记录。
            session: 可选 MongoDB 会话。

        Returns:
            实际安全删除的本批势力数量。
        """
        return await delete_created_documents_cas(
            self.collection,
            documents,
            business_key_field="faction_id",
            expected_dependency_guard_revision=0,
            session=session,
        )

    async def get_factions_by_novel(
        self,
        novel_id: str,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """获取指定小说下所有未软删除阵营，按 sort_order 升序排列。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营文档列表。
        """
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id},
            sort=[("sort_order", 1)],
            session=session,
        )

    async def get_faction(
        self,
        novel_id: str,
        faction_id: str,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """根据 novel_id + faction_id 获取单个阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            include_deleted: 是否允许读取软删除阵营。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营文档。
        """
        obj_id = to_object_id(novel_id)
        faction = await self.find_one(
            {"novel_id": obj_id, "faction_id": faction_id},
            include_deleted=include_deleted,
            session=session,
        )
        if not faction:
            raise NotFoundError(f"Faction with faction_id '{faction_id}' not found in novel {novel_id}")
        return faction

    async def get_deleted_faction(
        self,
        novel_id: str,
        faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """获取指定小说下最近一次软删除的阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            已软删除的阵营文档。
        """
        obj_id = to_object_id(novel_id)
        cursor = self.collection.find(
            {"novel_id": obj_id, "faction_id": faction_id, "is_deleted": True},
            session=session,
        ).sort("updated_at", -1).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            raise NotFoundError(f"Deleted faction with faction_id '{faction_id}' not found in novel {novel_id}")
        return docs[0]

    async def get_deleted_factions_by_level_type(
        self,
        novel_id: str,
        level_type: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """拉取指定小说下已软删除的阵营，可按层级过滤。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 可选阵营层级类型。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            已软删除阵营文档列表。
        """
        query: Dict[str, Any] = {"novel_id": to_object_id(novel_id), "is_deleted": True}
        if level_type:
            query["level_type"] = level_type
        cursor = self.collection.find(query, session=session).sort("updated_at", -1)
        return await cursor.to_list(length=None)

    async def get_factions_by_level_type(
        self,
        novel_id: str,
        level_type: str,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """拉取指定小说下特定 level_type 的阵营列表，按 sort_order 升序。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 阵营层级类型。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            阵营文档列表。
        """
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id, "level_type": level_type},
            sort=[("sort_order", 1)],
            session=session,
        )

    async def get_active_core_factions(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """读取小说内全部活动、未删除的核心势力。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            按 sort_order 与 faction_id 稳定排序的核心势力。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "level_type": "core",
                "active_status": "active",
            },
            sort=[("sort_order", 1), ("faction_id", 1)],
            session=session,
        )

    async def count_factions_by_level_type(
        self,
        novel_id: str,
        level_type: str,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> int:
        """统计指定小说下某个层级类型的阵营数量。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 阵营层级类型。
            include_deleted: 是否包含软删除阵营。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            匹配的阵营数量。
        """
        return await self.count_documents(
            {"novel_id": to_object_id(novel_id), "level_type": level_type},
            include_deleted=include_deleted,
            session=session,
        )

    async def get_child_factions(
        self,
        novel_id: str,
        parent_faction_id: str,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """拉取指定小说下某个父级阵营的所有直接子阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_faction_id: 父级业务阵营 ID。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            子阵营文档列表。
        """
        obj_id = to_object_id(novel_id)
        return await self.find_many(
            {"novel_id": obj_id, "parent_faction_id": parent_faction_id},
            sort=[("sort_order", 1)],
            session=session,
        )

    async def _raise_cas_miss(
        self,
        novel_id: str,
        faction_id: str,
        expected_version: int,
        *,
        require_deleted: bool,
        session: AsyncClientSession | None,
    ) -> None:
        """把势力条件写入未命中区分为不存在和版本冲突。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 稳定势力业务 ID。
            expected_version: 调用方持有的公开版本。
            require_deleted: 当前命令是否只允许操作回收站记录。
            session: 可选 MongoDB 会话。

        Returns:
            无；该方法始终抛出领域异常。
        """
        current = await self.collection.find_one(
            {"novel_id": to_object_id(novel_id), "faction_id": faction_id},
            projection={"version": 1, "is_deleted": 1},
            session=session,
        )
        if current is None or bool(current.get("is_deleted")) is not require_deleted:
            state = "回收站中" if require_deleted else "未删除状态下"
            raise NotFoundError(f"势力 '{faction_id}' 在{state}不存在")
        raise DuplicateKeyError(
            f"势力 '{faction_id}' 版本冲突："
            f"expected={expected_version}, actual={current['version']}"
        )

    async def update_faction_info(
        self,
        novel_id: str,
        faction_id: str,
        update_data: Dict[str, Any],
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 更新势力内容和父级，归属层级与卷不可变。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 稳定势力业务 ID。
            update_data: 已由 Service 过滤的内容字段。
            expected_version: 调用方持有的公开版本。
            session: 可选 MongoDB 会话。

        Returns:
            递增一次版本后的完整势力文档。
        """
        forbidden = {
            "novel_id",
            "faction_id",
            "level_type",
            "volume_id",
        }
        if forbidden & update_data.keys():
            raise ValueError("势力更新不得修改身份、层级或归属卷")
        allowed = {
            "name",
            "alias",
            "faction_type",
            "parent_faction_id",
            "positioning",
            "public_stance",
            "core_goal",
            "hidden_goal",
            "resources_and_advantages",
            "organization_style",
            "core_values",
            "conflict_with_mainline",
            "is_public",
            "influence_scope",
            "active_status",
            "expandability",
            "tags",
            "first_appearance_volume_id",
            "first_appearance_chapter_id",
            "sort_order",
            "extra",
        }
        unknown = sorted(update_data.keys() - allowed)
        if unknown:
            raise ValueError("势力更新包含未登记字段: " + ", ".join(unknown))
        fields = dict(update_data)
        if "name" in fields:
            fields["name"], fields["normalized_name"] = normalize_faction_name(
                fields["name"]
            )
        try:
            updated = await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "faction_id": faction_id,
                    "version": expected_version,
                    "is_deleted": False,
                },
                {
                    "$set": {**fields, "updated_at": get_utc_now()},
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("势力更新与活动核心规范名约束冲突") from exc
        if updated is None:
            await self._raise_cas_miss(
                novel_id,
                faction_id,
                expected_version,
                require_deleted=False,
                session=session,
            )
        return updated

    async def update_sort_order_cas(
        self,
        novel_id: str,
        faction_id: str,
        expected_version: int,
        sort_order: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按公开版本 CAS 更新一条活动核心势力的排序权重。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 稳定势力业务 ID。
            expected_version: 调用方持有的公开版本。
            sort_order: 新的非负排序权重。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            递增一次版本后的完整势力文档。
        """
        try:
            updated = await self.collection.find_one_and_update(
                {
                    "novel_id": to_object_id(novel_id),
                    "faction_id": faction_id,
                    "is_deleted": False,
                    "level_type": "core",
                    "active_status": "active",
                    "version": expected_version,
                },
                {
                    "$set": {
                        "sort_order": sort_order,
                        "updated_at": get_utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("势力排序顺序与现有约束冲突") from exc
        if updated is None:
            current = await self.collection.find_one(
                {
                    "novel_id": to_object_id(novel_id),
                    "faction_id": faction_id,
                },
                projection={"version": 1, "is_deleted": 1, "level_type": 1, "active_status": 1},
                session=session,
            )
            if (
                current is None
                or current.get("is_deleted") is True
                or current.get("level_type") != "core"
                or current.get("active_status") != "active"
            ):
                raise NotFoundError(f"活动核心势力 '{faction_id}' 不存在于小说 {novel_id}")
            raise DuplicateKeyError(
                f"势力 '{faction_id}' 版本冲突："
                f"expected={expected_version}, actual={current['version']}"
            )
        return updated

    async def soft_delete_faction(
        self,
        novel_id: str,
        faction_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 将核心势力移入回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            expected_version: 调用方持有的公开版本。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            软删除并递增版本后的完整势力文档。
        """
        now = get_utc_now()
        deleted = await self.collection.find_one_and_update(
            {
                "novel_id": to_object_id(novel_id),
                "faction_id": faction_id,
                "version": expected_version,
                "is_deleted": False,
            },
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now,
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
                faction_id,
                expected_version,
                require_deleted=False,
                session=session,
            )
        return deleted

    async def restore_faction(
        self,
        novel_id: str,
        faction_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """以 CAS 仅移除回收站势力的 user 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            expected_version: 调用方持有的公开版本。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            恢复并递增版本后的完整势力文档。
        """
        current = await self.collection.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "faction_id": faction_id,
                "version": expected_version,
                "is_deleted": True,
            },
            session=session,
        )
        if current is None:
            await self._raise_cas_miss(
                novel_id,
                faction_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        sources = list(dict.fromkeys(current.get("deletion_sources") or []))
        if "user" not in sources:
            raise DuplicateKeyError("势力没有可恢复的 user 删除来源")
        remaining_sources = [source for source in sources if source != "user"]
        try:
            restored = await self.collection.find_one_and_update(
                {
                    "_id": current["_id"],
                    "version": expected_version,
                    "is_deleted": True,
                    "deletion_sources": sources,
                },
                {
                    "$set": {
                        "is_deleted": bool(remaining_sources),
                        "deleted_at": (
                            current.get("deleted_at") if remaining_sources else None
                        ),
                        "deletion_sources": remaining_sources,
                        "updated_at": get_utc_now(),
                    },
                    "$inc": {"version": 1},
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except pymongo.errors.DuplicateKeyError as exc:
            raise DuplicateKeyError("势力恢复后与活动作用域规范名约束冲突") from exc
        if restored is None:
            await self._raise_cas_miss(
                novel_id,
                faction_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        return restored

    async def hard_delete_faction(
        self,
        novel_id: str,
        faction_id: str,
        expected_version: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """物理删除已软删除的指定阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            expected_version: 调用方持有的公开版本。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际删除成功时返回 True。
        """
        deleted = await self.collection.find_one_and_delete(
            {
                "novel_id": to_object_id(novel_id),
                "faction_id": faction_id,
                "version": expected_version,
                "is_deleted": True,
            },
            session=session,
        )
        if deleted is None:
            await self._raise_cas_miss(
                novel_id,
                faction_id,
                expected_version,
                require_deleted=True,
                session=session,
            )
        return True


faction_repo = FactionRepository()
