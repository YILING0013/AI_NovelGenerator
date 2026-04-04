import logging
from typing import Any, Dict, List

from application.db.repositories.volume_repository import volume_repo
from application.db.repositories.novel_repository import novel_repo
from application.db.base import BaseRepository
from application.db.utils import to_object_id, get_utc_now

logger = logging.getLogger(__name__)


class VolumeService:
    """
    卷（Volume）服务层，编排跨集合的级联操作。
    纯集合内操作由 VolumeRepository 负责，跨集合联动由此处编排。
    """

    # ── 创建 ─────────────────────────────────────────────────

    @staticmethod
    async def create_volume(data: Dict[str, Any]) -> str:
        """
        创建新卷：
        1. 校验 novel_id 指向的小说存在
        2. 调用 repository 插入卷文档
        3. 向上联动：novels.current_volume_count + 1
        """
        novel_id = data.get("novel_id")
        if not novel_id:
            raise ValueError("novel_id is required")

        # 前置校验：小说必须存在
        await novel_repo.get_novel_by_id(novel_id)  # 不存在会抛 NotFoundError

        volume_id = await volume_repo.create_volume(data)

        # 联动更新小说统计
        await novel_repo.increment_novel_stats(novel_id, {"current_volume_count": 1})

        return volume_id

    # ── 查询（透传） ──────────────────────────────────────────

    @staticmethod
    async def get_volumes_by_novel(novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下所有卷列表。"""
        return await volume_repo.get_volumes_by_novel(novel_id)

    @staticmethod
    async def get_volume_by_id(volume_id: str) -> Dict[str, Any]:
        """获取单个卷详情。"""
        return await volume_repo.get_volume_by_id(volume_id)

    # ── 更新（透传） ──────────────────────────────────────────

    @staticmethod
    async def update_volume_info(volume_id: str, update_data: Dict[str, Any]) -> bool:
        """更新卷基础信息。"""
        return await volume_repo.update_volume_info(volume_id, update_data)

    @staticmethod
    async def update_volume_stats(
        volume_id: str,
        arcs_count_delta: int = 0,
        word_count_delta: int = 0
    ) -> bool:
        """更新卷统计（由下级 arcs 增删时回调使用）。"""
        return await volume_repo.update_volume_stats(volume_id, arcs_count_delta, word_count_delta)

    # ── 软删除（级联） ────────────────────────────────────────

    @staticmethod
    async def soft_delete_volume(volume_id: str) -> bool:
        """
        软删除卷 + 级联：
        1. 获取卷信息（用于联动统计扣减）
        2. 软删除该卷自身
        3. 级联软删除该卷下所有 arcs
        4. 向上联动：novels.current_volume_count - 1，novels.current_word_count 扣减该卷字数
        """
        volume = await volume_repo.get_volume_by_id(volume_id)
        novel_id = str(volume["novel_id"])
        volume_word_count = volume.get("word_count", 0)

        # 1. 软删除自身
        success = await volume_repo.soft_delete_volume(volume_id)
        if not success:
            return False

        # 2. 级联软删除下属 arcs
        obj_id = to_object_id(volume_id)
        arcs_repo = BaseRepository("arcs")
        arcs_deleted = await arcs_repo.update_many(
            {"volume_id": obj_id},
            {"is_deleted": True, "deleted_at": get_utc_now()},
            include_deleted=False
        )
        logger.info(f"级联软删除卷 {volume_id} 下 {arcs_deleted} 个 arcs")

        # 3. 向上联动扣减小说统计
        stats_delta = {"current_volume_count": -1}
        if volume_word_count > 0:
            stats_delta["current_word_count"] = -volume_word_count
        await novel_repo.increment_novel_stats(novel_id, stats_delta)

        return True

    # ── 恢复（级联） ──────────────────────────────────────────

    @staticmethod
    async def restore_volume(volume_id: str) -> bool:
        """
        恢复已软删除的卷 + 级联：
        1. 恢复卷自身
        2. 级联恢复该卷下所有 arcs
        3. 向上联动：novels.current_volume_count + 1，回补字数
        """
        # 先获取已删除态的卷信息
        obj_id = to_object_id(volume_id)
        volume_repo_raw = volume_repo  # 复用同实例
        volume = await volume_repo_raw.find_one({"_id": obj_id}, include_deleted=True)
        if not volume or not volume.get("is_deleted", False):
            raise ValueError(f"Volume {volume_id} is not in deleted state")

        novel_id = str(volume["novel_id"])
        volume_word_count = volume.get("word_count", 0)

        # 1. 恢复自身
        success = await volume_repo.restore_volume(volume_id)
        if not success:
            return False

        # 2. 级联恢复下属 arcs
        arcs_repo = BaseRepository("arcs")
        arcs_restored = await arcs_repo.update_many(
            {"volume_id": obj_id, "is_deleted": True},
            {"is_deleted": False, "deleted_at": None},
            include_deleted=True
        )
        logger.info(f"级联恢复卷 {volume_id} 下 {arcs_restored} 个 arcs")

        # 3. 向上回补小说统计
        stats_delta = {"current_volume_count": 1}
        if volume_word_count > 0:
            stats_delta["current_word_count"] = volume_word_count
        await novel_repo.increment_novel_stats(novel_id, stats_delta)

        return True

    # ── 硬删除（级联） ────────────────────────────────────────

    @staticmethod
    async def hard_delete_volume(volume_id: str) -> Dict[str, Any]:
        """
        物理删除卷 + 级联：
        1. 校验该卷已处于软删除状态
        2. 级联物理删除所有关联 arcs
        3. 物理删除卷自身
        4. 返回删除统计
        """
        obj_id = to_object_id(volume_id)

        # 校验：仅允许删除已软删除的卷
        volume = await volume_repo.find_one({"_id": obj_id}, include_deleted=True)
        if not volume:
            raise ValueError(f"Volume {volume_id} not found")
        if not volume.get("is_deleted", False):
            raise ValueError("Only soft-deleted volumes can be permanently deleted")

        stats = {}

        # 1. 级联物理删除下属 arcs
        arcs_repo = BaseRepository("arcs")
        stats["arcs_deleted"] = await arcs_repo.hard_delete_many({"volume_id": obj_id})

        # 2. 物理删除卷自身
        volume_deleted = await volume_repo.hard_delete_volume(volume_id)
        stats["volume_deleted"] = 1 if volume_deleted else 0

        logger.info(f"硬删除卷 {volume_id} 完成: {stats}")
        return stats
