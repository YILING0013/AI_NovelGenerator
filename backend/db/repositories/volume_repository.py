"""卷正式聚合的 MongoDB 仓储。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import ensure_initial_version


class VolumeRepository(BaseRepository):
    """只提供卷持久化原语，跨集合业务由 VolumeService 编排。"""

    def __init__(self) -> None:
        """初始化 volumes 集合仓储。"""
        super().__init__("volumes")

    async def get_next_order_index(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """读取小说活动卷末尾的下一个 1-based 序号。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            当前最大活动序号加一；无活动卷时返回 1。
        """
        document = await self.collection.find_one(
            {"novel_id": to_object_id(novel_id), "is_deleted": False},
            projection={"order_index": 1},
            sort=[("order_index", -1)],
            session=session,
        )
        return 1 if document is None else int(document["order_index"]) + 1

    async def create_volume(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """插入已完成业务校验的新卷并固定初始版本。

        Args:
            data: 已过滤为卷正式字段的文档。
            session: 可选 MongoDB 会话。

        Returns:
            写入审计字段后的完整卷文档。
        """
        prepared = ensure_initial_version(data)
        prepared.setdefault("_id", ObjectId())
        prepared["novel_id"] = to_object_id(str(prepared["novel_id"]))
        prepared.setdefault("subtitle", "")
        prepared.setdefault("summary", "")
        prepared.setdefault("goal", "")
        prepared.setdefault("theme", "")
        prepared.setdefault("planning", None)
        prepared.setdefault("plot", "")
        prepared.setdefault("plot_source_fingerprint", None)
        prepared.setdefault("location_ids", [])
        prepared.setdefault("preparation", {})
        prepared.setdefault("status", "draft")
        prepared.setdefault("arcs_count", 0)
        prepared.setdefault("chapter_count", 0)
        prepared.setdefault("word_count", 0)
        prepared = self._prepare_audit_fields_for_insert(prepared)
        prepared["created_at"] = prepared["created_at"].replace(
            tzinfo=None,
            microsecond=(prepared["created_at"].microsecond // 1000) * 1000
        )
        prepared["updated_at"] = prepared["updated_at"].replace(
            tzinfo=None,
            microsecond=(prepared["updated_at"].microsecond // 1000) * 1000
        )
        try:
            result = await self.collection.insert_one(prepared, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("同一小说下的活动卷序号发生冲突") from exc
        return {**prepared, "_id": result.inserted_id}

    async def get_volumes_by_novel(
        self,
        novel_id: str,
        *,
        deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按 1-based 序号读取小说活动卷或回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。
            deleted: True 时读取回收站，否则读取活动卷。
            session: 可选 MongoDB 会话。

        Returns:
            稳定排序的卷文档列表。
        """
        query = {"novel_id": to_object_id(novel_id), "is_deleted": deleted}
        return await self.find_many(
            query,
            include_deleted=deleted,
            sort=(
                [("deleted_at", -1), ("_id", -1)]
                if deleted
                else [("order_index", 1), ("_id", 1)]
            ),
            session=session,
        )

    async def get_volume_by_id(
        self,
        volume_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按 ObjectId 读取卷，不存在或生命周期不匹配时返回 404。

        Args:
            volume_id: 卷 ObjectId 字符串。
            include_deleted: 是否允许读取回收站卷。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的完整卷文档。
        """
        document = await self.find_one(
            {"_id": to_object_id(volume_id)},
            include_deleted=include_deleted,
            session=session,
        )
        if document is None:
            raise NotFoundError(f"卷 {volume_id} 不存在")
        return document

    async def update_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
        fields: Mapping[str, Any],
        *,
        increment_version: bool,
        write_time: datetime | None = None,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """以卷前镜像的版本、生命周期和序号执行精确 CAS 更新。

        Args:
            snapshot: 写入前读取的完整卷文档。
            fields: 已经服务层校验的业务字段。
            increment_version: 成功时是否递增唯一公开版本。
            write_time: 可选预分配更新时间，供 standalone 未知确认精确核对。
            session: 可选 MongoDB 会话。

        Returns:
            写后文档；并发变化导致条件未命中时返回 None。
        """
        query = {
            "_id": snapshot["_id"],
            "version": int(snapshot["version"]),
            "is_deleted": bool(snapshot.get("is_deleted", False)),
            "order_index": int(snapshot["order_index"]),
            "updated_at": snapshot["updated_at"],
        }
        update: dict[str, Any] = {
            "$set": {**dict(fields), "updated_at": write_time or get_utc_now()}
        }
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
            raise DuplicateKeyError("同一小说下的活动卷序号发生冲突") from exc

    async def restore_snapshot(
        self,
        current: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """standalone 补偿时只把当前命令刚写过的卷恢复为前镜像。

        Args:
            current: 当前命令最近一次成功写后的文档。
            snapshot: 对应写入前镜像。
            session: 可选 MongoDB 会话。

        Returns:
            精确恢复成功时返回 True。
        """
        result = await self.collection.replace_one(
            {
                "_id": current["_id"],
                "version": int(current["version"]),
                "is_deleted": bool(current.get("is_deleted", False)),
                "order_index": int(current["order_index"]),
                "updated_at": current["updated_at"],
            },
            dict(snapshot),
            session=session,
        )
        return result.modified_count == 1

    async def hard_delete_created_batch(
        self,
        document_ids: Sequence[Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """按当前命令实际插入的 ObjectId 精确补偿新建卷。

        Args:
            document_ids: 当前命令返回的 BSON ObjectId。
            session: 可选 MongoDB 会话。

        Returns:
            实际删除数量。
        """
        if not document_ids:
            return 0
        result = await self.collection.delete_many(
            {"_id": {"$in": list(document_ids)}, "version": 1},
            session=session,
        )
        return result.deleted_count

    async def hard_delete_volume(
        self,
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """仅按回收站前镜像的身份、版本和序号物理删除一卷。

        Args:
            snapshot: 已校验为回收站状态的完整卷文档。
            session: 可选 MongoDB 会话。

        Returns:
            精确删除一条时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": snapshot["_id"],
                "version": int(snapshot["version"]),
                "is_deleted": True,
                "order_index": int(snapshot["order_index"]),
                "updated_at": snapshot["updated_at"],
            },
            session=session,
        )
        return result.deleted_count == 1


volume_repo = VolumeRepository()


__all__ = ["VolumeRepository", "volume_repo"]
