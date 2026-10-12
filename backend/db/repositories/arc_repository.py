"""篇章集合的读取。"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError
from backend.db.utils import to_object_id


class ArcRepository(BaseRepository):
    """只负责篇章存取，跨集合写入由 ArcService 完成。"""

    def __init__(self) -> None:
        """绑定 arcs 集合。"""
        super().__init__("arcs")

    async def get_arc(self, arc_id: str, *, include_deleted: bool = False, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """按稳定 ID 读取活动篇章或回收站篇章。

        Args:
            arc_id: 篇章 ObjectId 字符串。
            include_deleted: 是否允许读取回收站。
            session: 可选事务会话。

        Returns:
            完整篇章，不存在时抛出 404 错误。
        """
        document = await self.find_one({"_id": to_object_id(arc_id)}, include_deleted=include_deleted, session=session)
        if document is None:
            raise NotFoundError("篇章不存在或已删除")
        return document

    async def list_arcs(self, volume_id: str, *, deleted: bool = False, session: AsyncClientSession | None = None) -> list[dict[str, Any]]:
        """按顺序读取卷下活动篇章或回收站。

        Args:
            volume_id: 所属卷 ObjectId 字符串。
            deleted: 是否只读取回收站。
            session: 可选事务会话。

        Returns:
            顺序相同时按稳定 ID 排列的篇章列表。
        """
        return await self.collection.find(
            {"volume_id": to_object_id(volume_id), "is_deleted": deleted},
            {"creation_idempotency_key_hash": 0, "creation_request_hash": 0},
            session=session,
        ).sort([("order_index", ASCENDING), ("_id", ASCENDING)]).to_list(length=None)


arc_repo = ArcRepository()
