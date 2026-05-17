from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional

from backend.db.errors import DuplicateKeyError, InvalidIdError, NotFoundError
from backend.llm.schemas.novel_pydantic import CoreFactionsResultSchema
from backend.services.novel.faction_service import FactionService

router = APIRouter(prefix="/api/factions", tags=["factions"])


class CreateFactionRequest(BaseModel):
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
    sort_map: Dict[str, int]


def _serialize_faction(faction: dict) -> dict:
    """将阵营文档中的 ObjectId 转为字符串。

    Args:
        faction: MongoDB 阵营文档。

    Returns:
        可 JSON 序列化的阵营文档。
    """
    if "_id" in faction:
        faction["_id"] = str(faction["_id"])
    if "novel_id" in faction:
        faction["novel_id"] = str(faction["novel_id"])
    return faction


def _serialize_factions(factions: list) -> list:
    """批量序列化阵营列表。

    Args:
        factions: MongoDB 阵营文档列表。

    Returns:
        可 JSON 序列化的阵营文档列表。
    """
    for faction in factions:
        _serialize_faction(faction)
    return factions


def _serialize_relation(relation: dict) -> dict:
    """将阵营关系文档中的 ObjectId 转为字符串。

    Args:
        relation: MongoDB 阵营关系文档。

    Returns:
        可 JSON 序列化的阵营关系文档。
    """
    if "_id" in relation:
        relation["_id"] = str(relation["_id"])
    if "novel_id" in relation:
        relation["novel_id"] = str(relation["novel_id"])
    return relation


def _serialize_relations(relations: list) -> list:
    """批量序列化阵营关系列表。

    Args:
        relations: MongoDB 阵营关系文档列表。

    Returns:
        可 JSON 序列化的阵营关系文档列表。
    """
    for relation in relations:
        _serialize_relation(relation)
    return relations


@router.post("/novel/{novel_id}/create")
async def create_faction(novel_id: str, req: CreateFactionRequest):
    """创建一个新阵营，挂载到指定小说下。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 阵营创建请求。

    Returns:
        新阵营的 MongoDB id、业务 faction_id 和消息。
    """
    data = req.model_dump(exclude_unset=True)
    try:
        faction_oid, faction_id = await FactionService.create_faction(novel_id, data)
        return {"id": faction_oid, "faction_id": faction_id, "message": "Faction created"}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, InvalidIdError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/novel/{novel_id}/bulk-core-with-relations")
async def bulk_create_core_factions_with_relations(novel_id: str, req: CoreFactionsResultSchema):
    """批量创建全书核心阵营和阵营关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 已校验的核心阵营生成结果。

    Returns:
        新创建的核心阵营与阵营关系。
    """
    try:
        result = await FactionService.bulk_create_core_factions_with_relations(
            novel_id,
            req.model_dump(),
        )
        return {
            "factions": _serialize_factions(result["factions"]),
            "faction_relations": _serialize_relations(result["faction_relations"]),
        }
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, InvalidIdError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/novel/{novel_id}")
async def get_factions_by_novel(novel_id: str):
    """获取指定小说下的所有阵营列表。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        阵营列表响应。
    """
    try:
        factions = await FactionService.get_factions_by_novel(novel_id)
        return {"data": _serialize_factions(factions)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/novel/{novel_id}/level/{level_type}")
async def get_factions_by_level_type(novel_id: str, level_type: str):
    """获取指定小说下特定层级类型的阵营列表。

    Args:
        novel_id: 小说 ObjectId 字符串。
        level_type: 阵营层级类型。

    Returns:
        阵营列表响应。
    """
    try:
        factions = await FactionService.get_factions_by_level_type(novel_id, level_type)
        return {"data": _serialize_factions(factions)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/novel/{novel_id}/trash")
async def get_deleted_factions(novel_id: str, level_type: Optional[str] = None):
    """获取指定小说下已软删除的阵营列表。

    Args:
        novel_id: 小说 ObjectId 字符串。
        level_type: 可选阵营层级类型。

    Returns:
        已软删除阵营列表响应。
    """
    try:
        factions = await FactionService.get_deleted_factions_by_level_type(novel_id, level_type)
        return {"data": _serialize_factions(factions)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/novel/{novel_id}/children/{parent_faction_id}")
async def get_child_factions(novel_id: str, parent_faction_id: str):
    """获取指定父级阵营的所有直接子阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        parent_faction_id: 父级业务阵营 ID。

    Returns:
        子阵营列表响应。
    """
    try:
        factions = await FactionService.get_child_factions(novel_id, parent_faction_id)
        return {"data": _serialize_factions(factions)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/novel/{novel_id}/batch-sort")
async def batch_update_sort_order(novel_id: str, req: BatchUpdateSortOrderRequest):
    """批量更新阵营的排序权重。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 批量排序更新请求。

    Returns:
        被更新的阵营数量。
    """
    try:
        updated = await FactionService.batch_update_sort_order(novel_id, req.sort_map)
        return {"updated_count": updated}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/novel/{novel_id}/{faction_id}")
async def get_faction(novel_id: str, faction_id: str):
    """根据 novel_id + faction_id 获取单个阵营详情。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        阵营详情。
    """
    try:
        faction = await FactionService.get_faction(novel_id, faction_id)
        return _serialize_faction(faction)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/novel/{novel_id}/{faction_id}")
async def update_faction(novel_id: str, faction_id: str, req: UpdateFactionRequest):
    """更新阵营的基础信息。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。
        req: 阵营更新请求。

    Returns:
        更新是否成功。
    """
    try:
        success = await FactionService.update_faction_info(
            novel_id,
            faction_id,
            req.model_dump(exclude_unset=True),
        )
        return {"success": success}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, InvalidIdError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/novel/{novel_id}/{faction_id}")
async def soft_delete_faction(novel_id: str, faction_id: str):
    """软删除指定阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        软删除是否成功。
    """
    try:
        success = await FactionService.soft_delete_faction(novel_id, faction_id)
        return {"success": success}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, InvalidIdError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/novel/{novel_id}/{faction_id}/restore")
async def restore_faction(novel_id: str, faction_id: str):
    """恢复已软删除的阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        恢复是否成功。
    """
    try:
        success = await FactionService.restore_faction(novel_id, faction_id)
        return {"success": success}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, InvalidIdError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/novel/{novel_id}/{faction_id}/hard")
async def hard_delete_faction(novel_id: str, faction_id: str):
    """彻底物理删除指定阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        删除统计。
    """
    try:
        stats = await FactionService.hard_delete_faction(novel_id, faction_id)
        return {"message": "Hard deleted successfully", "stats": stats}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
