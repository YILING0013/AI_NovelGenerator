from typing import Tuple, Dict, Any
from backend.db.repositories.novel_repository import novel_repo
from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import to_object_id

class NovelService:
    @staticmethod
    async def check_novel_before_delete(novel_id: str) -> Tuple[bool, str]:
        """
        检查小说是否可以安全进行物理删除。
        返回：(是否安全, 提示信息)
        """
        try:
            # 首先检查小说是否存在（包括已软删除的）
            novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True)
            
            # 只有当小说已软删除时才允许物理删除
            if not novel.get("is_deleted", False):
                return False, "Only soft-deleted novels can be permanently deleted"
            
            return True, "Safe to delete"
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def hard_delete_novel(novel_id: str) -> Dict[str, Any]:
        """
        物理删除小说及其所有关联记录。
        **仅允许用于整本小说永久删除**
        """
        async def _delete(session):
            """在同一个写入单元内删除小说及所有已知子集合。"""
            try:
                novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True, session=session)
            except NotFoundError as exc:
                raise ValueError(f"Cannot hard delete novel: {exc}") from exc

            if not novel.get("is_deleted", False):
                raise ValueError("Cannot hard delete novel: Only soft-deleted novels can be permanently deleted")

            obj_id = to_object_id(novel_id)
            query = {"novel_id": obj_id}

            volumes_repo = BaseRepository("volumes")
            chapters_repo = BaseRepository("chapters")
            outlines_repo = BaseRepository("outlines")
            tasks_repo = BaseRepository("generation_tasks")
            memories_repo = BaseRepository("memory_fragments")
            factions_repo = BaseRepository("factions")
            faction_relations_repo = BaseRepository("faction_relations")

            stats = {}

            # 这些集合当前有的还是空仓储，统一按 novel_id 清理即可。
            stats["volumes_deleted"] = await volumes_repo.hard_delete_many(query, session=session)
            stats["chapters_deleted"] = await chapters_repo.hard_delete_many(query, session=session)
            stats["outlines_deleted"] = await outlines_repo.hard_delete_many(query, session=session)
            stats["tasks_deleted"] = await tasks_repo.hard_delete_many(query, session=session)
            stats["memories_deleted"] = await memories_repo.hard_delete_many(query, session=session)
            stats["faction_relations_deleted"] = await faction_relations_repo.hard_delete_many(query, session=session)
            stats["factions_deleted"] = await factions_repo.hard_delete_many(query, session=session)

            novel_deleted = await novel_repo.hard_delete_one({"_id": obj_id}, session=session)
            stats["novel_deleted"] = 1 if novel_deleted else 0

            return stats

        return await run_mongo_write_unit(_delete, "hard_delete_novel")
