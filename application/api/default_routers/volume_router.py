from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from application.services.novel.volume_service import VolumeService
from application.db.errors import NotFoundError, InvalidIdError, DuplicateKeyError

router = APIRouter(prefix="/api/volumes", tags=["volumes"])


class CreateVolumeRequest(BaseModel):
    novel_id: str
    title: str
    summary: Optional[str] = None
    order_index: Optional[int] = None


class UpdateVolumeRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    order_index: Optional[int] = None


class UpdateVolumeStatsRequest(BaseModel):
    arcs_count_delta: int = 0
    word_count_delta: int = 0


@router.post("/create")
async def create_volume(req: CreateVolumeRequest):
    """创建一个新卷，挂载到指定小说下。"""
    data = req.model_dump(exclude_unset=True)
    try:
        volume_id = await VolumeService.create_volume(data)
        return {"id": volume_id, "message": "Volume created"}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateKeyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/novel/{novel_id}")
async def get_volumes_by_novel(novel_id: str):
    """获取指定小说下的所有卷列表（按 order_index 升序）。"""
    try:
        volumes = await VolumeService.get_volumes_by_novel(novel_id)
        for v in volumes:
            if "_id" in v:
                v["_id"] = str(v["_id"])
            if "novel_id" in v:
                v["novel_id"] = str(v["novel_id"])
        return {"data": volumes}
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{volume_id}")
async def get_volume(volume_id: str):
    """根据ID获取单个卷的详细信息。"""
    try:
        volume = await VolumeService.get_volume_by_id(volume_id)
        volume["_id"] = str(volume["_id"])
        volume["novel_id"] = str(volume["novel_id"])
        return volume
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{volume_id}")
async def update_volume(volume_id: str, req: UpdateVolumeRequest):
    """更新卷的基础信息（标题、概要、状态、序号）。"""
    try:
        success = await VolumeService.update_volume_info(volume_id, req.model_dump(exclude_unset=True))
        return {"success": success}
    except DuplicateKeyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{volume_id}/stats")
async def update_volume_stats(volume_id: str, req: UpdateVolumeStatsRequest):
    """更新卷的统计数据（arcs_count / word_count 增减）。"""
    try:
        success = await VolumeService.update_volume_stats(
            volume_id, req.arcs_count_delta, req.word_count_delta
        )
        return {"success": success}
    except InvalidIdError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{volume_id}")
async def soft_delete_volume(volume_id: str):
    """软删除指定卷（级联软删除下属 arcs，并联动扣减小说统计）。"""
    try:
        success = await VolumeService.soft_delete_volume(volume_id)
        return {"success": success}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{volume_id}/restore")
async def restore_volume(volume_id: str):
    """恢复已软删除的卷（级联恢复下属 arcs，并联动回补小说统计）。"""
    try:
        success = await VolumeService.restore_volume(volume_id)
        return {"success": success}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, InvalidIdError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{volume_id}/hard")
async def hard_delete_volume(volume_id: str):
    """彻底物理删除指定卷及其所有关联 arcs，不可恢复。"""
    try:
        stats = await VolumeService.hard_delete_volume(volume_id)
        return {"message": "Hard deleted successfully", "stats": stats}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
