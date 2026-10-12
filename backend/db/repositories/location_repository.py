"""全书级正式地点 MongoDB 仓储。"""

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


class LocationRepository(BaseRepository):
    """封装小说作用域内地点的直接持久化原语。"""

    def __init__(self) -> None:
        """绑定 locations 集合。"""
        super().__init__("locations")

    async def create_location(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """插入已完成领域校验的新地点。

        Args:
            data: 含稳定地点 ID、小说 ID、顺序及正式内容的文档。
            session: 可选 MongoDB 会话。

        Returns:
            含 MongoDB ``_id``、版本与审计字段的完整地点。
        """
        document = ensure_initial_version(data)
        if not document.get("location_id") or not document.get("novel_id"):
            raise ValueError("地点缺少 location_id 或 novel_id")
        if not str(document.get("normalized_name") or "").strip():
            raise ValueError("地点缺少 normalized_name")
        now = document.get("created_at") or get_utc_now()
        document.update(
            {
                "_id": document.get("_id") or ObjectId(),
                "novel_id": to_object_id(document["novel_id"]),
                "version": 1,
                "dependency_guard_revision": 0,
                "is_deleted": False,
                "deleted_at": None,
                "detached_parent_location_id": document.get(
                    "detached_parent_location_id"
                ),
                "created_at": now,
                "updated_at": document.get("updated_at") or now,
            }
        )
        try:
            await self.collection.insert_one(document, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError(
                "地点 ID、同父规范名、同父顺序或创建幂等键冲突"
            ) from exc
        return document

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取同小说人工创建幂等键对应的地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            已创建地点；该键尚未使用时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "creation_idempotency_key_hash": key_hash,
                "location_order_pending_token": None,
            },
            include_deleted=True,
            session=session,
        )

    async def list_locations(
        self,
        novel_id: str,
        *,
        q: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
        parent_location_id: str | None = None,
        associated_faction_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按小说与可选筛选读取未删除地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选名称、别名、描述或标签搜索词。
            location_type: 可选地点类型。
            status: 可选正式状态。
            parent_location_id: 可选父地点；空字符串表示根级。
            associated_faction_id: 可选关联势力 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按父级、1-based 顺序和稳定 ID 排列的地点。
        """
        query: dict[str, Any] = {"novel_id": to_object_id(novel_id)}
        if location_type is not None:
            query["location_type"] = location_type
        if status is not None:
            query["status"] = status
        if parent_location_id is not None:
            query["parent_location_id"] = parent_location_id or None
        if associated_faction_id is not None:
            query["associated_faction_ids"] = associated_faction_id
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
            sort=[("parent_location_id", 1), ("order_index", 1), ("location_id", 1)],
            session=session,
        )

    async def list_deleted_locations(
        self,
        novel_id: str,
        *,
        q: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
        parent_location_id: str | None = None,
        associated_faction_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取地点回收站并应用与活动列表相同的内容筛选。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选搜索词。
            location_type: 可选地点类型。
            status: 可选正式状态。
            parent_location_id: 可选原父地点；空字符串表示原根级。
            associated_faction_id: 可选关联势力 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间倒序排列的回收站地点。
        """
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "is_deleted": True,
        }
        if location_type is not None:
            query["location_type"] = location_type
        if status is not None:
            query["status"] = status
        if parent_location_id is not None:
            query["parent_location_id"] = parent_location_id or None
        if associated_faction_id is not None:
            query["associated_faction_ids"] = associated_faction_id
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
            sort=[("deleted_at", -1), ("location_id", 1)],
            session=session,
        )

    async def get_location(
        self,
        novel_id: str,
        location_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按小说作用域和稳定 ID 读取地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            include_deleted: 是否允许返回回收站地点。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的完整地点 BSON 文档。
        """
        location = await self.find_one(
            {"novel_id": to_object_id(novel_id), "location_id": location_id},
            include_deleted=include_deleted,
            session=session,
        )
        if location is None:
            raise NotFoundError(f"地点 {location_id} 不存在于小说 {novel_id}")
        return location

    async def get_deleted_location(
        self,
        novel_id: str,
        location_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """读取小说回收站中的指定地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的已删除地点 BSON 文档。
        """
        location = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "location_id": location_id,
                "is_deleted": True,
            },
            include_deleted=True,
            session=session,
        )
        if location is None:
            raise NotFoundError(f"地点 {location_id} 不存在于小说 {novel_id} 的回收站")
        return location

    async def list_siblings(
        self,
        novel_id: str,
        parent_location_id: str | None,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取同父全部未删除地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_location_id: 父地点 ID；根级为 None。
            session: 可选 MongoDB 会话。

        Returns:
            按 1-based 顺序与稳定 ID 排列的兄弟地点。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "parent_location_id": parent_location_id,
            },
            sort=[("order_index", 1), ("location_id", 1)],
            session=session,
        )

    async def list_direct_children(
        self,
        novel_id: str,
        parent_location_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取指定地点的直接子地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_location_id: 父地点稳定 ID。
            include_deleted: 是否同时返回已删除子地点。
            session: 可选 MongoDB 会话。

        Returns:
            活动子地点按顺序、回收站子地点按稳定 ID排列的完整文档。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "parent_location_id": parent_location_id,
            },
            include_deleted=include_deleted,
            sort=[("is_deleted", 1), ("order_index", 1), ("location_id", 1)],
            session=session,
        )

    async def find_active_by_parent_and_name(
        self,
        novel_id: str,
        parent_location_id: str | None,
        normalized_name: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """查询同父下同规范名的未删除地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_location_id: 父地点 ID；根级为 None。
            normalized_name: 名称规范键。
            session: 可选 MongoDB 会话。

        Returns:
            命中的活动地点；不存在时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "parent_location_id": parent_location_id,
                "normalized_name": normalized_name,
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
        """按完整地点预镜像执行精确 CAS 更新。

        Args:
            snapshot: 当前写入前的完整地点。
            fields: 已由 Service 验证的字段变化。
            increment_version: 是否递增唯一公开版本。
            write_time: Service 预分配的 BSON 毫秒时间。
            session: 可选 MongoDB 会话。

        Returns:
            精确写后地点；预镜像已变化时返回 None。
        """
        identity = {
            "_id": snapshot["_id"],
            "novel_id": snapshot["novel_id"],
            "location_id": snapshot["location_id"],
            "version": snapshot["version"],
            "dependency_guard_revision": snapshot["dependency_guard_revision"],
            "is_deleted": bool(snapshot["is_deleted"]),
            "parent_location_id": snapshot.get("parent_location_id"),
            "order_index": snapshot["order_index"],
            "updated_at": snapshot["updated_at"],
        }
        update: dict[str, Any] = {"$set": {**dict(fields), "updated_at": write_time}}
        if increment_version:
            update["$inc"] = {"version": 1}
        try:
            return await self.collection.find_one_and_update(
                identity,
                update,
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("地点同父规范名或顺序冲突") from exc

    async def restore_snapshot_exact(
        self,
        written: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """仅在地点仍为本次写后镜像时恢复写前镜像。

        Args:
            written: 本命令写后的精确地点。
            snapshot: 本命令最初读取的完整地点。
            session: 可选 MongoDB 会话。

        Returns:
            精确恢复成功时返回 True。
        """
        query = {
            "_id": written["_id"],
            "novel_id": written["novel_id"],
            "location_id": written["location_id"],
            "version": written["version"],
            "dependency_guard_revision": written["dependency_guard_revision"],
            "is_deleted": bool(written["is_deleted"]),
            "parent_location_id": written.get("parent_location_id"),
            "order_index": written["order_index"],
            "updated_at": written["updated_at"],
        }
        try:
            result = await self.collection.replace_one(query, dict(snapshot), session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("地点补偿恢复发生唯一键冲突") from exc
        return result.matched_count == 1

    async def hard_delete_location(
        self,
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """按回收站预镜像精确物理删除地点。

        Args:
            snapshot: 已校验的回收站地点预镜像。
            session: 可选 MongoDB 会话。

        Returns:
            精确删除成功时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": snapshot["_id"],
                "novel_id": snapshot["novel_id"],
                "location_id": snapshot["location_id"],
                "version": snapshot["version"],
                "dependency_guard_revision": snapshot["dependency_guard_revision"],
                "is_deleted": True,
                "updated_at": snapshot["updated_at"],
            },
            session=session,
        )
        return result.deleted_count == 1

    async def delete_created_exact(
        self,
        document_ids: Sequence[ObjectId],
        *,
        key_hash: str,
        request_hash: str,
        pending_token: str,
    ) -> int:
        """删除仍停留在初始状态的本批新建地点。

        Args:
            document_ids: 本命令在插入前预分配的 MongoDB ObjectId。
            key_hash: 批量确认幂等键哈希。
            request_hash: 批量确认规范请求哈希。
            pending_token: 本批地点尚未公开时持有的命令标记。

        Returns:
            满足批次与初始版本守卫的实际删除数量。
        """
        if not document_ids:
            return 0
        deleted = 0
        # 逆拓扑删除可保证父级仍被本批子级引用时不会先消失。
        for document_id in reversed(list(document_ids)):
            result = await self.collection.delete_one(
                {
                    "_id": document_id,
                    "version": 1,
                    "dependency_guard_revision": 0,
                    "location_order_pending_token": {"$in": [pending_token, None]},
                    "is_deleted": False,
                    "generation_idempotency_key_hash": key_hash,
                    "generation_request_hash": request_hash,
                }
            )
            deleted += result.deleted_count
        return deleted

    async def delete_manual_created_exact(
        self,
        document_id: ObjectId,
        *,
        key_hash: str,
        request_hash: str,
        pending_token: str,
    ) -> bool:
        """精确补偿仍处初始状态的单条人工创建地点。

        Args:
            document_id: 创建前预分配的 MongoDB ObjectId。
            key_hash: 人工创建幂等键哈希。
            request_hash: 人工创建规范请求哈希。
            pending_token: 创建完成前持有的内部命令标记。

        Returns:
            精确删除成功时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": document_id,
                "version": 1,
                "dependency_guard_revision": 0,
                "location_order_pending_token": {"$in": [pending_token, None]},
                "is_deleted": False,
                "creation_idempotency_key_hash": key_hash,
                "creation_request_hash": request_hash,
            }
        )
        return result.deleted_count == 1

    async def publish_created_exact(
        self,
        document: Mapping[str, Any],
        pending_token: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """在顺序后态通过后移除新地点的内部未发布标记。

        Args:
            document: 仍为初始版本的本命令新地点镜像。
            pending_token: 创建时写入的内部命令标记。
            session: 可选 MongoDB 会话。

        Returns:
            精确发布后的地点；镜像已变化时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "_id": document["_id"],
                "version": document["version"],
                "dependency_guard_revision": document["dependency_guard_revision"],
                "location_order_pending_token": {"$in": [pending_token, None]},
                "is_deleted": False,
            },
            {"$set": {"location_order_pending_token": None}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def count_protected_references(
        self,
        novel_id: str,
        location_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, int]:
        """统计地点引用；篇章包含回收站记录，避免恢复后引用失效。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            规则、结构、场景、物品与伏笔的分项及总引用数。
        """
        obj_id = to_object_id(novel_id)
        contracts = {
            "world_rules": ("world_rules", "scope_entity_ids"),
            "volumes": ("volumes", "location_ids"),
            "arcs": ("arcs", "planning.location_ids"),
            "scenes": ("scenes", "planning.location_ids"),
            "items": ("items", "current_location_id"),
            "foreshadowings": ("foreshadowings", "location_ids"),
        }
        # 章节通过场景取得地点，旧影响响应仍保留 chapters=0。
        counts: dict[str, int] = {"chapters": 0}
        for label, (collection, field) in contracts.items():
            query: dict[str, Any] = {"novel_id": obj_id, field: location_id}
            if label == "items":
                query["item_write_pending_token"] = None
            counts[label] = await BaseRepository(collection).count_documents(
                query,
                include_deleted=label in {"volumes", "arcs", "scenes"},
                session=session,
            )
        counts["total"] = sum(counts.values())
        return counts

    async def count_pending_item_references(
        self,
        novel_id: str,
        location_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """统计尚未发布但正在引用地点的物品写入。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            当前地点关联的内部待发布物品数量。
        """
        return await BaseRepository("items").count_documents(
            {
                "novel_id": to_object_id(novel_id),
                "current_location_id": location_id,
                "item_write_pending_token": {"$type": "string"},
            },
            session=session,
        )


location_repo = LocationRepository()


__all__ = ["LocationRepository", "location_repo"]
