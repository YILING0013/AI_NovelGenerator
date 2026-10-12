"""人物事实人工读取、预览、确认及历史接口。"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel.character_fact_contract import (
    CharacterFactConfirmV1, CharacterFactPreviewInputV1, CharacterFactPreviewV1,
    CharacterFactQueryV1, CharacterFactReadResultV1, CharacterFactRecordV1, CharacterFactResultV1,
)
from backend.services.novel import character_fact_service
from backend.services.novel.character_fact_batch_contract import CharacterFactBatchCreateV1, CharacterFactBatchResultV1
from backend.services.novel.character_fact_batch_service import create_character_fact_batch


router = APIRouter(prefix="/api/character-facts/novel/{novel_id}", tags=["character-facts"])


@router.post("/batch", response_model=CharacterFactBatchResultV1)
async def save_character_batch(
    novel_id: ObjectIdString, req: CharacterFactBatchCreateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    """整批保存人物及归属，原请求重试返回原成功结果。

    Args:
        novel_id: 当前作品。
        req: 实际资料、共同起点及原生成依据。
        idempotency_key: 首次派发即固定的请求键。
    Returns:
        保存的身份与版本；内部逐人校验不交给作者操作。
    """
    try:
        return await create_character_fact_batch(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_BATCH", label="这批人物")


@router.post("/read", response_model=CharacterFactReadResultV1)
async def read_character_facts(novel_id: ObjectIdString, req: CharacterFactQueryV1) -> dict:
    """读取指定位置或服务端解析的最新位置。

    Args:
        novel_id: 路径固定的当前小说。
        req: 人物稳定 ID 与可省略的位置。
    Returns:
        实际位置、每字段值或未知原因、来源和原读取依据。
    """
    try:
        return await character_fact_service.query_character_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_FACT", label="人物事实")


@router.post("/preview", response_model=CharacterFactPreviewV1)
async def preview_character_facts(novel_id: ObjectIdString, req: CharacterFactPreviewInputV1) -> dict:
    """冻结作者将要确认的身份、位置、字段、来源和原值。

    Args:
        novel_id: 路径固定的当前小说。
        req: 严格人工预览请求。
    Returns:
        可保留为草稿的完整预览，不写人物或事实。
    """
    try:
        return await character_fact_service.preview_character_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_FACT", label="人物事实")


@router.post("/confirm", response_model=CharacterFactResultV1)
async def confirm_character_facts(
    novel_id: ObjectIdString, req: CharacterFactConfirmV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    """按作者原预览一次保存人物事实，原键成功重放不重新执行。

    Args:
        novel_id: 路径固定的当前小说。
        req: 原预览、原版本及作者确认值或作废说明。
        idempotency_key: 首次派发即冻结的请求键。
    Returns:
        首次完整成功结果；不是当前字段查询结果。
    """
    try:
        return await character_fact_service.confirm_character_facts(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_FACT", label="人物事实")


@router.get("/history", response_model=list[CharacterFactRecordV1])
async def list_character_fact_history(
    novel_id: ObjectIdString, entity_id: ObjectIdString,
    before_version: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[dict]:
    """按物理人物身份读取历史，实体已永久删除仍保留原记录。

    Args:
        novel_id: 历史所属小说。
        entity_id: 人物物理 ID，不能用名称重新绑定。
        before_version: 可选向前翻页的版本界限。
        limit: 最多 100 条记录。
    Returns:
        版本倒序的严格事实记录数组。
    """
    try:
        return await character_fact_service.list_character_fact_history(novel_id, entity_id, before_version=before_version, limit=limit)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_FACT", label="人物事实")


@router.get("/history/{history_id}", response_model=CharacterFactRecordV1)
async def get_character_fact_history(novel_id: ObjectIdString, history_id: ObjectIdString) -> dict:
    """查看一次确认的原文及当前逐字段有效性。

    Args:
        novel_id: 历史所属小说。
        history_id: 事实记录物理 ID。
    Returns:
        严格原记录，不按今天的来源改写历史内容。
    """
    try:
        return await character_fact_service.get_character_fact_history(novel_id, history_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_FACT", label="人物事实")
