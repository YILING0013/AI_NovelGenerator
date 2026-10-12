"""关系事实章后检查、人工读取、预览、确认及历史接口。"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel.character_relation_fact_contract import (
    CharacterRelationFactConfirmV1, CharacterRelationFactPreviewInputV1, CharacterRelationFactPreviewV1,
    CharacterRelationFactQueryV1, CharacterRelationFactReadResultV1, CharacterRelationFactRecordV1, CharacterRelationFactResultV1,
)
from backend.services.novel import character_relation_fact_service
from backend.services.novel.character_fact_batch_contract import CharacterRelationFactBatchCreateV1, CharacterRelationFactBatchResultV1
from backend.services.novel.character_fact_batch_service import create_character_relation_fact_batch
from backend.api.default_routers.character_relation_router import CharacterRelationIdPath, serialize_character_relation
from backend.llm.schemas.character_relation_pydantic import CharacterRelationDesignUpdateRequestV1, CharacterRelationResponseV1
from backend.services.novel.character_relation_service import CharacterRelationService
from backend.services.novel.chapter_check_contract import CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(tags=["character-relation-facts"])


@router.post("/api/character-relation-facts/novel/{novel_id}/batch", response_model=CharacterRelationFactBatchResultV1)
async def save_character_relation_batch(
    novel_id: ObjectIdString, req: CharacterRelationFactBatchCreateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    """整批保存新关系，不覆盖已有内容。

    Args:
        novel_id: 当前作品。
        req: 各段关系及其起点状态。
        idempotency_key: 原请求固定的重试键。
    Returns:
        原成功身份和版本。
    """
    try:
        return await create_character_relation_fact_batch(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_BATCH", label="这批人物关系")


@router.post("/api/chapter-records/novel/{novel_id}/character-relation-facts/check")
async def check_character_relation_facts(novel_id: ObjectIdString, req: GraphRunRequest):
    """按原章前事实生成关系建议，供单项检查和逐项检查共用。

    Args:
        novel_id: 路径固定的当前小说。
        req: 原任务图请求及固定章修订、关系和版本。
    Returns:
        含章前已知值或未知原因的 SSE 候选；采用后另走人工事实预览。
    """
    try:
        return await generate_task_flow(CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, req, scope={"novel_id": novel_id}, stream=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_CHECK", label="章后人物关系事实检查")


@router.post("/api/character-relation-facts/novel/{novel_id}/read", response_model=CharacterRelationFactReadResultV1)
async def read_character_relation_facts(novel_id: ObjectIdString, req: CharacterRelationFactQueryV1) -> dict:
    """读取指定位置或服务端解析的最新位置。

    Args:
        novel_id: 路径固定的当前小说。
        req: 关系稳定 ID 与可省略的位置。
    Returns:
        实际位置、每字段值或未知原因、来源和原读取依据。
    """
    try:
        return await character_relation_fact_service.query_character_relation_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_FACT", label="关系事实")


@router.post("/api/character-relation-facts/novel/{novel_id}/preview", response_model=CharacterRelationFactPreviewV1)
async def preview_character_relation_facts(novel_id: ObjectIdString, req: CharacterRelationFactPreviewInputV1) -> dict:
    """冻结作者将要确认的身份、位置、字段、来源和原值。

    Args:
        novel_id: 路径固定的当前小说。
        req: 严格人工预览请求。
    Returns:
        可保留为草稿的完整预览，不写关系或事实。
    """
    try:
        return await character_relation_fact_service.preview_character_relation_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_FACT", label="关系事实")


@router.post("/api/character-relation-facts/novel/{novel_id}/confirm", response_model=CharacterRelationFactResultV1)
async def confirm_character_relation_facts(
    novel_id: ObjectIdString, req: CharacterRelationFactConfirmV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    """按作者原预览一次保存关系事实，原键成功重放不重新执行。

    Args:
        novel_id: 路径固定的当前小说。
        req: 原预览、原版本及作者确认值或作废说明。
        idempotency_key: 首次派发即冻结的请求键。
    Returns:
        首次完整成功结果；不是当前字段查询结果。
    """
    try:
        return await character_relation_fact_service.confirm_character_relation_facts(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_FACT", label="关系事实")


@router.get("/api/character-relation-facts/novel/{novel_id}/history", response_model=list[CharacterRelationFactRecordV1])
async def list_character_relation_fact_history(
    novel_id: ObjectIdString, entity_id: ObjectIdString,
    before_version: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[dict]:
    """按物理关系身份读取历史，实体已永久删除仍保留原记录。

    Args:
        novel_id: 历史所属小说。
        entity_id: 关系物理 ID，不能用名称重新绑定。
        before_version: 可选向前翻页的版本界限。
        limit: 最多 100 条记录。
    Returns:
        版本倒序的严格事实记录数组。
    """
    try:
        return await character_relation_fact_service.list_character_relation_fact_history(novel_id, entity_id, before_version=before_version, limit=limit)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_FACT", label="关系事实")


@router.get("/api/character-relation-facts/novel/{novel_id}/history/{history_id}", response_model=CharacterRelationFactRecordV1)
async def get_character_relation_fact_history(novel_id: ObjectIdString, history_id: ObjectIdString) -> dict:
    """查看一次确认的原文及当前逐字段有效性。

    Args:
        novel_id: 历史所属小说。
        history_id: 事实记录物理 ID。
    Returns:
        严格原记录，不按今天的来源改写历史内容。
    """
    try:
        return await character_relation_fact_service.get_character_relation_fact_history(novel_id, history_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_FACT", label="关系事实")


@router.put(
    "/api/character-relations/novel/{novel_id}/{relation_id}/design",
    response_model=CharacterRelationResponseV1,
)
async def update_character_relation_design(
    novel_id: ObjectIdString, relation_id: CharacterRelationIdPath,
    req: CharacterRelationDesignUpdateRequestV1,
) -> CharacterRelationResponseV1:
    """保存关系设计，状态事实和端点保持原样。

    Args:
        novel_id: 关系所属小说。
        relation_id: 原关系的稳定业务 ID。
        req: 六个设计字段及原版本。
    Returns:
        版本递增一次后的关系公开响应。
    """
    try:
        relation = await CharacterRelationService.update_relation_design(novel_id, relation_id, req)
        return serialize_character_relation(relation)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_RELATION_DESIGN", label="关系设计")
