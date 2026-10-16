"""卷参与计划不写动态事实；新计划不制造未知字段的兼容默认值。"""

from copy import deepcopy

from bson import ObjectId

from backend.db.transaction import run_mongo_write_unit
from backend.db.write_contracts import build_idempotency_fingerprint
from backend.db.repositories.faction_volume_state_repository import faction_volume_state_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.repositories.volume_command_receipt_repository import volume_command_receipt_repo
from backend.db.repositories.faction_volume_state_repository import faction_volume_state_initialization_receipt_repo
from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumePlanFieldsV1, FactionVolumePlanUpdateV1, FactionVolumeStateInitializeV1
from backend.services.novel.chapter_record_source import protect_chapter_record_sources
from backend.services.novel.faction_volume_state_service import (
    _apply_state_change, _get_faction_in_novel, _get_volume_in_novel,
    _mongo_write_time, _normalize_text, _state_error, _validate_faction_volume_scope,
    acquire_state_write_lock, release_state_write_lock,
)


PLAN_FIELDS = tuple(FactionVolumePlanFieldsV1.model_fields)


def _normalize_plan(request, *, update=False):
    """只校验当前请求中的计划字段，不重验未改的旧原文。"""
    model = FactionVolumePlanUpdateV1 if update else FactionVolumePlanFieldsV1
    fields = model.model_validate(request).model_dump(mode="json", exclude_unset=update)
    normalized = {name: _normalize_text(value) if isinstance(value, str) else value for name, value in fields.items()}
    return model.model_validate(normalized).model_dump(mode="json", exclude_unset=update)


async def _parents(novel_id, volume_id, faction_id, session):
    """在原事务内保护作品、归属卷和势力的真实来源。"""
    # 调用方已取得小说状态锁；共享来源保护要求无状态锁，不能再以空锁谓词保护自己。
    await novel_repo.get_novel_by_id(novel_id, session=session)
    volume = await _get_volume_in_novel(novel_id, volume_id, include_deleted=False, session=session)
    faction = await _get_faction_in_novel(novel_id, faction_id, include_deleted=False, require_active=True, session=session)
    _validate_faction_volume_scope(faction, volume_id)
    await protect_chapter_record_sources({(name, str(row["_id"])): row for name, row in (
        ("volumes", volume), ("factions", faction),
    )}, session=session)


async def create_faction_volume_plan(novel_id, volume_id, faction_id, request, *, idempotency_key, session=None, source_state_id=None):
    """创建五字段计划，先回放原成功；返回首次完整状态。

    Args:
        novel_id: 所属作品。
        volume_id: 目标正式卷。
        faction_id: 已有势力身份。
        request: 作者确认的五字段计划。
        idempotency_key: 原始请求键。
        session: 可选外层原子采用事务。
        source_state_id: 从上卷复制计划时明确的原状态身份。
    Returns:
        不含任何动态事实的计划或首次成功的原文档。
    """
    content = _normalize_plan(request)
    fingerprint = build_idempotency_fingerprint(idempotency_key, {
        "operation": "create_participation_plan", "novel_id": novel_id,
        "volume_id": volume_id, "faction_id": faction_id, "content": content,
        **({"source_state_id": str(source_state_id)} if source_state_id is not None else {}),
    })

    async def write(current_session):
        existing = await faction_volume_state_repo.find_by_creation_idempotency(novel_id, fingerprint.key_hash, session=current_session)
        if existing is not None:
            if existing.get("creation_request_hash") != fingerprint.request_hash:
                raise _state_error("FACTION_VOLUME_PLAN_IDEMPOTENCY_CONFLICT", "这次保存已用于其他内容，请保留原请求", status_code=409)
            return deepcopy(existing["plan_creation_result"])
        lock = await acquire_state_write_lock(novel_id, session=current_session)
        try:
            await _parents(novel_id, volume_id, faction_id, current_session)
            if await faction_volume_state_repo.find_active_by_pair(novel_id, volume_id, faction_id, session=current_session):
                raise _state_error("FACTION_VOLUME_STATE_ALREADY_EXISTS", "该势力在本卷已有参与计划，请保留输入并核对当前内容", status_code=409)
            identity, now = ObjectId(), _mongo_write_time()
            document = {"_id": identity, "state_id": identity, "novel_id": ObjectId(novel_id),
                "volume_id": ObjectId(volume_id), "faction_id": faction_id,
                "content_contract": "participation_plan_v1", **content,
                "source_state_id": ObjectId(source_state_id) if source_state_id is not None else None, "version": 1, "dependency_guard_revision": 0,
                "is_deleted": False, "deleted_at": None, "deletion_sources": [],
                "created_at": now, "updated_at": now, **fingerprint.as_creation_fields()}
            document["plan_creation_result"] = deepcopy(document)
            return await faction_volume_state_repo.create_state(document, session=current_session)
        finally:
            await release_state_write_lock(novel_id, lock, session=current_session)

    if session is not None:
        if not session.in_transaction:
            raise RuntimeError("卷参与计划保存需要事务")
        return await write(session)
    return await run_mongo_write_unit(write, "create_faction_volume_plan", require_transaction=True)


async def update_faction_volume_plan(novel_id, state_id, request, *, session=None, idempotency_key=None):
    """差量更新计划，保留旧动态原文及所有事实；版本冲突零写。

    Args:
        novel_id: 当前作品。
        state_id: 原参与记录物理身份。
        request: 原版本及实际修改的计划字段。
        session: 可选整批采用事务。
        idempotency_key: 人工请求的原键；整批采用由外层收据保护。
    Returns:
        本次计划修改后的原文档。
    """
    changes = _normalize_plan(request, update=True)
    original = {"operation": "update_faction_volume_plan", "novel_id": novel_id, "state_id": state_id, "changes": deepcopy(changes)}
    fingerprint = build_idempotency_fingerprint(idempotency_key, original) if idempotency_key is not None else None
    expected = changes.pop("expected_version")

    async def write(current_session):
        if fingerprint is not None:
            receipt = await volume_command_receipt_repo.find_receipt(novel_id, fingerprint.key_hash, session=current_session)
            if receipt is not None:
                if receipt.get("operation") != original["operation"] or receipt.get("request_hash") != fingerprint.request_hash:
                    raise _state_error("FACTION_VOLUME_PLAN_IDEMPOTENCY_CONFLICT", "这次保存已用于其他内容，请保留原请求", status_code=409)
                return deepcopy(receipt["result"])
        lock = await acquire_state_write_lock(novel_id, session=current_session)
        try:
            current = await faction_volume_state_repo.get_state(novel_id, state_id, session=current_session)
            if current["version"] != expected:
                raise _state_error("FACTION_VOLUME_STATE_VERSION_CONFLICT", "本卷计划已在另一处修改；输入已保留，请核对后再保存", status_code=409)
            await _parents(novel_id, str(current["volume_id"]), current["faction_id"], current_session)
            saved = await _apply_state_change(current, changes, changes=[], session=current_session,
                conflict_message="本卷计划在保存期间变化；输入已保留")
            if fingerprint is not None:
                await volume_command_receipt_repo.create_receipt({"novel_id": novel_id, "volume_id": current["volume_id"],
                    "operation": original["operation"], "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash,
                    "request": original, "result": deepcopy(saved)}, session=current_session)
            return saved
        finally:
            await release_state_write_lock(novel_id, lock, session=current_session)

    if session is not None:
        if not session.in_transaction:
            raise RuntimeError("卷参与计划保存需要事务")
        return await write(session)
    return await run_mongo_write_unit(write, "update_faction_volume_plan", require_transaction=True)


async def initialize_faction_volume_plans(novel_id, volume_id, request, *, idempotency_key):
    """沿用上一卷复制入口，仅复制计划；整批冲突零写，成功优先回放。

    Args:
        novel_id: 当前作品。
        volume_id: 目标卷。
        request: 作者选择的势力集合，不允许跳过冲突。
        idempotency_key: 原始整批请求键。
    Returns:
        原源卷、目标卷及首次保存的完整计划集合。
    """
    model = FactionVolumeStateInitializeV1.model_validate(request)
    identities = sorted(model.faction_ids)
    fingerprint = build_idempotency_fingerprint(idempotency_key, {
        "operation": "initialize_participation_plans_from_previous", "novel_id": novel_id,
        "target_volume_id": volume_id, "faction_ids": identities, "skip_existing": False,
    })

    async def write(session):
        receipt = await faction_volume_state_initialization_receipt_repo.find_receipt(novel_id, fingerprint.key_hash, session=session)
        if receipt is not None:
            if receipt["request_hash"] != fingerprint.request_hash:
                raise _state_error("FACTION_VOLUME_PLAN_IDEMPOTENCY_CONFLICT", "这次复制请求已用于其他内容，请保留原请求", status_code=409)
            return {"source_volume_id": str(receipt["source_volume_id"]), "target_volume_id": str(receipt["target_volume_id"]), "states": deepcopy(receipt["states"])}
        volumes = sorted(await volume_repo.get_volumes_by_novel(novel_id, session=session), key=lambda row: row["order_index"])
        index = next((index for index, row in enumerate(volumes) if str(row["_id"]) == volume_id), -1)
        if index <= 0:
            raise _state_error("FACTION_VOLUME_PLAN_SOURCE_REQUIRED", "本卷之前没有可复制参与计划的正式卷", status_code=409)
        previous = volumes[index - 1]
        sources = await faction_volume_state_repo.list_by_volume(novel_id, str(previous["_id"]), session=session)
        selected = {row["faction_id"]: row for row in sources if row["faction_id"] in identities}
        if set(selected) != set(identities):
            raise _state_error("FACTION_VOLUME_PLAN_SOURCE_CHANGED", "上卷所选计划已变化，请保留选择并重新核对", status_code=409)
        for identity in identities:
            if await faction_volume_state_repo.find_any_by_pair(novel_id, volume_id, identity, session=session):
                raise _state_error("FACTION_VOLUME_STATE_ALREADY_EXISTS", "所选势力在本卷已有参与记录；整批未保存", status_code=409)
        protected = {("volumes", str(row["_id"])): row for row in volumes}
        protected.update({("faction_volume_states", str(row["_id"])): row for row in selected.values()})
        await protect_chapter_record_sources(protected, session=session)
        states = []
        for index, identity in enumerate(identities):
            source = selected[identity]
            states.append(await create_faction_volume_plan(novel_id, volume_id, identity,
                {field: source[field] for field in PLAN_FIELDS}, idempotency_key=f"faction-plan-copy:{fingerprint.key_hash}:{index}",
                session=session, source_state_id=str(source["state_id"])))
        receipt = {"novel_id": ObjectId(novel_id), "source_volume_id": previous["_id"], "target_volume_id": ObjectId(volume_id),
            "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash,
            "operation": "initialize_participation_plans_from_previous", "faction_ids": identities,
            "state_ids": [row["state_id"] for row in states], "states": states, "created_at": _mongo_write_time()}
        await faction_volume_state_initialization_receipt_repo.create_receipt(receipt, session=session)
        return {"source_volume_id": str(previous["_id"]), "target_volume_id": volume_id, "states": states}

    return await run_mongo_write_unit(write, "initialize_faction_volume_plans", require_transaction=True)
