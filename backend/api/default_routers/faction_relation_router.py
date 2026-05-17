from fastapi import APIRouter, HTTPException

from backend.db.errors import InvalidIdError, NotFoundError
from backend.services.novel.faction_relation_service import FactionRelationService

router = APIRouter(prefix="/api/faction-relations", tags=["faction-relations"])


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


@router.get("/novel/{novel_id}")
async def get_relations_by_novel(novel_id: str):
    """获取指定小说下当前有效的阵营关系。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        阵营关系列表响应。
    """
    try:
        relations = await FactionRelationService.get_relations_by_novel(novel_id)
        return {"data": _serialize_relations(relations)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/novel/{novel_id}/faction/{faction_id}")
async def get_relations_by_faction(novel_id: str, faction_id: str):
    """获取某个阵营参与的当前有效关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        阵营关系列表响应。
    """
    try:
        relations = await FactionRelationService.get_relations_by_faction(novel_id, faction_id)
        return {"data": _serialize_relations(relations)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
