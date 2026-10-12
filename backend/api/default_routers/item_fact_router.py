"""物品按章状态、人工确认与整批AI起点接口。"""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.api.default_routers.item_router import _serialize_items
from backend.llm.schemas.item_pydantic import ItemBulkGeneratedResponseV1
from backend.services.novel import item_fact_service as service
from backend.services.novel.item_fact_contract import ItemFactPreviewInputV1, ItemFactPreviewV1, ItemFactConfirmV1, ItemFactResultV1, ItemFactRecordV1
from backend.services.novel.item_fact_api_contract import (
    ItemFactQueryV1, ItemFactReadResultV1, ItemFactBatchPreviewInputV1, ItemFactBatchPreviewV1, ItemFactBatchConfirmV1,
)
from backend.services.novel.chapter_record_contract import ChapterItemOwnerConfirmV1
from backend.services.novel.chapter_check_service import prepare_chapter_item_owner_facts
from backend.services.novel.chapter_check_contract import CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(tags=["item-facts"])


@router.post("/api/item-facts/novel/{novel_id}/read", response_model=ItemFactReadResultV1)
async def read_item_facts(novel_id: ObjectIdString, req: ItemFactQueryV1) -> dict:
    """读取选定章前后或最新位置的完整状态。

    Args:
        novel_id: 当前小说。
        req: 物品编号和位置。
    Returns:
        完整状态或未知原因，以及实际来源。
    """
    try:
        return await service.query_item_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品状态")


@router.post("/api/item-facts/novel/{novel_id}/preview", response_model=ItemFactPreviewV1)
async def preview_item_facts(novel_id: ObjectIdString, req: ItemFactPreviewInputV1) -> dict:
    """准备作者选择的整组状态，不修改正式物品。

    Args:
        novel_id: 当前小说。
        req: 原目标、位置、引用与来源。
    Returns:
        可保存到草稿的原预览。
    """
    try:
        return await service.preview_item_facts(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品状态")


@router.post("/api/item-facts/novel/{novel_id}/confirm", response_model=ItemFactResultV1)
async def confirm_item_facts(novel_id: ObjectIdString, req: ItemFactConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """按原键确认一次，成功回放不替换为今日状态。

    Args:
        novel_id: 当前小说。
        req: 冻结的预览及作者完整后值。
        idempotency_key: 首次提交的原键。
    Returns:
        原完整成功回执。
    """
    try:
        return await service.confirm_item_facts(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品状态")


@router.get("/api/item-facts/novel/{novel_id}/history", response_model=list[ItemFactRecordV1])
async def list_item_fact_history(novel_id: ObjectIdString, entity_id: ObjectIdString,
    before_version: Annotated[int | None, Query(ge=1)] = None, limit: Annotated[int, Query(ge=1, le=100)] = 100) -> list[dict]:
    """分页查看同一物理物品的原状态记录。

    Args:
        novel_id: 原所属小说。
        entity_id: 原物理身份。
        before_version: 可选向前翻页版本。
        limit: 单页数量。
    Returns:
        版本倒序的原记录。
    """
    try:
        return await service.list_item_fact_history(novel_id, entity_id, before_version=before_version, limit=limit)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品记录")


@router.get("/api/chapter-records/novel/{novel_id}/item-facts/history", response_model=list[ItemFactRecordV1])
async def list_chapter_item_fact_history(novel_id: ObjectIdString, chapter_id: ObjectIdString | None = None,
    before_id: ObjectIdString | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 100) -> list[dict]:
    """查看来源章的完整物品变化，旧 state-history 响应保持原样。

    Args:
        novel_id: 所属小说。
        chapter_id: 来源章，允许已回收；省略时供只读档案发现全书来源章。
        before_id: 上页最后一条记录身份。
        limit: 本页数量。
    Returns:
        新物品记录，包括替代和作废标记。
    """
    try:
        return await service.list_item_fact_history(novel_id, chapter_id=chapter_id, before_id=before_id, limit=limit)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品记录")


@router.get("/api/item-facts/novel/{novel_id}/history/{history_id}", response_model=ItemFactRecordV1)
async def get_item_fact_history(novel_id: ObjectIdString, history_id: ObjectIdString) -> dict:
    """查看一次原确认，保留原章版本及引文。

    Args:
        novel_id: 原所属小说。
        history_id: 原记录身份。
    Returns:
        严格原记录。
    """
    try:
        return await service.get_item_fact_history(novel_id, history_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品记录")


@router.post("/api/item-facts/novel/{novel_id}/batch/preview", response_model=ItemFactBatchPreviewV1)
async def preview_item_fact_batch(novel_id: ObjectIdString, req: ItemFactBatchPreviewInputV1) -> dict:
    """为原AI批次准备共同起点，各候选仍独立保留完整状态。

    Args:
        novel_id: 当前小说。
        req: 原整批候选及作者选择的起点。
    Returns:
        待整批确认的预览。
    """
    try:
        return await service.preview_item_fact_batch(novel_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品批次")


@router.post("/api/item-facts/novel/{novel_id}/batch/confirm", response_model=ItemBulkGeneratedResponseV1)
async def confirm_item_fact_batch(novel_id: ObjectIdString, req: ItemFactBatchConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """一次确认整批，任何一条失败则全部不保存。

    Args:
        novel_id: 当前小说。
        req: 原整批冻结请求。
        idempotency_key: 原整批确认键。
    Returns:
        原批次映射及成功快照，不是当前状态。
    """
    try:
        result = await service.confirm_item_fact_batch(novel_id, req, idempotency_key=idempotency_key)
        return {"candidate_ref_map": result["candidate_ref_map"], "items": _serialize_items(result["items"])}
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品批次")


@router.post("/api/chapter-records/novel/{novel_id}/item-facts/check")
async def check_item_facts(novel_id: ObjectIdString, req: GraphRunRequest):
    """单项B和连续性F共用原章前整组检查。

    Args:
        novel_id: 当前小说。
        req: 固定章修订、物品版本及A到B。
    Returns:
        原任务图的SSE检查结果，不写物品。
    """
    try:
        return await generate_task_flow(CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, req, scope={"novel_id": novel_id}, stream=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_CHECK", label="物品转交检查")


@router.post("/api/chapter-records/novel/{novel_id}/item-facts/prepare")
async def prepare_item_transfer(novel_id: ObjectIdString, req: ChapterItemOwnerConfirmV1) -> dict:
    """采用原转交证据，准备已有整组确认，不创建第二套回执。

    Args:
        novel_id: 当前小说。
        req: 原检查、方向、版本和引文。
    Returns:
        原整组预览和只替换持有人的完整后值。
    """
    try:
        return await prepare_chapter_item_owner_facts(novel_id, req.model_dump(mode="json"))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="ITEM_FACT", label="物品转交")
