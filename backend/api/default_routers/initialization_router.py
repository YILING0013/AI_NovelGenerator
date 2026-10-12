"""全书初始化就绪状态只读 API。"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.contracts import ObjectIdString
from backend.services.novel.initialization_readiness_service import (
    InitializationReadinessResponseV1,
    InitializationReadinessService,
)


router = APIRouter(prefix="/api/novels", tags=["initialization"])


@router.get(
    "/{novel_id}/initialization-readiness",
    response_model=InitializationReadinessResponseV1,
)
async def get_initialization_readiness(
    novel_id: ObjectIdString,
) -> InitializationReadinessResponseV1:
    """返回从阶段 1 正式事实实时计算的初始化门禁。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        七个固定步骤及下一阶段是否解锁。
    """
    return await InitializationReadinessService.get_readiness(novel_id)


__all__ = ["router"]
