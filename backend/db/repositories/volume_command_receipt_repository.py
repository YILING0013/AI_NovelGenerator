"""卷创建与批量规划确认的不可变幂等收据仓储。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError
from backend.db.utils import to_object_id


class VolumeCommandReceiptRepository(BaseRepository):
    """保存成功命令的原始公开结果，不承载卷事实或候选。"""

    def __init__(self) -> None:
        """初始化 volume_command_receipts 集合仓储。"""
        super().__init__("volume_command_receipts")

    async def find_receipt(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与幂等键哈希读取成功命令收据。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            不可变成功收据；未使用该键时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            session=session,
        )

    async def create_receipt(
        self,
        document: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """插入一次已成功生成正式结果的不可变命令收据。

        Args:
            document: 请求摘要、命令类型和原始公开结果快照。
            session: 可选 MongoDB 会话。

        Returns:
            含 BSON ``_id`` 的收据文档。
        """
        prepared = dict(document)
        prepared["novel_id"] = to_object_id(str(prepared["novel_id"]))
        prepared = self._prepare_audit_fields_for_insert(prepared)
        try:
            result = await self.collection.insert_one(prepared, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("卷命令幂等键已被并发请求占用") from exc
        return {**prepared, "_id": result.inserted_id}

volume_command_receipt_repo = VolumeCommandReceiptRepository()


__all__ = ["VolumeCommandReceiptRepository", "volume_command_receipt_repo"]
