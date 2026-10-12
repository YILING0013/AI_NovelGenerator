"""小说正式聚合的 MongoDB 仓储。"""

from __future__ import annotations

from typing import Any, Mapping

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import ensure_initial_version, update_versioned_document


class NovelRepository(BaseRepository):
    """只提供小说持久化原语，业务写入由 NovelService 统一编排。"""

    def __init__(self) -> None:
        """初始化 novels 集合仓储。"""
        super().__init__("novels")

    async def create_novel(
        self,
        data: Mapping[str, Any],
        session: AsyncClientSession | None = None,
    ) -> str:
        """插入已完成业务校验的新小说并固定初始版本。

        Args:
            data: 已过滤为小说白名单字段的正式文档。
            session: 可选 MongoDB 会话。

        Returns:
            新小说的 ObjectId 字符串。
        """
        prepared = ensure_initial_version(data)
        if not str(prepared.get("title") or "").strip():
            raise ValueError("小说标题不能为空")
        prepared.setdefault("genre", "unclassified")
        prepared.setdefault("tags", [])
        prepared.setdefault("status", "draft")
        prepared.setdefault("current_volume_count", 0)
        prepared.setdefault("current_chapter_count", 0)
        prepared.setdefault("current_word_count", 0)
        try:
            return await self.insert_one(prepared, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("小说创建幂等键已被并发请求占用") from exc

    async def find_by_creation_idempotency(
        self,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按幂等键哈希读取首次小说创建结果。

        Args:
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            同键创建的小说文档；尚未使用时返回 None。
        """
        return await self.find_one(
            {"creation_idempotency_key_hash": key_hash},
            include_deleted=True,
            session=session,
        )

    async def get_all_novels(
        self,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取全部活动小说并按最后修改时间倒序排列。

        Args:
            session: 可选 MongoDB 会话。

        Returns:
            活动小说 BSON 文档列表。
        """
        return await self.find_many(
            {},
            sort=[("updated_at", -1), ("_id", -1)],
            session=session,
        )

    async def get_deleted_novels(
        self,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取全部回收站小说并按删除时间倒序排列。

        Args:
            session: 可选 MongoDB 会话。

        Returns:
            回收站小说 BSON 文档列表。
        """
        return await self.find_many(
            {"is_deleted": True},
            include_deleted=True,
            sort=[("deleted_at", -1), ("_id", -1)],
            session=session,
        )

    async def get_novel_by_id(
        self,
        novel_id: str,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按 ObjectId 读取小说，不存在或生命周期不匹配时抛出 404 领域异常。

        Args:
            novel_id: 小说 ObjectId 字符串。
            include_deleted: 是否允许读取回收站小说。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的小说 BSON 文档。
        """
        novel = await self.find_one(
            {"_id": to_object_id(novel_id)},
            include_deleted=include_deleted,
            session=session,
        )
        if novel is None:
            raise NotFoundError(f"小说 {novel_id} 不存在")
        return novel

    async def update_versioned_novel(
        self,
        novel_id: str,
        expected_version: int,
        update_fields: Mapping[str, Any],
        *,
        is_deleted: bool,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """执行一次小说 CAS 更新并返回写后文档。

        Args:
            novel_id: 小说 ObjectId 字符串。
            expected_version: 调用方读取到的版本。
            update_fields: 服务层完成白名单校验的业务字段。
            is_deleted: 当前操作要求的软删除状态。
            session: 可选 MongoDB 会话。

        Returns:
            CAS 成功后的小说；版本、状态或删除占用冲突时返回 None。
        """
        return await update_versioned_document(
            self.collection,
            {
                "_id": to_object_id(novel_id),
                # 读取后的间隙可能已取得永久删除占用，实际更新也要拒绝。
                "hard_delete_claim": {"$exists": False},
                "location_write_lock_token": None,
                "item_write_lock_token": None,
                "state_write_lock_token": None,
            },
            expected_version,
            update_fields,
            is_deleted=is_deleted,
            session=session,
        )

    async def acquire_location_write_lock(
        self,
        novel_id: str,
        command_token: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """为一个地点写命令取得小说级内部互斥。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            command_token: 当前地点命令的唯一内部标记。
            session: 可选 MongoDB 会话。

        Returns:
            取得互斥后的活动小说；小说不可用或已有地点命令时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "_id": to_object_id(novel_id),
                "is_deleted": False,
                "hard_delete_claim": {"$exists": False},
                "location_write_lock_token": None,
            },
            {
                "$inc": {"location_write_lock_revision": 1},
                "$set": {"location_write_lock_token": command_token},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def release_location_write_lock(
        self,
        novel_id: str,
        command_token: str,
        expected_revision: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """只释放仍由指定地点命令持有的小说级内部互斥。

        Args:
            novel_id: 小说 ObjectId 字符串。
            command_token: 当前地点命令的唯一内部标记。
            expected_revision: 取得互斥时返回的单调修订号。
            session: 可选 MongoDB 会话。

        Returns:
            精确清空当前命令标记时返回 True。
        """
        result = await self.collection.update_one(
            {
                "_id": to_object_id(novel_id),
                "location_write_lock_token": command_token,
                "location_write_lock_revision": expected_revision,
            },
            {"$set": {"location_write_lock_token": None}},
            session=session,
        )
        return result.matched_count == 1

    async def acquire_item_write_lock(
        self,
        novel_id: str,
        command_token: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """为一个物品写命令取得小说级内部互斥。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            command_token: 当前物品命令的唯一内部标记。
            session: 可选 MongoDB 会话。

        Returns:
            取得互斥后的活动小说；小说不可用或已有物品命令时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "_id": to_object_id(novel_id),
                "is_deleted": False,
                "hard_delete_claim": {"$exists": False},
                "item_write_lock_token": None,
            },
            {
                "$inc": {"item_write_lock_revision": 1},
                "$set": {"item_write_lock_token": command_token},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def release_item_write_lock(
        self,
        novel_id: str,
        command_token: str,
        expected_revision: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """只释放仍由指定物品命令持有的小说级内部互斥。

        Args:
            novel_id: 小说 ObjectId 字符串。
            command_token: 当前物品命令的唯一内部标记。
            expected_revision: 取得互斥时返回的单调修订号。
            session: 可选 MongoDB 会话。

        Returns:
            精确清空当前命令标记时返回 True。
        """
        result = await self.collection.update_one(
            {
                "_id": to_object_id(novel_id),
                "item_write_lock_token": command_token,
                "item_write_lock_revision": expected_revision,
            },
            {"$set": {"item_write_lock_token": None}},
            session=session,
        )
        return result.matched_count == 1

    async def acquire_state_write_lock(
        self,
        novel_id: str,
        command_token: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """为角色卷状态及其来源生命周期命令取得小说级互斥。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            command_token: 当前状态命令的唯一内部标记。
            session: 可选 MongoDB 会话。

        Returns:
            取得互斥后的活动小说；小说不可用或已有状态命令时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "_id": to_object_id(novel_id),
                "is_deleted": False,
                "hard_delete_claim": {"$exists": False},
                "state_write_lock_token": None,
            },
            {
                "$inc": {"state_write_lock_revision": 1},
                "$set": {"state_write_lock_token": command_token},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def release_state_write_lock(
        self,
        novel_id: str,
        command_token: str,
        expected_revision: int,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """只释放仍由指定角色卷状态命令持有的小说级互斥。

        Args:
            novel_id: 小说 ObjectId 字符串。
            command_token: 当前状态命令的唯一内部标记。
            expected_revision: 取得互斥时返回的单调修订号。
            session: 可选 MongoDB 会话。

        Returns:
            精确清空当前命令标记时返回 True。
        """
        result = await self.collection.update_one(
            {
                "_id": to_object_id(novel_id),
                "state_write_lock_token": command_token,
                "state_write_lock_revision": expected_revision,
            },
            {"$set": {"state_write_lock_token": None}},
            session=session,
        )
        return result.matched_count == 1

    async def claim_hard_delete(
        self,
        novel_id: str,
        expected_version: int,
        claim_token: str,
        *,
        session: AsyncClientSession | None = None,
        expected_revision_count: int | None = None,
        expected_writing_guard_revision: int | None = None,
    ) -> dict[str, Any] | None:
        """在删除消费者前以 CAS 声明一个可重入的物理删除操作。

        Args:
            novel_id: 回收站小说 ObjectId 字符串。
            expected_version: 调用方确认的回收站版本。
            claim_token: 由小说 ID 与版本确定性生成的内部声明值。
            session: 可选 MongoDB 会话。
            expected_revision_count: 首次明确批准的历史数量，同一删除重入时不能改。
            expected_writing_guard_revision: 本次读到的来源保护计数；None 表示字段尚不存在。

        Returns:
            成功声明或命中同一声明的小说预镜像；发生并发变更时返回 None。
        """
        return await self.collection.find_one_and_update(
            {
                "_id": to_object_id(novel_id),
                "version": expected_version,
                "is_deleted": True,
                "writing_guard_revision": (expected_writing_guard_revision if expected_writing_guard_revision is not None else {"$exists": False}),
                "location_write_lock_token": None,
                "item_write_lock_token": None,
                "state_write_lock_token": None,
                "$or": [
                    {"hard_delete_claim": {"$exists": False}},
                    {"hard_delete_claim": claim_token, **({"hard_delete_history_count": expected_revision_count} if expected_revision_count is not None else {})},
                ],
            },
            {"$set": {"hard_delete_claim": claim_token, **({"hard_delete_history_count": expected_revision_count} if expected_revision_count is not None else {})}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def delete_claimed_novel(
        self,
        novel_id: str,
        expected_version: int,
        claim_token: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """删除已由当前请求精确声明的小说文档。

        Args:
            novel_id: 小说 ObjectId 字符串。
            expected_version: 当前物理删除声明绑定的版本。
            claim_token: 当前物理删除声明值。
            session: 可选 MongoDB 会话。

        Returns:
            精确删除一个小说文档时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": to_object_id(novel_id),
                "version": expected_version,
                "is_deleted": True,
                "hard_delete_claim": claim_token,
            },
            session=session,
        )
        return result.deleted_count == 1

    async def count_cover_references(
        self,
        cover_url: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """统计活动与回收站小说对一个安全封面 URL 的全部引用。

        Args:
            cover_url: 内容哈希命名的封面静态 URL。
            session: 可选 MongoDB 会话。

        Returns:
            全生命周期小说文档的引用数量。
        """
        return await self.collection.count_documents(
            {"cover_image": cover_url},
            session=session,
        )

    async def update_novel_stats(
        self,
        novel_id: str,
        stats_data: Mapping[str, int],
        session: AsyncClientSession | None = None,
    ) -> bool:
        """由 NovelService 写入完整统计值并递增小说版本。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            stats_data: 统计字段的完整新值。
            session: 可选 MongoDB 会话。

        Returns:
            实际更新小说时返回 True。
        """
        allowed = {"current_volume_count", "current_chapter_count", "current_word_count"}
        filtered = {key: int(value) for key, value in stats_data.items() if key in allowed}
        if not filtered:
            return False
        result = await self.collection.update_one(
            {"_id": to_object_id(novel_id), "is_deleted": False},
            {
                "$set": {**filtered, "updated_at": get_utc_now()},
                "$inc": {"version": 1},
            },
            session=session,
        )
        return result.modified_count == 1

    async def increment_novel_stats(
        self,
        novel_id: str,
        stats_deltas: Mapping[str, int],
        session: AsyncClientSession | None = None,
    ) -> bool:
        """由 NovelService 原子增减统计值并递增小说版本。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            stats_deltas: 统计字段的原子增量。
            session: 可选 MongoDB 会话。

        Returns:
            实际更新小说时返回 True。
        """
        allowed = {"current_volume_count", "current_chapter_count", "current_word_count"}
        increments = {
            key: int(value)
            for key, value in stats_deltas.items()
            if key in allowed and int(value) != 0
        }
        if not increments:
            return False
        result = await self.collection.update_one(
            {"_id": to_object_id(novel_id), "is_deleted": False},
            {
                "$inc": {**increments, "version": 1},
                "$set": {"updated_at": get_utc_now()},
            },
            session=session,
        )
        return result.modified_count == 1

    async def update_stats_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
        stats_deltas: Mapping[str, int],
        *,
        write_time: Any,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """以小说前镜像版本精确更新卷数/章数/字数并返回写后镜像。

        Args:
            snapshot: 当前写入单元开始时读取的完整活动小说。
            stats_deltas: 允许为空的统计增量；空增量只递增版本以锁定写入单元。
            write_time: 由 Service 预分配的 BSON 毫秒精度写入时间。
            session: 可选 MongoDB 会话。

        Returns:
            CAS 成功后的小说；并发变化或统计将变为负数时返回 None。
        """
        allowed = {
            "current_volume_count",
            "current_chapter_count",
            "current_word_count",
        }
        next_stats = {
            field: int(snapshot[field]) + int(stats_deltas.get(field, 0))
            for field in allowed
        }
        if any(value < 0 for value in next_stats.values()):
            return None
        return await self.collection.find_one_and_update(
            {
                "_id": snapshot["_id"],
                "version": int(snapshot["version"]),
                "is_deleted": False,
            },
            {
                "$set": {**next_stats, "updated_at": write_time},
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )

    async def restore_snapshot_exact(
        self,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """standalone 补偿时只恢复当前命令刚写出的小说镜像。

        Args:
            before: 当前命令写入前的完整小说。
            after: 当前命令写入成功后的完整小说。
            session: 可选 MongoDB 会话。

        Returns:
            精确恢复成功时返回 True。
        """
        result = await self.collection.update_one(
            {
                "_id": after["_id"],
                "version": int(after["version"]),
                "is_deleted": bool(after.get("is_deleted", False)),
                "current_volume_count": int(after["current_volume_count"]),
                "current_chapter_count": int(after["current_chapter_count"]),
                "current_word_count": int(after["current_word_count"]),
                "updated_at": after["updated_at"],
            },
            {
                "$set": {
                    "version": int(before["version"]),
                    "current_volume_count": int(
                        before["current_volume_count"]
                    ),
                    "current_chapter_count": int(
                        before["current_chapter_count"]
                    ),
                    "current_word_count": int(before["current_word_count"]),
                    "updated_at": before["updated_at"],
                }
            },
            session=session,
        )
        return result.modified_count == 1


novel_repo = NovelRepository()


__all__ = ["NovelRepository", "novel_repo"]
