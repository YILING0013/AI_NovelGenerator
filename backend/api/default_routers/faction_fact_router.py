"""势力按剧情位置记录资料的产品路由，与旧写口保护同时接入。"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel import faction_fact_service as service
from backend.services.novel.faction_fact_api_contract import (
    FactionFactQueryV1, FactionFactPreviewRequestV1, FactionFactPreviewV1,
)
from backend.services.novel.faction_fact_contract import (
    FactionFactConfirmV1, FactionFactReadResultV1, FactionFactRecordV1, FactionFactResultV1,
)
from backend.services.novel.faction_fact_batch_contract import FactionFactBatchCreateV1, FactionFactBatchResultV1
from backend.services.novel.faction_fact_batch_service import create_faction_fact_batch


router = APIRouter(prefix="/api/faction-facts/novel/{novel_id}", tags=["faction-facts"])


@router.post("/create-batch", response_model=FactionFactBatchResultV1)
async def create_faction_batch(novel_id: ObjectIdString, req: FactionFactBatchCreateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """整批采用势力及关系；位置与内容一次确认，原键恢复原请求。

    Args:
        novel_id: 当前作品。
        req: 原位置、候选及生成依据。
        idempotency_key: 首次派发保留的原键。
    Returns:
        首次完整公开结果。
    """
    try:
        return await create_faction_fact_batch(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FACTION_FACT", label="势力资料")


@router.post("/read", response_model=FactionFactReadResultV1)
async def read_faction_facts(novel_id: ObjectIdString, req: FactionFactQueryV1) -> dict:
    """读取指定位置的势力资料，缺项保持未知。

    Args:
        novel_id: 当前小说。
        req: 势力编号和可选位置。
    Returns:
        原位置、逐字段值和可复验依据。
    """
    try:
        return await service.query_faction_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FACTION_FACT", label="势力资料")


@router.post("/preview", response_model=FactionFactPreviewV1)
async def preview_faction_facts(novel_id: ObjectIdString, req: FactionFactPreviewRequestV1) -> dict:
    """准备本次修改，不创建势力或占用编号。

    Args:
        novel_id: 当前小说。
        req: 原目标版本、位置、字段和来源。
    Returns:
        可冻结到原草稿的预览。
    """
    try:
        return await service.preview_faction_facts(novel_id, req.model_dump(mode="json", exclude_unset=True))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FACTION_FACT", label="势力资料")


@router.post("/confirm", response_model=FactionFactResultV1)
async def confirm_faction_facts(novel_id: ObjectIdString, req: FactionFactConfirmV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """原样提交已冻结的请求，成功重放优先于今日来源检查。

    Args:
        novel_id: 原所属小说。
        req: 原严格确认命令。
        idempotency_key: 首次提交的键，结果未知时不能更换。
    Returns:
        首次完整成功结果。
    """
    try:
        return await service.confirm_faction_facts(novel_id, req.model_dump(mode="json", exclude_unset=True), idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FACTION_FACT", label="势力资料")


@router.get("/history", response_model=list[FactionFactRecordV1])
async def list_faction_fact_history(novel_id: ObjectIdString, entity_id: ObjectIdString,
    before_version: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100) -> list[dict]:
    """按原物理身份分页查看历史，包括已回收势力。

    Args:
        novel_id: 原所属小说。
        entity_id: 原势力物理身份。
        before_version: 上页最后的保存版本。
        limit: 本页上限。
    Returns:
        版本倒序的原记录，不把旧裸资料升级成事实。
    """
    try:
        return await service.list_faction_fact_history(novel_id, entity_id, before_version=before_version, limit=limit)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FACTION_FACT", label="势力记录")


@router.get("/history/{history_id}", response_model=FactionFactRecordV1)
async def get_faction_fact_history(novel_id: ObjectIdString, history_id: ObjectIdString) -> dict:
    """查看一条原记录，保留当时的来源和逐字段处置。

    Args:
        novel_id: 原所属小说。
        history_id: 原历史记录身份。
    Returns:
        严格原记录。
    """
    try:
        return await service.get_faction_fact_history(novel_id, history_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FACTION_FACT", label="势力记录")
