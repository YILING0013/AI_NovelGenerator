"""章节详情与不含正文的目录读取。"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError
from backend.db.utils import to_object_id


class ChapterRepository(BaseRepository):
    """章节持久化读取，跨集合保存由章节服务负责。"""

    def __init__(self) -> None:
        """绑定 chapters 集合。"""
        super().__init__("chapters")

    async def get_chapter(self, chapter_id: str, *, include_deleted: bool = False, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """读取一章的完整章计划和正文。

        Args:
            chapter_id: 章节 ID。
            include_deleted: 是否允许回收站。
            session: 可选事务。
        Returns:
            章节完整文档。
        """
        chapter = await self.find_one({"_id": to_object_id(chapter_id)}, include_deleted=include_deleted, session=session)
        if chapter is None:
            raise NotFoundError("章节不存在或已回收")
        return chapter

    async def list_in_scene(self, scene_id: str, *, deleted: bool = False, session: AsyncClientSession | None = None) -> list[dict[str, Any]]:
        """只读取当前场景的章节目录，不加载正文。

        Args:
            scene_id: 父场景 ID。
            deleted: 是否读取回收站。
            session: 可选事务。
        Returns:
            按场景内顺序排列的目录。
        """
        return await self.collection.find(
            {"scene_id": to_object_id(scene_id), "is_deleted": deleted},
            {"content": 0, "creation_idempotency_key_hash": 0, "creation_request_hash": 0}, session=session,
        ).sort([("order_index", 1), ("_id", 1)]).to_list(length=None)


chapter_repo = ChapterRepository()
