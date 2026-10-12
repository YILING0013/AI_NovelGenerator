"""角色卷级参与状态 MongoDB 仓储。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError, DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import ensure_initial_version


class CharacterVolumeStateRepository(BaseRepository):
    """封装小说作用域内角色卷状态的直接持久化原语。"""

    def __init__(self) -> None:
        """绑定角色卷状态集合。

        Args:
            无。

        Returns:
            无。
        """
        super().__init__("character_volume_states")

    async def create_state(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """插入一条已完成领域校验的角色卷状态。

        Args:
            data: 含小说、卷、角色、业务内容和幂等摘要的正式文档。
            session: 可选 MongoDB 会话。

        Returns:
            含 ObjectId、版本和审计字段的完整写后文档。
        """
        document = ensure_initial_version(data)
        state_id = document.get("state_id") or document.get("_id") or ObjectId()
        state_id = to_object_id(state_id)
        now = document.get("created_at") or get_utc_now()
        document.update(
            {
                "_id": state_id,
                "state_id": state_id,
                "novel_id": to_object_id(document["novel_id"]),
                "volume_id": to_object_id(document["volume_id"]),
                "source_state_id": (
                    to_object_id(document["source_state_id"])
                    if document.get("source_state_id") is not None
                    else None
                ),
                "version": 1,
                "dependency_guard_revision": 0,
                "is_deleted": False,
                "deleted_at": None,
                "deletion_sources": [],
                "created_at": now,
                "updated_at": document.get("updated_at") or now,
            }
        )
        try:
            await self.collection.insert_one(document, session=session)
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError(
                "同一角色同一卷已有活动状态，或幂等键发生冲突"
            ) from exc
        return document

    async def create_states(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按顺序批量插入已完整预检的角色卷状态。

        Args:
            documents: 已预分配状态 ObjectId 的正式文档序列。
            session: 可选 MongoDB 会话。

        Returns:
            与输入顺序一致的完整写后文档。
        """
        prepared: list[dict[str, Any]] = []
        for raw in documents:
            document = ensure_initial_version(raw)
            state_id = to_object_id(document.get("state_id") or document.get("_id") or ObjectId())
            now = document.get("created_at") or get_utc_now()
            document.update(
                {
                    "_id": state_id,
                    "state_id": state_id,
                    "novel_id": to_object_id(document["novel_id"]),
                    "volume_id": to_object_id(document["volume_id"]),
                    "source_state_id": (
                        to_object_id(document["source_state_id"])
                        if document.get("source_state_id") is not None
                        else None
                    ),
                    "version": 1,
                    "dependency_guard_revision": 0,
                    "is_deleted": False,
                    "deleted_at": None,
                    "deletion_sources": [],
                    "created_at": now,
                    "updated_at": document.get("updated_at") or now,
                }
            )
            prepared.append(document)
        if not prepared:
            return []
        try:
            await self.collection.insert_many(prepared, ordered=True, session=session)
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError(
                "初始化目标已有角色卷状态，或幂等键发生冲突"
            ) from exc
        return prepared

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与创建幂等键摘要读取首次写入结果。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始幂等键的 SHA-256 摘要。
            session: 可选 MongoDB 会话。

        Returns:
            命中的完整状态；尚未使用该键时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "creation_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            session=session,
        )

    async def get_state(
        self,
        novel_id: str,
        state_id: str | ObjectId,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按小说作用域和状态 ObjectId 读取一条记录。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 或可转换字符串。
            include_deleted: 是否允许返回带删除来源的记录。
            session: 可选 MongoDB 会话。

        Returns:
            匹配生命周期条件的完整状态。
        """
        state = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "state_id": to_object_id(state_id),
            },
            include_deleted=include_deleted,
            session=session,
        )
        if state is None:
            raise NotFoundError(f"角色卷状态 {state_id} 不存在于小说 {novel_id}")
        return state

    async def find_active_by_pair(
        self,
        novel_id: str,
        volume_id: str | ObjectId,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取指定角色在指定卷中的唯一活动状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 卷 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            唯一活动状态；不存在时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "volume_id": to_object_id(volume_id),
                "character_id": character_id,
            },
            session=session,
        )

    async def find_any_by_pair(
        self,
        novel_id: str,
        volume_id: str | ObjectId,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取指定角色与卷组合的任一生命周期状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 卷 ObjectId 或可转换字符串。
            character_id: 稳定角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            任一历史记录；从未建立时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "volume_id": to_object_id(volume_id),
                "character_id": character_id,
            },
            include_deleted=True,
            session=session,
        )

    async def list_by_volume(
        self,
        novel_id: str,
        volume_id: str | ObjectId,
        *,
        scope: str | None = None,
        status: Literal["active", "deleted", "all"] = "active",
        q: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出一卷中的角色状态并应用公开筛选。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 卷 ObjectId 或可转换字符串。
            scope: 可选参与层级。
            status: active、deleted 或 all 生命周期视图。
            q: 可选目标与状态文本搜索词。
            session: 可选 MongoDB 会话。

        Returns:
            按参与层级、角色 ID 稳定排序的状态列表。
        """
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "volume_id": to_object_id(volume_id),
        }
        if status != "all":
            query["is_deleted"] = status == "deleted"
        if scope is not None:
            query["participation_scope"] = scope
        if q is not None:
            pattern = re.escape(q)
            query["$or"] = [
                {field: {"$regex": pattern, "$options": "i"}}
                for field in (
                    "character_id",
                    "current_goal",
                    "start_state",
                    "planned_end_state",
                    "psychological_state",
                    "public_state",
                    "hidden_state",
                )
            ]
        return await self.find_many(
            query,
            include_deleted=status in {"deleted", "all"},
            sort=[("character_id", 1), ("state_id", 1)],
            session=session,
        )

    async def list_by_character(
        self,
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取角色跨卷的完整历史，包括带删除来源的记录。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按创建时间和状态 ObjectId 稳定排序的历史列表。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
            },
            include_deleted=True,
            sort=[("created_at", 1), ("state_id", 1)],
            session=session,
        )

    async def list_for_character_source(
        self,
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取角色删除来源需要覆盖的全部状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 作为删除来源的角色业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            按状态 ObjectId 稳定排序的活动与回收站记录。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "character_id": character_id,
            },
            include_deleted=True,
            sort=[("state_id", 1)],
            session=session,
        )

    async def list_for_volume_source(
        self,
        novel_id: str,
        volume_id: str | ObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取卷删除来源需要覆盖的全部状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 作为删除来源的卷 ObjectId。
            session: 可选 MongoDB 会话。

        Returns:
            按状态 ObjectId 稳定排序的活动与回收站记录。
        """
        return await self.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "volume_id": to_object_id(volume_id),
            },
            include_deleted=True,
            sort=[("state_id", 1)],
            session=session,
        )

    async def update_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
        fields: Mapping[str, Any],
        *,
        increment_version: bool,
        write_time: datetime,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按完整状态前镜像执行精确 CAS 更新。

        Args:
            snapshot: 当前命令读取的完整状态预镜像。
            fields: 已完成领域校验的目标字段。
            increment_version: 是否把公开版本递增一次。
            write_time: 当前命令预分配的 MongoDB 毫秒时间。
            session: 可选 MongoDB 会话。

        Returns:
            写后状态；前镜像已变化时返回 None。
        """
        query = {
            "_id": snapshot["_id"],
            "state_id": snapshot["state_id"],
            "novel_id": snapshot["novel_id"],
            "volume_id": snapshot["volume_id"],
            "character_id": snapshot["character_id"],
            "version": int(snapshot["version"]),
            "dependency_guard_revision": int(
                snapshot["dependency_guard_revision"]
            ),
            "is_deleted": bool(snapshot["is_deleted"]),
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
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("角色卷状态唯一约束发生冲突") from exc

    async def restore_snapshot(
        self,
        current: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """standalone 补偿时从当前命令写后镜像精确恢复前镜像。

        Args:
            current: 当前命令写入成功后的完整状态。
            snapshot: 对应写入前镜像。
            session: 可选 MongoDB 会话。

        Returns:
            精确恢复一条时返回 True。
        """
        result = await self.collection.replace_one(
            {
                "_id": current["_id"],
                "version": int(current["version"]),
                "dependency_guard_revision": int(
                    current["dependency_guard_revision"]
                ),
                "is_deleted": bool(current["is_deleted"]),
                "updated_at": current["updated_at"],
            },
            dict(snapshot),
            session=session,
        )
        return result.modified_count == 1

    async def delete_created_states_exact(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """精确删除当前命令新建且尚未被后续修改的状态。

        Args:
            documents: 当前命令插入时保存的完整状态序列。
            session: 可选 MongoDB 会话。

        Returns:
            实际精确删除的状态数量。
        """
        deleted = 0
        for document in documents:
            result = await self.collection.delete_one(
                {
                    "_id": document["_id"],
                    "state_id": document["state_id"],
                    "version": 1,
                    "dependency_guard_revision": 0,
                    "is_deleted": False,
                    "updated_at": document["updated_at"],
                },
                session=session,
            )
            deleted += int(result.deleted_count)
        return deleted

    async def hard_delete_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """按回收站状态完整前镜像物理删除一条状态。

        Args:
            snapshot: 已校验版本和回收站状态的完整文档。
            session: 可选 MongoDB 会话。

        Returns:
            精确删除一条时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": snapshot["_id"],
                "state_id": snapshot["state_id"],
                "novel_id": snapshot["novel_id"],
                "version": int(snapshot["version"]),
                "dependency_guard_revision": int(
                    snapshot["dependency_guard_revision"]
                ),
                "is_deleted": True,
                "updated_at": snapshot["updated_at"],
            },
            session=session,
        )
        return result.deleted_count == 1


class CharacterVolumeStateInitializationReceiptRepository(BaseRepository):
    """保存从上一卷初始化命令的不可变成功回执。"""

    def __init__(self) -> None:
        """绑定角色卷状态初始化回执集合。

        Args:
            无。

        Returns:
            无。
        """
        super().__init__("character_volume_state_initialization_receipts")

    async def find_receipt(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与初始化幂等键读取不可变成功回执。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256 摘要。
            session: 可选 MongoDB 会话。

        Returns:
            已发布的成功回执；尚未发布时返回 None。
        """
        return await self.collection.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "idempotency_key_hash": key_hash,
            },
            session=session,
        )

    async def create_receipt(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """发布一条不可变初始化成功回执。

        Args:
            data: 含请求摘要、源目标卷和结果快照的回执字段。
            session: 可选 MongoDB 会话。

        Returns:
            含 MongoDB ObjectId 与创建时间的回执。
        """
        document = {
            **dict(data),
            "_id": data.get("_id") or ObjectId(),
            "novel_id": to_object_id(data["novel_id"]),
            "source_volume_id": to_object_id(data["source_volume_id"]),
            "target_volume_id": to_object_id(data["target_volume_id"]),
            "created_at": data.get("created_at") or get_utc_now(),
        }
        try:
            await self.collection.insert_one(document, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("初始化幂等回执已被并发请求发布") from exc
        return document


character_volume_state_repo = CharacterVolumeStateRepository()
character_volume_state_initialization_receipt_repo = (
    CharacterVolumeStateInitializationReceiptRepository()
)


__all__ = [
    "CharacterVolumeStateInitializationReceiptRepository",
    "CharacterVolumeStateRepository",
    "character_volume_state_initialization_receipt_repo",
    "character_volume_state_repo",
]
