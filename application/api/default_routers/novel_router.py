from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from application.db.repositories.novel_repository import novel_repo
from application.services.novel.novel_service import NovelService
from application.db.errors import NotFoundError, InvalidIdError

router = APIRouter(prefix="/api/novels", tags=["novels"])

class CreateNovelRequest(BaseModel):
    title: str
    subtitle: Optional[str] = None
    genre: Optional[str] = "unclassified"
    tags: Optional[List[str]] = []
    introduction: Optional[str] = None
    summary: Optional[str] = None
    core_seed: Optional[str] = None
    worldview: Optional[str] = None
    writing_style: Optional[str] = None
    narrative_pov: Optional[str] = None
    era_background: Optional[str] = None
    cover_image: Optional[str] = None

class UpdateNovelRequest(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    genre: Optional[str] = None
    tags: Optional[List[str]] = None
    introduction: Optional[str] = None
    summary: Optional[str] = None
    core_seed: Optional[str] = None
    worldview: Optional[str] = None
    writing_style: Optional[str] = None
    narrative_pov: Optional[str] = None
    era_background: Optional[str] = None
    cover_image: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str

@router.post("/create")
async def create_novel(req: CreateNovelRequest):
    """创建一个新的小说项目。"""
    data = req.dict(exclude_unset=True)
    try:
        novel_id = await novel_repo.create_novel(data)
        return {"id": novel_id, "message": "Novel created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/list")
async def get_all_novels():
    """获取所有小说的列表，仅包含基础信息。"""
    novels = await novel_repo.get_all_novels()
    for novel in novels:
        if "_id" in novel:
            novel["_id"] = str(novel["_id"])
        novel["stats"] = {
            "chapter_count": novel.get("current_chapter_count", 0),
            "total_word_count": novel.get("current_word_count", 0)
        }
    return {"data": novels}

@router.get("/deleted/list")
async def get_deleted_novels():
    """获取所有已软删除的小说列表（回收站）。"""
    novels = await novel_repo.get_deleted_novels()
    for novel in novels:
        if "_id" in novel:
            novel["_id"] = str(novel["_id"])
        novel["stats"] = {
            "chapter_count": novel.get("current_chapter_count", 0),
            "total_word_count": novel.get("current_word_count", 0)
        }
    return {"data": novels}

@router.get("/{novel_id}")
async def get_novel(novel_id: str):
    """根据ID获取指定小说的详细信息。"""
    try:
        novel = await novel_repo.get_novel_by_id(novel_id)
        novel["_id"] = str(novel["_id"])
        novel["stats"] = {
            "chapter_count": novel.get("current_chapter_count", 0),
            "total_word_count": novel.get("current_word_count", 0)
        }
        return novel
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{novel_id}")
async def update_novel(novel_id: str, req: UpdateNovelRequest):
    """更新指定小说的基础信息（如标题、简介等）。"""
    try:
        success = await novel_repo.update_novel_info(novel_id, req.dict(exclude_unset=True))
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{novel_id}/status")
async def update_status(novel_id: str, req: StatusUpdate):
    """更新指定小说的状态（例如从草稿变为连载中）。"""
    try:
        success = await novel_repo.update_novel_status(novel_id, req.status)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{novel_id}")
async def soft_delete(novel_id: str):
    """软删除指定的小说及将其放入回收站。"""
    try:
        success = await novel_repo.soft_delete_novel(novel_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{novel_id}/restore")
async def restore_novel(novel_id: str):
    """从回收站中恢复（取消软删除）指定的小说。"""
    try:
        success = await novel_repo.restore_novel(novel_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{novel_id}/hard")
async def hard_delete(novel_id: str):
    """彻底（物理）删除指定的小说及其所有关联数据，不可恢复。"""
    try:
        stats = await NovelService.hard_delete_novel(novel_id)
        return {"message": "Hard deleted successfully", "stats": stats}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
