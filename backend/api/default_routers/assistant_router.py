"""小说级助手会话、可补读事件、候选审核和显式保存接口。"""

from __future__ import annotations

import os
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import Field

from backend.api.contracts import ObjectIdString
from backend.api.error_protocol import DomainApiError, sanitize_json_value, sse_error_payload, sse_event
from backend.config.config import get_config_value
from backend.db.base import BaseRepository
from backend.db.utils import get_utc_now
from backend.llm.config import get_llm_config
from backend.services.assistant.changes import edit_change, get_change, prepare_undo, public_change, review_change
from backend.services.assistant.contracts import AnswerRequest, AssistantModel, ChangeApproval, ChangeEdit, ContinueRequest, ResourceKind, ResourceRef, SessionCreate, SessionUpdate, TurnRequest
from backend.services.assistant.reading import catalogue_query
from backend.services.assistant.resources import build_index_record, get_resource, sync_index
from backend.services.assistant.runtime import answer_run, apply_and_resume, book_lease, cancel_run, create_run, create_session, emit_event, get_run, get_session, public_run, public_session, run_conversation, update_session


def assistant_enabled() -> bool:
    """读取独立功能开关，关闭时保留历史和原业务数据。

    Args:
        无。
    Returns:
        是否开放新的助手操作。
    """
    return os.getenv("NOVEL_ASSISTANT_ENABLED", str(get_config_value("novel_assistant_enabled", True))).lower() not in {"0", "false", "off"}


def require_assistant() -> None:
    """为新执行请求检查功能开关。

    Args:
        无。
    Returns:
        无；关闭时明确拒绝执行，查询历史仍可用。
    """
    if not assistant_enabled():
        raise DomainApiError("ASSISTANT_DISABLED", "小说助手当前已关闭，可使用原编辑入口", status_code=503)


router = APIRouter(prefix="/api/novels/{novel_id}/assistant", tags=["novel-assistant"])
RequestKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.get("/resources/{kind}/{resource_id}")
async def resource_description(novel_id: ObjectIdString, kind: ResourceKind, resource_id: str) -> dict:
    """返回引用字段选择所需的摘要，不展开长文。

    Args:
        novel_id: 当前小说。
        kind: 资料类别。
        resource_id: 当前对象。
    Returns:
        名称、可读字段和版本。
    """
    record = await get_resource(novel_id, ResourceRef(resource_type=kind, id=resource_id))
    entry = build_index_record(novel_id, kind, record)
    return {"name": entry["name"], "fields": entry["fields"], "version": entry["source_version"]}


@router.get("/resources/{kind}/{resource_id}/location")
async def resource_location(novel_id: ObjectIdString, kind: ResourceKind, resource_id: str) -> dict:
    """从当前保存记录补齐页面位置，浏览器不能用外部网址导航。

    Args:
        novel_id: 当前小说。
        kind: 资料类型。
        resource_id: 资料 ID。
    Returns:
        白名单工作台及对象查询参数。
    """
    record = await get_resource(novel_id, ResourceRef(resource_type=kind, id=resource_id), include_deleted=True)
    workspace, view, key = {
        "novel": ("novel-info", None, None), "volume": ("volume-planning", "overview", "volume_id"),
        "arc": ("arc-planning", None, "arc_id"), "scene": ("chapter-editor", None, "scene_id"), "chapter": ("chapter-editor", None, "chapter_id"),
        "character": ("character-cards", "profiles", "character_id"), "faction": ("faction-cards", "profiles", "faction_id"),
        "location": ("location-cards", "locations", "location_id"), "item": ("item-cards", "items", "item_id"), "world_rule": ("rule-cards", "rules", "rule_id"),
        "foreshadowing": ("foreshadowings", "active", "foreshadowing_id"),
        "character_relation": ("character-cards", "relations", "relation_id"), "faction_relation": ("faction-cards", "relations", "relation_id"),
        "character_faction_binding": ("character-cards", "bindings", "binding_id"),
        "character_volume_state": ("volume-planning", "characters", "state_id"), "faction_volume_state": ("volume-planning", "factions", "state_id"),
    }[kind]
    params = {"workspace": workspace, "assistant_kind": kind, "assistant_id": resource_id, "assistant_deleted": str(bool(record.get("is_deleted"))).lower()}
    if view:
        params["view"] = "trash" if record.get("is_deleted") and not kind.endswith("_volume_state") and kind != "character_faction_binding" else view
    if key:
        params[key] = resource_id
    for parent in ("volume_id", "arc_id", "scene_id", "character_id", "faction_id"):
        if record.get(parent) and parent not in params:
            params[parent] = str(record[parent])
    return {"params": params}


@router.get("/changes/{change_id}")
async def change_detail(novel_id: ObjectIdString, change_id: ObjectIdString) -> dict:
    """读取当前候选。

    Args:
        novel_id: 当前小说。
        change_id: 候选 ID。
    Returns:
        不含服务端历史和凭据的候选。
    """
    return public_change(await get_change(novel_id, change_id))


class ReviewRequest(AssistantModel):
    """只审核指定候选版本，模型设置由所属会话提供。"""
    expected_revision: int = Field(ge=1)


@router.get("/capabilities")
async def capabilities(novel_id: ObjectIdString) -> dict:
    """读取开关和可选模型，不返回凭据或接入地址。

    Args:
        novel_id: 当前小说。
    Returns:
        开关、默认服务及模型能力。
    """
    await get_resource(novel_id, ResourceRef(resource_type="novel", id=novel_id), include_deleted=True)
    config = get_llm_config()
    return {"schema_version": 1, "enabled": assistant_enabled(), "default_provider": config.default_provider,
            "creation_contract_version": 1, "writing_message_max_length": 5000,
            "providers": [{"id": name, "model": provider.default_model, "supports_function_calling": provider.supports_function_calling} for name, provider in config.providers.items() if provider.enabled]}


@router.get("/sessions")
async def sessions(novel_id: ObjectIdString, archived: bool = False) -> dict:
    """分页前的轻量会话列表，正文在详情接口读取。

    Args:
        novel_id: 当前小说。
        archived: 是否读取归档会话。
    Returns:
        最近一百个会话摘要。
    """
    rows = await BaseRepository("assistant_sessions").collection.find({"novel_id": ObjectId(novel_id), "archived": archived}).sort("updated_at", -1).limit(100).to_list()
    return {"data": [public_session(row) for row in rows]}


@router.post("/sessions", dependencies=[Depends(require_assistant)])
async def new_session(novel_id: ObjectIdString, request: SessionCreate) -> dict:
    """创建当前小说的独立会话。

    Args:
        novel_id: 当前小说。
        request: 会话设置。
    Returns:
        新会话摘要。
    """
    return public_session(await create_session(novel_id, request))


@router.get("/sessions/{session_id}")
async def session_detail(novel_id: ObjectIdString, session_id: ObjectIdString, before: str | None = None) -> dict:
    """读取持久消息、候选和最新运行，不触发后台继续。

    Args:
        novel_id: 当前小说。
        session_id: 会话 ID。
        before: 较早消息的 ObjectId 游标。
    Returns:
        最近五十条消息及此会话候选、运行信息。
    """
    chat = await get_session(novel_id, session_id)
    query = {"session_id": chat["_id"]}
    if before:
        if not ObjectId.is_valid(before):
            raise DomainApiError("ASSISTANT_CURSOR_INVALID", "消息游标不正确")
        query["_id"] = {"$lt": ObjectId(before)}
    messages = await BaseRepository("assistant_messages").collection.find(query).sort("_id", -1).limit(51).to_list()
    runs = await BaseRepository("assistant_runs").collection.find({"session_id": chat["_id"], "novel_id": chat["novel_id"]}).sort("created_at", -1).limit(20).to_list()
    current_runs = [public_run(await get_run(novel_id, str(run["_id"]))) for run in runs]
    changes = await BaseRepository("assistant_changes").collection.find({"session_id": chat["_id"], "novel_id": chat["novel_id"]}).sort("created_at", -1).limit(100).to_list()
    # 显示的旧卡片可能属于第 21 轮以后，仍按原轮次补收，不增加运行列表。
    older_run_ids = {change["run_id"] for change in changes} - {run["_id"] for run in runs}
    for run_id in older_run_ids:
        await get_run(novel_id, str(run_id))
    if older_run_ids:
        changes = await BaseRepository("assistant_changes").collection.find({"session_id": chat["_id"], "novel_id": chat["novel_id"]}).sort("created_at", -1).limit(100).to_list()
    return {"session": public_session(chat), "messages": sanitize_json_value([{**value, "id": str(value["_id"])} for value in reversed(messages[:50])]),
            "has_more": len(messages) > 50, "before": str(messages[49]["_id"]) if len(messages) > 50 else None,
            "changes": [public_change(value) for value in reversed(changes)], "runs": current_runs}


@router.patch("/sessions/{session_id}")
async def patch_session(novel_id: ObjectIdString, session_id: ObjectIdString, request: SessionUpdate) -> dict:
    """修改标题、归档状态和下一轮设置。

    Args:
        novel_id: 当前小说。
        session_id: 目标会话。
        request: 明确更新的字段。
    Returns:
        更新后的会话摘要。
    """
    return public_session(await update_session(novel_id, session_id, request))


def conversation_stream(novel_id: str, run_id: str, additional_rounds: int = 0) -> StreamingResponse:
    """把持久事件转成现有 SSE 协议，断线会停止当前执行。

    Args:
        novel_id: 当前小说。
        run_id: 目标轮次。
        additional_rounds: 明确追加的轮数。
    Returns:
        可用事件序号补读的流式响应。
    """
    async def body():
        yield sse_event("run", public_run(await get_run(novel_id, run_id)))
        try:
            async for event in run_conversation(novel_id, run_id, additional_rounds=additional_rounds):
                yield f"id: {event['seq']}\n" + sse_event(event["event"], {"seq": event["seq"], **event["data"]})
        except Exception as exc:
            yield sse_event("error", sse_error_payload(exc))
    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/sessions/{session_id}/turns/stream", dependencies=[Depends(require_assistant)])
async def turn_stream(novel_id: ObjectIdString, session_id: ObjectIdString, request: TurnRequest, idempotency_key: RequestKey) -> StreamingResponse:
    """固定本条消息并执行；同键重连不会新建或自动重跑。

    Args:
        novel_id: 当前小说。
        session_id: 当前会话。
        request: 本轮消息、位置和附件。
        idempotency_key: 该条消息的稳定发送键。
    Returns:
        持久事件流。
    """
    run = await create_run(novel_id, session_id, request, idempotency_key)
    return conversation_stream(novel_id, str(run["_id"]))


@router.get("/runs/{run_id}/events")
async def run_events(novel_id: ObjectIdString, run_id: ObjectIdString, after: int = Query(default=0, ge=0)) -> dict:
    """补读已经保存的事件，不启动执行。

    Args:
        novel_id: 当前小说。
        run_id: 轮次 ID。
        after: 已收到的最后序号。
    Returns:
        后续最多一百条事件及当前状态。
    """
    run = await get_run(novel_id, run_id)
    events = await BaseRepository("assistant_events").collection.find({"run_id": run["_id"], "seq": {"$gt": after}}, {"_id": 0, "seq": 1, "event": 1, "data": 1}).sort("seq", 1).limit(101).to_list()
    return {"run": public_run(run), "events": events[:100], "has_more": len(events) > 100}


@router.post("/runs/{run_id}/continue", dependencies=[Depends(require_assistant)])
async def continue_run(novel_id: ObjectIdString, run_id: ObjectIdString, request: ContinueRequest) -> StreamingResponse:
    """明确追加预算并从检查点继续。

    Args:
        novel_id: 当前小说。
        run_id: 轮次 ID。
        request: 追加轮数。
    Returns:
        后续持久事件流。
    """
    run = await get_run(novel_id, run_id)
    if run.get("pending_question"):
        raise DomainApiError("ASSISTANT_ANSWER_REQUIRED", "请回答对话里的问题，之后会继续原任务", status_code=409)
    return conversation_stream(novel_id, run_id, request.additional_rounds)


@router.post("/runs/{run_id}/answers/stream", dependencies=[Depends(require_assistant)])
async def answer_stream(novel_id: ObjectIdString, run_id: ObjectIdString, request: AnswerRequest, idempotency_key: RequestKey) -> StreamingResponse:
    """保存作者对原问题的回答，并从原检查点继续。

    Args:
        novel_id: 当前小说。
        run_id: 等待回答的原轮次。
        request: 问题标识与作者原回答。
        idempotency_key: 回答的稳定提交键。
    Returns:
        原轮次的后续持久事件流。
    """
    await answer_run(novel_id, run_id, request, idempotency_key)
    return conversation_stream(novel_id, run_id)


@router.post("/runs/{run_id}/cancel")
async def stop_run(novel_id: ObjectIdString, run_id: ObjectIdString) -> dict:
    """停止执行，保留已经保存的业务修改及所有候选。

    Args:
        novel_id: 当前小说。
        run_id: 当前轮次。
    Returns:
        最新运行状态。
    """
    return await cancel_run(novel_id, run_id)


@router.patch("/changes/{change_id}", dependencies=[Depends(require_assistant)])
async def patch_change(novel_id: ObjectIdString, change_id: ObjectIdString, request: ChangeEdit) -> dict:
    """编辑候选内容并清空旧审核。

    Args:
        novel_id: 当前小说。
        change_id: 修改组 ID。
        request: 原修订及新候选。
    Returns:
        需重新审核的候选。
    """
    return public_change(await edit_change(novel_id, change_id, request))


@router.post("/changes/{change_id}/review", dependencies=[Depends(require_assistant)])
async def review(novel_id: ObjectIdString, change_id: ObjectIdString, request: ReviewRequest) -> dict:
    """按会话模型独立审核当前候选。

    Args:
        novel_id: 当前小说。
        change_id: 修改组。
        request: 具体修订。
    Returns:
        带审核范围的候选。
    """
    change = await get_change(novel_id, change_id)
    chat = await get_session(novel_id, str(change["session_id"]))
    async with book_lease(novel_id, f"review:{change_id}"):
        result = await review_change(novel_id, change_id, request.expected_revision, chat)
    await emit_event(str(change["run_id"]), "change", public_change(result))
    return public_change(result)


@router.post("/changes/{change_id}/apply", dependencies=[Depends(require_assistant)])
async def apply(novel_id: ObjectIdString, change_id: ObjectIdString, request: ChangeApproval) -> dict:
    """接受作者对精确修订的确认并执行原事务保存。

    Args:
        novel_id: 当前小说。
        change_id: 修改组。
        request: 具体修订、回收恢复确认及内容风险确认。
    Returns:
        写后复读结果；同版本重复确认返回原回执。
    """
    return sanitize_json_value(await apply_and_resume(novel_id, change_id, request))


@router.post("/changes/{change_id}/undo", dependencies=[Depends(require_assistant)])
async def undo(novel_id: ObjectIdString, change_id: ObjectIdString, idempotency_key: RequestKey) -> dict:
    """准备可检查的撤销候选，仍须审核并确认。

    Args:
        novel_id: 当前小说。
        change_id: 已保存修改组。
        idempotency_key: 此次撤销准备的稳定键。
    Returns:
        新的反向候选。
    """
    change = await get_change(novel_id, change_id)
    result = await prepare_undo(novel_id, change_id, run_id=str(change["run_id"]), key=f"undo:{idempotency_key}", author_requested=True)
    await emit_event(str(change["run_id"]), "change", public_change(result))
    return public_change(result)


@router.get("/index/status")
@router.post("/index/rebuild")
async def index_status(novel_id: ObjectIdString) -> dict:
    """可恢复地核对基础索引，不调用摘要模型。

    Args:
        novel_id: 当前小说。
    Returns:
        当前覆盖数量和实际更新条数。
    """
    return await sync_index(novel_id)


@router.get("/resources")
async def attachment_resources(novel_id: ObjectIdString, query: str = Query(default="", max_length=200), offset: int = Query(default=0, ge=0)) -> dict:
    """提供附件选择器的小型资料目录。

    Args:
        novel_id: 当前小说。
        query: 普通名称或摘要文字。
        offset: 分页起点。
    Returns:
        当前二十条摘要记录。
    """
    await sync_index(novel_id)
    return await catalogue_query(novel_id, {"query": query, "offset": offset, "limit": 20})
