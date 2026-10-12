"""场景集合的读取。"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError
from backend.db.utils import to_object_id


class SceneRepository(BaseRepository):
    """场景存取；跨集合写入由场景服务负责。"""

    def __init__(self) -> None:
        """绑定 scenes 集合。"""
        super().__init__("scenes")

    async def get_scene(self, scene_id: str, *, include_deleted: bool = False, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """读取场景或回收站场景。

        Args:
            scene_id: 场景 ID。
            include_deleted: 是否包含回收站。
            session: 可选事务。
        Returns:
            完整场景，不存在时抛出 404。
        """
        scene = await self.find_one({"_id": to_object_id(scene_id)}, include_deleted=include_deleted, session=session)
        if scene is None:
            raise NotFoundError("场景不存在或已回收")
        return scene

    async def list_scenes(self, arc_id: str, *, deleted: bool = False, session: AsyncClientSession | None = None) -> list[dict[str, Any]]:
        """读取当前篇章的有序场景列表。

        Args:
            arc_id: 父篇章 ID。
            deleted: 是否读取回收站。
            session: 可选事务。
        Returns:
            不含内部创建键的场景列表。
        """
        return await self.collection.find(
            {"arc_id": to_object_id(arc_id), "is_deleted": deleted},
            {"creation_idempotency_key_hash": 0, "creation_request_hash": 0}, session=session,
        ).sort([("order_index", 1), ("_id", 1)]).to_list(length=None)


scene_repo = SceneRepository()
