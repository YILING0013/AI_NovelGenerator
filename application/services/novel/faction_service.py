import logging
from typing import Any, Dict, List

from application.db.repositories.faction_repository import faction_repo
from application.db.repositories.novel_repository import novel_repo

logger = logging.getLogger(__name__)


class FactionService:
    """
    阵营（Faction）服务层，编排跨集合的业务逻辑。
    纯集合内操作由 FactionRepository 负责，跨集合联动由此处编排。
    """

    # 创建 
    @staticmethod
    async def create_faction(data: Dict[str, Any]) -> str:
        """
        创建新阵营：
        1. 校验 novel_id 指向的小说存在
        2. 若未传入 faction_id，自动生成
        3. 调用 repository 插入阵营文档
        """
        novel_id = data.get("novel_id")
        if not novel_id:
            raise ValueError("novel_id is required")

        # 前置校验：小说必须存在
        await novel_repo.get_novel_by_id(novel_id)  # 不存在会抛 NotFoundError

        # 自动生成 faction_id
        if not data.get("faction_id"):
            data["faction_id"] = await faction_repo._get_next_faction_id(novel_id)

        return await faction_repo.create_faction(data)

    # 查询（透传） 
    @staticmethod
    async def get_factions_by_novel(novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下所有阵营列表。"""
        return await faction_repo.get_factions_by_novel(novel_id)

    @staticmethod
    async def get_faction_by_id(faction_id: str) -> Dict[str, Any]:
        """获取单个阵营详情（按业务 faction_id）。"""
        return await faction_repo.get_faction_by_id(faction_id)

    @staticmethod
    async def get_factions_by_level_type(novel_id: str, level_type: str) -> List[Dict[str, Any]]:
        """获取指定小说下特定层级类型的阵营列表。"""
        return await faction_repo.get_factions_by_level_type(novel_id, level_type)

    @staticmethod
    async def get_child_factions(novel_id: str, parent_faction_id: str) -> List[Dict[str, Any]]:
        """获取指定父级阵营的所有直接子阵营。"""
        return await faction_repo.get_child_factions(novel_id, parent_faction_id)

    # 更新（透传） 
    @staticmethod
    async def update_faction_info(faction_id: str, update_data: Dict[str, Any]) -> bool:
        """更新阵营基础信息。"""
        return await faction_repo.update_faction_info(faction_id, update_data)

    @staticmethod
    async def batch_update_sort_order(novel_id: str, sort_map: Dict[str, int]) -> int:
        """批量更新阵营排序权重。"""
        return await faction_repo.batch_update_sort_order(novel_id, sort_map)

    # 软删除（含子阵营处理） 
    @staticmethod
    async def soft_delete_faction(faction_id: str) -> bool:
        """
        软删除阵营：
        1. 获取阵营信息（验证存在）
        2. 软删除该阵营自身 + 解除子阵营挂靠
        """
        # 验证阵营存在
        await faction_repo.get_faction_by_id(faction_id)  # 不存在会抛 NotFoundError

        success = await faction_repo.soft_delete_faction(faction_id)
        if success:
            logger.info(f"软删除阵营 {faction_id} 完成")
        return success

    # 恢复 
    @staticmethod
    async def restore_faction(faction_id: str) -> bool:
        """
        恢复已软删除的阵营：
        1. 校验阵营存在且处于已删除状态
        2. 恢复阵营
        """
        faction = await faction_repo.find_one({"faction_id": faction_id}, include_deleted=True)
        if not faction:
            raise ValueError(f"Faction {faction_id} not found")
        if not faction.get("is_deleted", False):
            raise ValueError(f"Faction {faction_id} is not in deleted state")

        success = await faction_repo.restore_faction(faction_id)
        if success:
            logger.info(f"恢复阵营 {faction_id} 完成")
        return success

    # 硬删除 
    @staticmethod
    async def hard_delete_faction(faction_id: str) -> Dict[str, Any]:
        """
        物理删除阵营：
        1. 校验阵营存在且处于已软删除状态
        2. 解除子阵营挂靠 + 物理删除阵营文档
        3. 返回删除统计
        """
        # 获取子阵营数量（用于统计）
        faction = await faction_repo.find_one({"faction_id": faction_id}, include_deleted=True)
        if not faction:
            raise ValueError(f"Faction {faction_id} not found")
        if not faction.get("is_deleted", False):
            raise ValueError("Only soft-deleted factions can be permanently deleted")

        # 统计子阵营数量
        children = await faction_repo.find_many(
            {"parent_faction_id": faction_id},
            include_deleted=False
        )
        children_count = len(children)

        # hard_delete_faction 会处理子阵营解除挂靠和物理删除
        deleted = await faction_repo.hard_delete_faction(faction_id)

        stats = {
            "faction_deleted": 1 if deleted else 0,
            "children_unlinked": children_count,
        }
        logger.info(f"硬删除阵营 {faction_id} 完成: {stats}")
        return stats
