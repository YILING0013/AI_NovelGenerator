from typing import Tuple, Dict, Any
from application.db.repositories.novel_repository import novel_repo
from application.db.base import BaseRepository
from application.db.utils import to_object_id

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
        is_safe, msg = await NovelService.check_novel_before_delete(novel_id)
        if not is_safe:
            raise ValueError(f"Cannot hard delete novel: {msg}")

        obj_id = to_object_id(novel_id)
        query = {"novel_id": obj_id}
        
        volumes_repo = BaseRepository("volumes")
        chapters_repo = BaseRepository("chapters")
        outlines_repo = BaseRepository("outlines")
        tasks_repo = BaseRepository("generation_tasks")
        memories_repo = BaseRepository("memory_fragments")
        
        stats = {}
        
        stats["volumes_deleted"] = await volumes_repo.hard_delete_many(query)
        stats["chapters_deleted"] = await chapters_repo.hard_delete_many(query)
        stats["outlines_deleted"] = await outlines_repo.hard_delete_many(query)
        stats["tasks_deleted"] = await tasks_repo.hard_delete_many(query)
        stats["memories_deleted"] = await memories_repo.hard_delete_many(query)
        
        # 最后删除小说本身
        novel_deleted = await novel_repo.hard_delete_one({"_id": obj_id})
        stats["novel_deleted"] = 1 if novel_deleted else 0
        
        return stats
