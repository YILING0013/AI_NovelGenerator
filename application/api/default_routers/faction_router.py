from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional

from application.services.novel.faction_service import FactionService
from application.db.errors import NotFoundError, InvalidIdError, DuplicateKeyError

router = APIRouter(prefix="/api/factions", tags=["factions"])


# 请求模型 

class CreateFactionRequest(BaseModel):
    novel_id: str
    name: str
    faction_id: Optional[str] = None
    alias: Optional[List[str]] = None
    faction_type: Optional[str] = None
    level_type: Optional[str] = None
    parent_faction_id: Optional[str] = None
    positioning: Optional[str] = None
    public_stance: Optional[str] = None
    core_goal: Optional[str] = None
    hidden_goal: Optional[str] = None
    resources_and_advantages: Optional[List[str]] = None
    organization_style: Optional[str] = None
    core_values: Optional[List[str]] = None
    conflict_with_mainline: Optional[str] = None
    is_public: Optional[bool] = None
    influence_scope: Optional[str] = None
    active_status: Optional[str] = None
    expandability: Optional[str] = None
    tags: Optional[List[str]] = None
    first_appearance_volume_id: Optional[str] = None
    first_appearance_chapter_id: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[Dict] = None


class UpdateFactionRequest(BaseModel):
    name: Optional[str] = None
    alias: Optional[List[str]] = None
    faction_type: Optional[str] = None
    level_type: Optional[str] = None
    parent_faction_id: Optional[str] = None
    positioning: Optional[str] = None
    public_stance: Optional[str] = None
    core_goal: Optional[str] = None
    hidden_goal: Optional[str] = None
    resources_and_advantages: Optional[List[str]] = None
    organization_style: Optional[str] = None
    core_values: Optional[List[str]] = None
    conflict_with_mainline: Optional[str] = None
    is_public: Optional[bool] = None
    influence_scope: Optional[str] = None
    active_status: Optional[str] = None
    expandability: Optional[str] = None
    tags: Optional[List[str]] = None
    first_appearance_volume_id: Optional[str] = None
    first_appearance_chapter_id: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[Dict] = None


class BatchUpdateSortOrderRequest(BaseModel):
    novel_id: str
    sort_map: Dict[str, int]


# 辅助函数 

def _serialize_faction(faction: dict) -> dict:
    """将阵营文档中的 ObjectId 转为字符串。"""
    if "_id" in faction:
        faction["_id"] = str(faction["_id"])
    if "novel_id" in faction:
        faction["novel_id"] = str(faction["novel_id"])
    return faction


def _serialize_factions(factions: list) -> list:
    """批量序列化阵营列表。"""
    for f in factions:
        _serialize_faction(f)
    return factions


# 端点 

@router.post("/create")
async def create_faction(req: CreateFactionRequest):
    """创建一个新阵营，挂载到指定小说下。"""
    data = req.model_dump(exclude_unset=True)
    try:
        faction_oid = await FactionService.create_faction(data)
        return {"id": faction_oid, "faction_id": data.get("faction_id"), "message": "Faction created"}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateKeyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/novel/{novel_id}")
async def get_factions_by_novel(novel_id: str):
    """获取指定小说下的所有阵营列表（按 sort_order 升序）。"""
    try:
        factions = await FactionService.get_factions_by_novel(novel_id)
        return {"data": _serialize_factions(factions)}
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/novel/{novel_id}/level/{level_type}")
async def get_factions_by_level_type(novel_id: str, level_type: str):
    """获取指定小说下特定层级类型的阵营列表。"""
    try:
        factions = await FactionService.get_factions_by_level_type(novel_id, level_type)
        return {"data": _serialize_factions(factions)}
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/novel/{novel_id}/children/{parent_faction_id}")
async def get_child_factions(novel_id: str, parent_faction_id: str):
    """获取指定父级阵营的所有直接子阵营。"""
    try:
        factions = await FactionService.get_child_factions(novel_id, parent_faction_id)
        return {"data": _serialize_factions(factions)}
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{faction_id}")
async def get_faction(faction_id: str):
    """根据业务 faction_id 获取单个阵营的详细信息。"""
    try:
        faction = await FactionService.get_faction_by_id(faction_id)
        return _serialize_faction(faction)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{faction_id}")
async def update_faction(faction_id: str, req: UpdateFactionRequest):
    """更新阵营的基础信息（白名单模式）。"""
    try:
        success = await FactionService.update_faction_info(faction_id, req.model_dump(exclude_unset=True))
        return {"success": success}
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/batch-sort")
async def batch_update_sort_order(req: BatchUpdateSortOrderRequest):
    """批量更新阵营的排序权重（用于前端拖拽排序）。"""
    try:
        updated = await FactionService.batch_update_sort_order(req.novel_id, req.sort_map)
        return {"updated_count": updated}
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{faction_id}")
async def soft_delete_faction(faction_id: str):
    """软删除指定阵营（解除子阵营挂靠）。"""
    try:
        success = await FactionService.soft_delete_faction(faction_id)
        return {"success": success}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{faction_id}/restore")
async def restore_faction(faction_id: str):
    """恢复已软删除的阵营。"""
    try:
        success = await FactionService.restore_faction(faction_id)
        return {"success": success}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{faction_id}/hard")
async def hard_delete_faction(faction_id: str):
    """彻底物理删除指定阵营，不可恢复。仅允许已软删除的阵营被硬删除。"""
    try:
        stats = await FactionService.hard_delete_faction(faction_id)
        return {"message": "Hard deleted successfully", "stats": stats}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
