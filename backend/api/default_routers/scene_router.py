"""篇章下场景规划与回收站 API。"""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Header, Query
from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel.scene_contract import SceneCreateV1, SceneDeleteImpactV1, SceneHardDeleteV1, SceneListV1, SceneReadV1, SceneReorderV1, SceneUpdateV1, SceneVersionV1, serialize_scene
from backend.services.novel.scene_service import SceneService

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.post("/arc/{arc_id}", response_model=SceneReadV1)
async def create_scene(arc_id: ObjectIdString, req: SceneCreateV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """在篇章末尾幂等创建场景。

    Args:
        arc_id: 父篇章 ID。
        req: 场景标题和规划。
        idempotency_key: 稳定创建键。
    Returns:
        完整场景。
    """
    try:
        scene = await SceneService.create_scene(arc_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return serialize_scene(scene)


@router.get("/arc/{arc_id}", response_model=SceneListV1)
async def list_scenes(arc_id: ObjectIdString, deleted: bool = False) -> dict:
    """读取场景目录或回收站。

    Args:
        arc_id: 父篇章 ID。
        deleted: 是否查看回收站。
    Returns:
        场景目录。
    """
    try:
        rows = await SceneService.list_scenes(arc_id, deleted=deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return {"data": [serialize_scene(row) for row in rows]}


@router.patch("/arc/{arc_id}/reorder", response_model=SceneListV1)
async def reorder_scenes(arc_id: ObjectIdString, req: SceneReorderV1) -> dict:
    """提交全部活动场景的版本和新顺序。

    Args:
        arc_id: 父篇章 ID。
        req: 完整场景排序。
    Returns:
        新顺序目录。
    """
    try:
        rows = await SceneService.reorder_scenes(arc_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return {"data": [serialize_scene(row) for row in rows]}


@router.get("/{scene_id}", response_model=SceneReadV1)
async def get_scene(scene_id: ObjectIdString, include_deleted: bool = False) -> dict:
    """读取活动父链下的场景详情。

    Args:
        scene_id: 场景 ID。
        include_deleted: 是否允许回收站详情。
    Returns:
        完整场景。
    """
    try:
        scene = await SceneService.get_scene(scene_id, include_deleted=include_deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return serialize_scene(scene)


@router.get("/{scene_id}/delete-impact", response_model=SceneDeleteImpactV1)
async def get_scene_delete_impact(scene_id: ObjectIdString) -> dict:
    """读取阻止删除的章节数量。

    Args:
        scene_id: 场景 ID。
    Returns:
        活动及回收站章节数。
    """
    try:
        return await SceneService.get_delete_impact(scene_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")


@router.put("/{scene_id}", response_model=SceneReadV1)
async def update_scene(scene_id: ObjectIdString, req: SceneUpdateV1) -> dict:
    """按版本局部保存场景。

    Args:
        scene_id: 场景 ID。
        req: 版本及修改字段。
    Returns:
        保存后的场景。
    """
    try:
        scene = await SceneService.update_scene(scene_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return serialize_scene(scene)


@router.delete("/{scene_id}", response_model=SceneReadV1)
async def delete_scene(scene_id: ObjectIdString, expected_version: Annotated[int, Query(ge=1)]) -> dict:
    """将没有章节的场景移入回收站。

    Args:
        scene_id: 场景 ID。
        expected_version: 已读版本。
    Returns:
        回收站场景。
    """
    try:
        scene = await SceneService.set_deleted(scene_id, expected_version=expected_version, deleted=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return serialize_scene(scene)


@router.post("/{scene_id}/restore", response_model=SceneReadV1)
async def restore_scene(scene_id: ObjectIdString, req: SceneVersionV1) -> dict:
    """恢复场景到当前篇章末尾。

    Args:
        scene_id: 场景 ID。
        req: 已读版本。
    Returns:
        恢复后的场景。
    """
    try:
        scene = await SceneService.set_deleted(scene_id, expected_version=req.expected_version, deleted=False)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return serialize_scene(scene)


@router.delete("/{scene_id}/hard", response_model=SceneHardDeleteV1)
async def hard_delete_scene(scene_id: ObjectIdString, expected_version: Annotated[int, Query(ge=1)]) -> dict:
    """永久删除没有章节的回收站场景。

    Args:
        scene_id: 场景 ID。
        expected_version: 已读版本。
    Returns:
        删除结果。
    """
    try:
        await SceneService.hard_delete_scene(scene_id, expected_version=expected_version)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="SCENE", label="场景")
    return {"scene_id": scene_id.lower(), "deleted": True}

