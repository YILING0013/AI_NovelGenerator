from typing import Any, Dict, List, Optional
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.base import BaseRepository
from backend.db.utils import to_object_id
from backend.db.errors import NotFoundError, InvalidIdError

class NovelRepository(BaseRepository):
    def __init__(self):
        """初始化小说仓储，指定集合为'novels'"""
        super().__init__("novels")

    async def create_novel(self, data: Dict[str, Any], session: AsyncClientSession | None = None) -> str:
        """创建一本小说，并初始化相关的默认字段和统计数据。

        Args:
            data: 前端提交的小说基础数据。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            新小说的 ObjectId 字符串。
        """
        if "title" not in data or not data["title"]:
            raise ValueError("Novel title cannot be empty")

        prepared = dict(data)
        prepared.setdefault("genre", "unclassified")
        if "tags" not in prepared or not isinstance(prepared["tags"], list):
            prepared["tags"] = []

        prepared.setdefault("status", "draft")
        
        # 新建小说时统计字段从 0 开始，后续由卷/章节服务联动增减。
        prepared.setdefault("current_volume_count", 0)
        prepared.setdefault("current_chapter_count", 0)
        prepared.setdefault("current_word_count", 0)
        
        return await self.insert_one(prepared, session=session)

    async def get_all_novels(self) -> List[Dict[str, Any]]:
        """获取所有未删除的小说的简要信息（列表视图）"""
        query = {}
        # 获取列表的部分信息
        cursor = self.collection.find(
            {"is_deleted": False},
            projection={"_id": 1, "title": 1, "subtitle": 1, 
                        "genre": 1, "status": 1, "tags": 1, 
                        "cover_image": 1, "current_chapter_count": 1, "current_word_count": 1
                    }
        )
        return await cursor.to_list(length=None)

    async def get_deleted_novels(self) -> List[Dict[str, Any]]:
        """获取所有已软删除的小说列表（回收站视图）"""
        cursor = self.collection.find(
            {"is_deleted": True},
            projection={"_id": 1, "title": 1, "subtitle": 1,
                        "genre": 1, "status": 1, "tags": 1,
                        "cover_image": 1, "current_chapter_count": 1, "current_word_count": 1,
                        "deleted_at": 1
                    }
        )
        return await cursor.to_list(length=None)

    async def get_novel_by_id(
        self,
        novel_id: str,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """根据ID获取小说的详细信息，如果不存在则抛出NotFoundError异常。

        Args:
            novel_id: 小说 ObjectId 字符串。
            include_deleted: 是否允许读取软删除小说。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            小说文档。
        """
        obj_id = to_object_id(novel_id)
        novel = await self.find_one({"_id": obj_id}, include_deleted=include_deleted, session=session)
        if not novel:
            raise NotFoundError(f"Novel with id {novel_id} not found")
        return novel

    async def update_novel_info(
        self,
        novel_id: str,
        update_data: Dict[str, Any],
        session: AsyncClientSession | None = None,
    ) -> bool:
        """更新小说的基本信息，自动过滤掉受保护的字段（如_id, created_at等）。

        Args:
            novel_id: 小说 ObjectId 字符串。
            update_data: 待更新字段。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际修改成功时返回 True。
        """
        # 防止更新只读/审计字段
        protected_fields = {"_id", "created_at", "updated_at", "is_deleted", "deleted_at"}
        filtered_data = {k: v for k, v in update_data.items() if k not in protected_fields}
        
        if not filtered_data:
            return False
            
        obj_id = to_object_id(novel_id)
        return await self.update_one({"_id": obj_id}, filtered_data, session=session)

    async def update_novel_status(
        self,
        novel_id: str,
        status: str,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """更新小说的状态（如草稿、连载中等），会校验状态的有效性。

        Args:
            novel_id: 小说 ObjectId 字符串。
            status: 新状态。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际修改成功时返回 True。
        """
        valid_statuses = {"draft", "ongoing", "completed", "archived"}
        if status not in valid_statuses:
            raise ValueError(f"状态无效: {status}")
            
        obj_id = to_object_id(novel_id)
        return await self.update_one({"_id": obj_id}, {"status": status}, session=session)

    async def update_novel_stats(
        self,
        novel_id: str,
        stats_data: Dict[str, int],
        session: AsyncClientSession | None = None,
    ) -> bool:
        """更新小说的统计数据（如当前卷数、章数、字数等）。

        Args:
            novel_id: 小说 ObjectId 字符串。
            stats_data: 统计字段完整值。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际修改成功时返回 True。
        """
        # 预期的键如current_volume_count、current_chapter_count、current_word_count
        obj_id = to_object_id(novel_id)
        return await self.update_one({"_id": obj_id}, stats_data, session=session)

    async def increment_novel_stats(
        self,
        novel_id: str,
        stats_deltas: Dict[str, int],
        session: AsyncClientSession | None = None,
    ) -> bool:
        """原子增减小说的统计数据（如current_volume_count +1/-1）。

        Args:
            novel_id: 小说 ObjectId 字符串。
            stats_deltas: 统计字段增量。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际修改成功时返回 True。
        """
        allowed_keys = {"current_volume_count", "current_chapter_count", "current_word_count"}
        filtered = {k: v for k, v in stats_deltas.items() if k in allowed_keys and v != 0}
        if not filtered:
            return False
        obj_id = to_object_id(novel_id)
        return await self.increment_one({"_id": obj_id}, filtered, session=session)

    async def soft_delete_novel(self, novel_id: str, session: AsyncClientSession | None = None) -> bool:
        """软删除指定ID的小说。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际软删除成功时返回 True。
        """
        obj_id = to_object_id(novel_id)
        return await self.soft_delete_one({"_id": obj_id}, session=session)

    async def restore_novel(self, novel_id: str, session: AsyncClientSession | None = None) -> bool:
        """恢复被软删除的指定ID的小说。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际恢复成功时返回 True。
        """
        obj_id = to_object_id(novel_id)
        return await self.restore_one({"_id": obj_id}, session=session)

novel_repo = NovelRepository()
