"""全书级正式物品 MongoDB 仓储。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import ensure_initial_version


class ItemRepository(BaseRepository):
    """封装小说作用域内物品的直接持久化原语。"""

    def __init__(self) -> None:
        """绑定 items 集合。

        Args:
            无。

        Returns:
            None。
        """
        super().__init__("items")

    async def create_item(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """插入已完成领域校验的新物品。

        Args:
            data: 含稳定 ID、小说 ID、顺序和正式内容的文档。
            session: 可选 MongoDB 会话。

        Returns:
            含 MongoDB ID、版本和审计字段的完整物品。
        """
        document = ensure_initial_version(data)
        if not document.get("item_id") or not document.get("novel_id"):
            raise ValueError("物品缺少 item_id 或 novel_id")
        if not str(document.get("normalized_name") or "").strip():
            raise ValueError("物品缺少 normalized_name")
        now = document.get("created_at") or get_utc_now()
        document.update(
            {
                "_id": document.get("_id") or ObjectId(),
                "novel_id": to_object_id(document["novel_id"]),
                "version": 1,
                "dependency_guard_revision": 0,
                "is_deleted": False,
                "deleted_at": None,
                "created_at": now,
                "updated_at": document.get("updated_at") or now,
            }
        )
        try:
            await self.collection.insert_one(document, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError(
                "物品 ID、活动规范名、活动顺序或创建幂等键冲突"
            ) from exc
        return document

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取同小说人工创建幂等键对应的已发布物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 创建幂等键摘要。
            session: 可选 MongoDB 会话。

        Returns:
            命中的已发布物品；不存在时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "creation_idempotency_key_hash": key_hash,
                "item_write_pending_token": None,
            },
            include_deleted=True,
            session=session,
        )

    async def list_items(
        self,
        novel_id: str,
        *,
        q: str | None = None,
        item_type: str | None = None,
        lifecycle_status: str | None = None,
        owner_character_id: str | None = None,
        controlling_faction_id: str | None = None,
        current_location_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按小说和可选字段筛选未删除、已发布物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选内容搜索词。
            item_type: 可选物品类型筛选值。
            lifecycle_status: 可选生命周期状态筛选值。
            owner_character_id: 可选当前持有角色 ID。
            controlling_faction_id: 可选当前控制势力 ID。
            current_location_id: 可选当前地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按活动顺序和稳定 ID 排列的匹配物品。
        """
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "item_write_pending_token": None,
        }
        if item_type is not None:
            query["item_type"] = item_type
        if lifecycle_status is not None:
            query["lifecycle_status"] = lifecycle_status
        if owner_character_id is not None:
            query["owner_character_id"] = owner_character_id
        if controlling_faction_id is not None:
            query["controlling_faction_id"] = controlling_faction_id
        if current_location_id is not None:
            query["current_location_id"] = current_location_id
        if q is not None:
            pattern = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"aliases": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
                {"tags": {"$regex": pattern, "$options": "i"}},
            ]
        return await self.find_many(
            query,
            sort=[("order_index", 1), ("item_id", 1)],
            session=session,
        )

    async def list_deleted_items(
        self,
        novel_id: str,
        *,
        q: str | None = None,
        item_type: str | None = None,
        lifecycle_status: str | None = None,
        owner_character_id: str | None = None,
        controlling_faction_id: str | None = None,
        current_location_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取物品回收站并应用与活动列表一致的筛选。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选内容搜索词。
            item_type: 可选物品类型筛选值。
            lifecycle_status: 可选生命周期状态筛选值。
            owner_character_id: 可选删除前持有角色 ID。
            controlling_faction_id: 可选删除前控制势力 ID。
            current_location_id: 可选删除前所在地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间和稳定 ID 排列的匹配回收站物品。
        """
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "is_deleted": True,
            "item_write_pending_token": None,
        }
        if item_type is not None:
            query["item_type"] = item_type
        if lifecycle_status is not None:
            query["lifecycle_status"] = lifecycle_status
        if owner_character_id is not None:
            query["owner_character_id"] = owner_character_id
        if controlling_faction_id is not None:
            query["controlling_faction_id"] = controlling_faction_id
        if current_location_id is not None:
            query["current_location_id"] = current_location_id
        if q is not None:
            pattern = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"aliases": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
                {"tags": {"$regex": pattern, "$options": "i"}},
            ]
        return await self.find_many(
            query,
            include_deleted=True,
            sort=[("deleted_at", -1), ("item_id", 1)],
            session=session,
        )

    async def get_item(
        self,
        novel_id: str,
        item_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按小说作用域和稳定 ID 读取已发布物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            include_deleted: 是否允许返回回收站物品。
            session: 可选 MongoDB 会话。

        Returns:
            指定小说内的已发布物品。
        """
        item = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "item_id": item_id,
                "item_write_pending_token": None,
            },
            include_deleted=include_deleted,
            session=session,
        )
        if item is None:
            raise NotFoundError(f"物品 {item_id} 不存在于小说 {novel_id}")
        return item

    async def get_deleted_item(
        self,
        novel_id: str,
        item_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """读取小说回收站中的指定已发布物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            session: 可选 MongoDB 会话。

        Returns:
            指定的已发布回收站物品。
        """
        item = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "item_id": item_id,
                "is_deleted": True,
                "item_write_pending_token": None,
            },
            include_deleted=True,
            session=session,
        )
        if item is None:
            raise NotFoundError(f"物品 {item_id} 不存在于小说 {novel_id} 的回收站")
        return item

    async def list_active_items(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取小说内完整活动物品集合。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            按 1-based 顺序和稳定 ID 排列的全部活动物品。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "item_write_pending_token": None,
            },
            sort=[("order_index", 1), ("item_id", 1)],
            session=session,
        )

    async def find_active_by_normalized_name(
        self,
        novel_id: str,
        normalized_name: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取同小说下相同规范名的活动物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            normalized_name: 已完成统一规范化的物品名称。
            session: 可选 MongoDB 会话。

        Returns:
            命中的活动物品；不存在时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "normalized_name": normalized_name,
                "item_write_pending_token": None,
            },
            session=session,
        )

    async def update_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
        fields: Mapping[str, Any],
        *,
        increment_version: bool,
        write_time: Any,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按完整物品预镜像执行精确 CAS 更新。

        Args:
            snapshot: 当前命令读取的完整物品预镜像。
            fields: 已完成领域校验的目标字段。
            increment_version: 是否把公开版本递增一次。
            write_time: 本次命令统一使用的写入时间。
            session: 可选 MongoDB 会话。

        Returns:
            精确更新后的物品；预镜像已变化时返回 None。
        """
        query = {
            "_id": snapshot["_id"],
            "novel_id": snapshot["novel_id"],
            "item_id": snapshot["item_id"],
            "version": snapshot["version"],
            "dependency_guard_revision": snapshot["dependency_guard_revision"],
            "is_deleted": bool(snapshot["is_deleted"]),
            "order_index": snapshot["order_index"],
            "item_write_pending_token": snapshot.get("item_write_pending_token"),
            "updated_at": snapshot["updated_at"],
        }
        update: dict[str, Any] = {"$set": {**dict(fields), "updated_at": write_time}}
        if increment_version:
            update["$inc"] = {"version": 1}
        try:
            return await self.collection.find_one_and_update(
                query,
                update,
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("物品活动规范名或顺序冲突") from exc

    async def restore_snapshot_exact(
        self,
        written: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """仅在物品仍为本次写后镜像时恢复写前镜像。

        Args:
            written: 当前命令产生的完整写后镜像。
            snapshot: 当前命令最初读取的完整写前镜像。
            session: 可选 MongoDB 会话。

        Returns:
            精确恢复写前镜像时返回 True。
        """
        query = {
            "_id": written["_id"],
            "novel_id": written["novel_id"],
            "item_id": written["item_id"],
            "version": written["version"],
            "dependency_guard_revision": written["dependency_guard_revision"],
            "is_deleted": bool(written["is_deleted"]),
            "order_index": written["order_index"],
            "item_write_pending_token": written.get("item_write_pending_token"),
            "updated_at": written["updated_at"],
        }
        try:
            result = await self.collection.replace_one(
                query,
                dict(snapshot),
                session=session,
            )
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("物品补偿恢复发生唯一键冲突") from exc
        return result.matched_count == 1

    async def publish_created_exact(
        self,
        document: Mapping[str, Any],
        pending_token: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """精确移除创建或恢复物品的内部未发布标记。

        Args:
            document: 创建或恢复流程持有的完整物品镜像。
            pending_token: 当前写命令的内部未发布标记。
            session: 可选 MongoDB 会话。

        Returns:
            已发布的完整物品；精确条件不匹配时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "_id": document["_id"],
                "version": document["version"],
                "dependency_guard_revision": document["dependency_guard_revision"],
                "item_write_pending_token": {"$in": [pending_token, None]},
                "is_deleted": bool(document["is_deleted"]),
                "updated_at": document["updated_at"],
            },
            {"$set": {"item_write_pending_token": None}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def delete_manual_created_exact(
        self,
        document: Mapping[str, Any],
        *,
        key_hash: str,
        request_hash: str,
        pending_token: str,
    ) -> bool:
        """精确补偿仍处初始状态的待发布或刚发布人工物品。

        Args:
            document: 本次创建写入的完整初始镜像。
            key_hash: 创建幂等键摘要。
            request_hash: 创建规范载荷摘要。
            pending_token: 本次创建的内部待发布标记。

        Returns:
            精确删除初始物品时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": document["_id"],
                "novel_id": document["novel_id"],
                "item_id": document["item_id"],
                "version": 1,
                "dependency_guard_revision": 0,
                "is_deleted": False,
                "order_index": document["order_index"],
                "updated_at": document["updated_at"],
                "item_write_pending_token": {"$in": [pending_token, None]},
                "creation_idempotency_key_hash": key_hash,
                "creation_request_hash": request_hash,
            }
        )
        return result.deleted_count == 1

    async def delete_generated_exact(
        self,
        document_ids: Sequence[ObjectId],
        *,
        key_hash: str,
        request_hash: str,
        pending_token: str,
    ) -> int:
        """精确补偿本批仍处初始状态的生成物品。

        Args:
            document_ids: 本命令插入前预分配的 MongoDB ObjectId。
            key_hash: 批量确认幂等键摘要。
            request_hash: 批量确认规范请求摘要。
            pending_token: 本批物品的内部待发布标记。

        Returns:
            满足批次与初始状态守卫的实际删除数量。
        """
        deleted = 0
        for document_id in reversed(list(document_ids)):
            result = await self.collection.delete_one(
                {
                    "_id": document_id,
                    "version": 1,
                    "dependency_guard_revision": 0,
                    "is_deleted": False,
                    "item_write_pending_token": {"$in": [pending_token, None]},
                    "generation_idempotency_key_hash": key_hash,
                    "generation_request_hash": request_hash,
                }
            )
            deleted += result.deleted_count
        return deleted

    async def hard_delete_item(
        self,
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """按回收站预镜像精确物理删除物品。

        Args:
            snapshot: 已通过生命周期校验的回收站物品预镜像。
            session: 可选 MongoDB 会话。

        Returns:
            精确删除目标物品时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": snapshot["_id"],
                "novel_id": snapshot["novel_id"],
                "item_id": snapshot["item_id"],
                "version": snapshot["version"],
                "dependency_guard_revision": snapshot["dependency_guard_revision"],
                "is_deleted": True,
                "item_write_pending_token": None,
                "updated_at": snapshot["updated_at"],
            },
            session=session,
        )
        return result.deleted_count == 1

    async def count_protected_references(
        self,
        novel_id: str,
        item_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, int]:
        """统计物品引用；篇章包含回收站记录，避免恢复后引用失效。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            session: 可选 MongoDB 会话。

        Returns:
            各消费者集合的引用数量和总数。
        """
        obj_id = to_object_id(novel_id)
        # 章节不直接引用物品，保留旧影响响应中的零计数字段。
        counts: dict[str, int] = {"chapters": 0}
        for collection in ("arcs", "scenes", "foreshadowings"):
            query: dict[str, Any] = {"novel_id": obj_id}
            if collection in {"arcs", "scenes"}:
                query["planning.item_ids"] = item_id
            else:
                query["$or"] = [
                    {"item_ids": item_id},
                    {"entity_refs.item_ids": item_id},
                ]
            counts[collection] = await BaseRepository(collection).count_documents(
                query,
                include_deleted=collection in {"arcs", "scenes"},
                session=session,
            )
        counts["total"] = sum(counts.values())
        return counts


item_repo = ItemRepository()


__all__ = ["ItemRepository", "item_repo"]
