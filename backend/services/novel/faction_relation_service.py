from typing import Any, Dict, List

from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo


class FactionRelationService:
    """
    阵营关系服务层，负责查询前校验小说和阵营作用域。
    """

    @staticmethod
    async def get_relations_by_novel(novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下当前有效的全部阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            阵营关系文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_relation_repo.get_relations_by_novel(novel_id)

    @staticmethod
    async def get_relations_by_faction(novel_id: str, faction_id: str) -> List[Dict[str, Any]]:
        """获取某个阵营参与的全部当前有效关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。

        Returns:
            阵营关系文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        # 先确认阵营属于当前小说，避免跨小说 faction_id 被误用。
        await faction_repo.get_faction(novel_id, faction_id)
        return await faction_relation_repo.get_relations_by_faction(novel_id, faction_id)
