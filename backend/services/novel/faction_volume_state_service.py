"""势力卷级参与状态的领域编排、幂等、CAS 与生命周期服务。"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from bson import ObjectId
from pydantic import ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import (
    DuplicateKeyError,
    IdempotencyConflictError,
    NotFoundError,
)
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.faction_volume_state_repository import (
    faction_volume_state_initialization_receipt_repo,
    faction_volume_state_repo,
)
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import (
    build_idempotency_fingerprint,
    resolve_idempotent_replay,
    validate_expected_version,
)
from backend.llm.schemas.faction_volume_state_pydantic import (
    FactionVolumeStateFieldsV1,
    FactionVolumeStateInitializeV1,
    FactionVolumeStateUpdateV1,
    FactionVolumeStateUpsertV1,
)
from backend.services.novel.character_volume_state_service import (
    acquire_state_write_lock,
    release_state_write_lock,
)


logger = logging.getLogger(__name__)

STATE_CONTENT_FIELDS = (
    "participation_scope",
    "current_goal",
    "start_state",
    "planned_end_state",
    "power_level",
    "resources",
    "public_stance",
    "hidden_agenda",
    "influence_scope",
    "active_status",
)
INITIALIZATION_COPY_FIELDS = STATE_CONTENT_FIELDS
STATE_FACT_FIELDS = {"power_level": "power_level", "resources": "resources", "public_stance": "public_stance", "influence_scope": "influence_scope", "active_status": "story_status"}
StateChange = tuple[dict[str, Any], dict[str, Any]]


class FactionStateSourceCompensationError(RuntimeError):
    """父级删除来源传播失败且 standalone 状态补偿未完整完成。"""


def _state_error(
    code: str,
    message: str,
    *,
    status_code: int = 422,
    field_errors: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> DomainApiError:
    """构造势力卷状态领域错误。"""
    return DomainApiError(
        code,
        message,
        status_code=status_code,
        field_errors=field_errors,
        details=details,
    )


def _mongo_write_time() -> datetime:
    """生成与 BSON 往返精确相等的毫秒时间。"""
    now = get_utc_now()
    return now.replace(tzinfo=None, microsecond=(now.microsecond // 1000) * 1000)


def _validation_details(exc: ValidationError) -> dict[str, list[str]]:
    """把 Pydantic 错误压平为稳定字段路径。"""
    result: dict[str, list[str]] = {}
    for error in exc.errors():
        path = ".".join(str(part) for part in error.get("loc", ())) or "$"
        message = str(error.get("msg") or "请求字段不合法")
        if message not in result.setdefault(path, []):
            result[path].append(message)
    return result


def _normalize_text(value: str) -> str:
    """规范用户文本而不折叠有意义的内部空白。"""
    return unicodedata.normalize("NFKC", value).strip()


def _prepare_content(value: Any) -> dict[str, Any]:
    """校验并规范一条完整势力卷状态内容。"""
    try:
        model = (
            value
            if isinstance(value, FactionVolumeStateFieldsV1)
            else FactionVolumeStateFieldsV1.model_validate(value)
        )
    except ValidationError as exc:
        raise _state_error(
            "FACTION_VOLUME_STATE_VALIDATION_FAILED",
            "势力卷状态字段校验失败",
            field_errors=_validation_details(exc),
        ) from exc
    content = model.model_dump(mode="json")
    for field in (
        "current_goal",
        "start_state",
        "planned_end_state",
        "public_stance",
        "hidden_agenda",
        "influence_scope",
    ):
        content[field] = _normalize_text(content[field])
    content["resources"] = [_normalize_text(item) for item in content["resources"]]
    try:
        return FactionVolumeStateFieldsV1.model_validate(content).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        raise _state_error(
            "FACTION_VOLUME_STATE_VALIDATION_FAILED",
            "势力卷状态规范化后的字段不合法",
            field_errors=_validation_details(exc),
        ) from exc


def _state_matches_fields(
    document: Mapping[str, Any],
    fields: Mapping[str, Any],
) -> bool:
    """判断写后文档是否精确包含目标字段。"""
    return all(document.get(field) == value for field, value in fields.items())


async def _get_volume_in_novel(
    novel_id: str,
    volume_id: str,
    *,
    include_deleted: bool,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """读取并验证卷的小说作用域。"""
    volume = await volume_repo.get_volume_by_id(
        volume_id,
        include_deleted=include_deleted,
        session=session,
    )
    if volume.get("novel_id") != to_object_id(novel_id):
        raise _state_error(
            "VOLUME_NOT_FOUND",
            "卷不存在、已删除或不属于当前小说",
            status_code=404,
        )
    return volume


async def _get_faction_in_novel(
    novel_id: str,
    faction_id: str,
    *,
    include_deleted: bool,
    require_active: bool,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """读取并验证势力作用域与可用状态。"""
    faction = await faction_repo.get_faction(
        novel_id,
        faction_id,
        include_deleted=include_deleted,
        session=session,
    )
    if require_active and faction.get("active_status", "active") != "active":
        raise _state_error(
            "FACTION_NOT_ACTIVE",
            "势力已停用，不能建立或更新卷级状态",
            status_code=404,
            details={"faction_id": faction_id},
        )
    return faction


def _validate_faction_volume_scope(
    faction: Mapping[str, Any],
    volume_id: str | ObjectId,
) -> None:
    """校验势力主档是否允许参与目标卷。

    Args:
        faction: 已确认属于当前小说且可用的势力主档。
        volume_id: 目标正式卷 ObjectId 或字符串。

    Returns:
        无；core 可参与任意卷，volume/local 仅可参与归属卷。
    """
    level_type = str(faction.get("level_type") or "")
    owned_volume_id = faction.get("volume_id")
    if level_type == "core":
        if owned_volume_id is not None:
            raise _state_error(
                "FACTION_SCOPE_DATA_INVALID",
                "核心势力主档不能保存归属卷",
                status_code=409,
                details={"faction_id": str(faction.get("faction_id") or "")},
            )
        return
    if level_type not in {"volume", "local"} or owned_volume_id is None:
        raise _state_error(
            "FACTION_SCOPE_DATA_INVALID",
            "势力主档的层级与归属卷组合不完整",
            status_code=409,
            details={"faction_id": str(faction.get("faction_id") or "")},
        )
    if to_object_id(owned_volume_id) != to_object_id(volume_id):
        raise _state_error(
            "FACTION_VOLUME_SCOPE_INVALID",
            "卷级或局部势力只能参与其归属卷",
            field_errors={"volume_id": ["目标卷不是该势力的正式归属卷"]},
            details={
                "faction_id": str(faction.get("faction_id") or ""),
                "owned_volume_id": str(owned_volume_id),
            },
        )


async def _apply_state_change(
    snapshot: Mapping[str, Any],
    fields: Mapping[str, Any],
    *,
    changes: list[StateChange],
    session: AsyncClientSession | None,
    conflict_message: str,
) -> dict[str, Any]:
    """执行一次状态 CAS，并识别 standalone 写成功后的未知确认。"""
    write_time = _mongo_write_time()
    try:
        updated = await faction_volume_state_repo.update_from_snapshot(
            snapshot,
            fields,
            increment_version=True,
            write_time=write_time,
            session=session,
        )
    except Exception:
        if session is not None:
            raise
        current = await faction_volume_state_repo.collection.find_one(
            {"_id": snapshot["_id"]}
        )
        if (
            current is None
            or int(current.get("version", 0)) != int(snapshot["version"]) + 1
            or current.get("updated_at") != write_time
            or not _state_matches_fields(current, fields)
        ):
            raise
        updated = current
    if updated is None:
        raise _state_error(
            "FACTION_VOLUME_STATE_VERSION_CONFLICT",
            conflict_message,
            status_code=409,
        )
    changes.append((dict(snapshot), dict(updated)))
    return updated


async def compensate_state_changes(changes: Sequence[StateChange]) -> None:
    """按写后镜像精确恢复 standalone 状态变更。

    Args:
        changes: 当前命令已成功写入的前镜像与写后镜像。

    Returns:
        无；任一状态无法精确恢复时抛出 RuntimeError。
    """
    for before, after in reversed(list(changes)):
        restored = await faction_volume_state_repo.restore_snapshot(after, before)
        if not restored:
            raise RuntimeError("势力卷状态 standalone 补偿未精确命中")


async def _change_deletion_source(
    snapshots: Sequence[Mapping[str, Any]],
    source: Literal["volume", "faction"],
    *,
    add: bool,
    session: AsyncClientSession | None,
) -> list[StateChange]:
    """为一组状态添加或移除一个父级删除来源。"""
    changes: list[StateChange] = []
    try:
        for snapshot in snapshots:
            sources = list(dict.fromkeys(snapshot.get("deletion_sources") or []))
            if add:
                if source in sources:
                    continue
                next_sources = [*sources, source]
            else:
                if source not in sources:
                    continue
                next_sources = [item for item in sources if item != source]
            deleted_at = snapshot.get("deleted_at")
            if next_sources and deleted_at is None:
                deleted_at = _mongo_write_time()
            if not next_sources:
                deleted_at = None
            await _apply_state_change(
                snapshot,
                {
                    "deletion_sources": next_sources,
                    "is_deleted": bool(next_sources),
                    "deleted_at": deleted_at,
                },
                changes=changes,
                session=session,
                conflict_message="父级生命周期传播期间势力卷状态已变化",
            )
        return changes
    except Exception:
        if session is None and changes:
            try:
                await compensate_state_changes(changes)
            except Exception as compensation_exc:
                raise FactionStateSourceCompensationError(
                    "势力卷状态删除来源传播失败，且 standalone 补偿未完成"
                ) from compensation_exc
        raise


def _receipt_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """复制不可变初始化回执中的公开业务结果。"""
    return {
        "source_volume_id": str(receipt["source_volume_id"]),
        "target_volume_id": str(receipt["target_volume_id"]),
        "states": [dict(item) for item in receipt.get("states") or []],
    }


class FactionVolumeStateService:
    """编排势力卷状态及其跨父级生命周期不变量。"""

    @staticmethod
    async def upsert_state(
        novel_id: str,
        volume_id: str,
        faction_id: str,
        request: Any,
        *,
        idempotency_key: str | None,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按卷与势力复合路径幂等创建或完整更新一条状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 卷 ObjectId 字符串。
            faction_id: 稳定势力业务 ID。
            request: 严格完整业务字段及可选预期版本。
            idempotency_key: 创建分支必须提供的幂等键；更新分支可省略。
            session: 可选外层事务，用于档案与卷状态一起确认。

        Returns:
            新建、更新或同键同载荷重放的完整状态。
        """
        model = FactionVolumeStateUpsertV1.model_validate(request)
        payload = model.model_dump(mode="json")
        expected_version = payload.pop("expected_version")
        content = _prepare_content(payload)
        mode = "create" if expected_version is None else "update"
        fingerprint = None
        if mode == "create":
            if idempotency_key is None:
                raise _state_error(
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "创建势力卷状态必须提供 Idempotency-Key",
                )
            fingerprint = build_idempotency_fingerprint(
                idempotency_key,
                {
                    "operation": mode,
                    "novel_id": novel_id,
                    "volume_id": volume_id,
                    "faction_id": faction_id,
                    "content": content,
                },
            )

        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            if expected_version is None:
                replay = resolve_idempotent_replay(await faction_volume_state_repo.find_by_creation_idempotency(novel_id, fingerprint.key_hash, session=session), fingerprint.request_hash, label="势力卷状态创建")
                if replay is not None:
                    return replay
            from backend.services.novel.faction_fact_service import ensure_faction_fields_unmanaged
            await ensure_faction_fields_unmanaged(novel_id, [faction_id], list(STATE_FACT_FIELDS.values()), session=session)
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                if expected_version is None:
                    assert fingerprint is not None
                    replay = resolve_idempotent_replay(
                        await faction_volume_state_repo.find_by_creation_idempotency(
                            novel_id,
                            fingerprint.key_hash,
                            session=session,
                        ),
                        fingerprint.request_hash,
                        label="势力卷状态创建",
                    )
                    if replay is not None:
                        return replay
                await novel_repo.get_novel_by_id(novel_id, session=session)
                await _get_volume_in_novel(
                    novel_id,
                    volume_id,
                    include_deleted=False,
                    session=session,
                )
                faction = await _get_faction_in_novel(
                    novel_id,
                    faction_id,
                    include_deleted=False,
                    require_active=True,
                    session=session,
                )
                _validate_faction_volume_scope(faction, volume_id)
                current = await faction_volume_state_repo.find_active_by_pair(
                    novel_id,
                    volume_id,
                    faction_id,
                    session=session,
                )
                if current is not None and current.get("content_contract") == "participation_plan_v1":
                    raise _state_error("FACTION_FACT_REQUIRED", "这条记录只保存参与计划，实际情况请在剧情资料中选择位置记录", status_code=409)
                if expected_version is None:
                    assert fingerprint is not None
                    if current is not None:
                        raise _state_error(
                            "FACTION_VOLUME_STATE_ALREADY_EXISTS",
                            "该势力在本卷已有活动状态；更新必须提交 expected_version",
                            status_code=409,
                            details={
                                "state_id": str(current["state_id"]),
                                "current_version": int(current["version"]),
                            },
                        )
                    state_id = ObjectId()
                    now = _mongo_write_time()
                    document = {
                        "_id": state_id,
                        "state_id": state_id,
                        "novel_id": to_object_id(novel_id),
                        "volume_id": to_object_id(volume_id),
                        "faction_id": faction_id,
                        **content,
                        "source_state_id": None,
                        "version": 1,
                        "dependency_guard_revision": 0,
                        "is_deleted": False,
                        "deleted_at": None,
                        "deletion_sources": [],
                        "created_at": now,
                        "updated_at": now,
                        **fingerprint.as_creation_fields(),
                    }
                    try:
                        return await faction_volume_state_repo.create_state(
                            document,
                            session=session,
                        )
                    except DuplicateKeyError:
                        replay = resolve_idempotent_replay(
                            await faction_volume_state_repo.find_by_creation_idempotency(
                                novel_id,
                                fingerprint.key_hash,
                                session=session,
                            ),
                            fingerprint.request_hash,
                            label="势力卷状态创建",
                        )
                        if replay is not None:
                            return replay
                        raise
                    except Exception:
                        if session is not None:
                            raise
                        published = await faction_volume_state_repo.collection.find_one(
                            {"_id": state_id}
                        )
                        if (
                            published is None
                            or published.get("creation_idempotency_key_hash")
                            != fingerprint.key_hash
                            or published.get("creation_request_hash")
                            != fingerprint.request_hash
                        ):
                            raise
                        return published

                if current is None:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_NOT_FOUND",
                        "该势力在本卷没有可更新的活动状态",
                        status_code=404,
                    )
                expected = validate_expected_version(expected_version)
                if int(current["version"]) != expected:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_VERSION_CONFLICT",
                        "势力卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                changes: list[StateChange] = []
                return await _apply_state_change(
                    current,
                    content,
                    changes=changes,
                    session=session,
                    conflict_message="势力卷状态在更新期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)
        try:
            return await run_mongo_write_unit(write, "upsert_faction_volume_state", require_transaction=True)
        except DuplicateKeyError:
            # 唯一索引并发输家只回读正式幂等结果，不推测其他冲突成功。
            if expected_version is None:
                assert fingerprint is not None
                replay = resolve_idempotent_replay(
                    await faction_volume_state_repo.find_by_creation_idempotency(
                        novel_id,
                        fingerprint.key_hash,
                    ),
                    fingerprint.request_hash,
                    label="势力卷状态创建",
                )
                if replay is not None:
                    return replay
            raise

    @staticmethod
    async def get_state(novel_id: str, state_id: str) -> dict[str, Any]:
        """读取小说内一条活动或回收站势力卷状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 字符串。

        Returns:
            指定状态的完整正式文档。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_volume_state_repo.get_state(
            novel_id,
            state_id,
            include_deleted=True,
        )

    @staticmethod
    async def list_volume_states(
        novel_id: str,
        volume_id: str,
        *,
        scope: str | None = None,
        status: Literal["active", "deleted", "all"] = "active",
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取一卷内符合参与层级、生命周期和搜索词的状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 卷 ObjectId 字符串。
            scope: 可选 primary、secondary 或 background。
            status: active、deleted 或 all。
            q: 可选状态文本搜索词。

        Returns:
            按稳定领域顺序排列的势力卷状态列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        await _get_volume_in_novel(
            novel_id,
            volume_id,
            include_deleted=status != "active",
            session=None,
        )
        states = await faction_volume_state_repo.list_by_volume(
            novel_id,
            volume_id,
            scope=scope,
            status=status,
            q=q,
        )
        scope_order = {"primary": 0, "secondary": 1, "background": 2}
        return sorted(
            states,
            key=lambda state: (
                scope_order[str(state["participation_scope"])],
                str(state["faction_id"]),
                str(state["state_id"]),
            ),
        )

    @staticmethod
    async def list_faction_history(
        novel_id: str,
        faction_id: str,
    ) -> list[dict[str, Any]]:
        """读取势力跨卷的活动与回收站状态历史。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 稳定势力业务 ID。

        Returns:
            该势力全部卷级状态的稳定列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        await _get_faction_in_novel(
            novel_id,
            faction_id,
            include_deleted=True,
            require_active=False,
            session=None,
        )
        return await faction_volume_state_repo.list_by_faction(
            novel_id,
            faction_id,
        )

    @staticmethod
    async def update_state(novel_id: str, state_id: str, request: Any, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """按状态 ObjectId 和预期版本局部更新业务字段。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 字符串。
            request: 含 expected_version 与显式业务字段的严格请求。
            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            CAS 更新后的完整状态。
        """
        model = FactionVolumeStateUpdateV1.model_validate(request)
        payload = model.model_dump(mode="json", exclude_unset=True)
        expected = int(payload.pop("expected_version"))
        if not set(payload) & STATE_FACT_FIELDS.keys():
            from backend.services.novel.faction_volume_plan_service import update_faction_volume_plan
            return await update_faction_volume_plan(novel_id, state_id, {**payload, "expected_version": expected}, session=session)
        for field in (
            "current_goal",
            "start_state",
            "planned_end_state",
            "public_stance",
            "hidden_agenda",
            "influence_scope",
        ):
            if field in payload:
                payload[field] = _normalize_text(payload[field])
        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            from backend.services.novel.faction_fact_service import ensure_faction_fields_unmanaged
            original = await faction_volume_state_repo.get_state(novel_id, state_id, session=session)
            if original.get("content_contract") == "participation_plan_v1":
                raise _state_error("FACTION_FACT_REQUIRED", "这条记录只保存参与计划，实际情况请在剧情资料中选择位置记录", status_code=409)
            await ensure_faction_fields_unmanaged(novel_id, [original["faction_id"]], [STATE_FACT_FIELDS[field] for field in payload if field in STATE_FACT_FIELDS], session=session)
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                current = await faction_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=False,
                    session=session,
                )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_VERSION_CONFLICT",
                        "势力卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                await _get_volume_in_novel(
                    novel_id,
                    str(current["volume_id"]),
                    include_deleted=False,
                    session=session,
                )
                faction = await _get_faction_in_novel(
                    novel_id,
                    str(current["faction_id"]),
                    include_deleted=False,
                    require_active=True,
                    session=session,
                )
                _validate_faction_volume_scope(faction, current["volume_id"])
                target_content = {
                    field: payload.get(field, current[field])
                    for field in STATE_CONTENT_FIELDS
                }
                target_content = _prepare_content(target_content)
                write_fields = {
                    field: target_content[field]
                    for field in payload
                    if field in STATE_CONTENT_FIELDS
                }
                changes: list[StateChange] = []
                return await _apply_state_change(
                    current,
                    write_fields,
                    changes=changes,
                    session=session,
                    conflict_message="势力卷状态在更新期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)

        return await run_mongo_write_unit(write, "update_faction_volume_state", require_transaction=True)

    @staticmethod
    async def soft_delete_state(novel_id: str, state_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """给势力卷状态添加 user 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 字符串。
            expected_version: 调用方持有的公开版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            添加用户来源后的完整状态。
        """
        expected = validate_expected_version(expected_version)

        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                current = await faction_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=True,
                    session=session,
                )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_VERSION_CONFLICT",
                        "势力卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                sources = list(dict.fromkeys(current.get("deletion_sources") or []))
                if "user" in sources:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_ALREADY_DELETED",
                        "势力卷状态已包含用户删除来源",
                        status_code=409,
                    )
                changes: list[StateChange] = []
                return await _apply_state_change(
                    current,
                    {
                        "deletion_sources": [*sources, "user"],
                        "is_deleted": True,
                        "deleted_at": current.get("deleted_at") or _mongo_write_time(),
                    },
                    changes=changes,
                    session=session,
                    conflict_message="势力卷状态在删除期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)

        return await run_mongo_write_unit(write, "soft_delete_faction_volume_state")

    @staticmethod
    async def restore_state(novel_id: str, state_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """仅移除势力卷状态的 user 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 字符串。
            expected_version: 调用方持有的公开版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            移除用户来源后的完整状态；仍有父级来源时保持删除态。
        """
        expected = validate_expected_version(expected_version)

        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                current = await faction_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=True,
                    session=session,
                )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_VERSION_CONFLICT",
                        "势力卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                sources = list(dict.fromkeys(current.get("deletion_sources") or []))
                if "user" not in sources:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_USER_SOURCE_MISSING",
                        "势力卷状态没有可恢复的用户删除来源",
                        status_code=409,
                    )
                next_sources = [source for source in sources if source != "user"]
                changes: list[StateChange] = []
                return await _apply_state_change(
                    current,
                    {
                        "deletion_sources": next_sources,
                        "is_deleted": bool(next_sources),
                        "deleted_at": current.get("deleted_at") if next_sources else None,
                    },
                    changes=changes,
                    session=session,
                    conflict_message="势力卷状态在恢复期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)

        return await run_mongo_write_unit(write, "restore_faction_volume_state")

    @staticmethod
    async def hard_delete_state(
        novel_id: str,
        state_id: str,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        """在没有后代或结构事件引用时永久删除回收站状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 字符串。
            expected_version: 调用方持有的公开版本。

        Returns:
            含 deleted=true 与被删除 state_id 的结果。
        """
        expected = validate_expected_version(expected_version)

        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                current = await faction_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=True,
                    session=session,
                )
                if current.get("is_deleted") is not True:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_NOT_IN_TRASH",
                        "只有回收站状态可以永久删除",
                        status_code=409,
                    )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_VERSION_CONFLICT",
                        "势力卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                state_obj_id = current["state_id"]
                descendants = await faction_volume_state_repo.collection.count_documents(
                    {
                        "novel_id": to_object_id(novel_id),
                        "source_state_id": state_obj_id,
                    },
                    session=session,
                )
                protected: dict[str, int] = {}
                identity_values = [state_obj_id, str(state_obj_id)]
                for collection_name in ("arcs", "chapters", "scenes", "events"):
                    count = await BaseRepository(collection_name).collection.count_documents(
                        {
                            "novel_id": to_object_id(novel_id),
                            "$or": [
                                {"faction_volume_state_id": {"$in": identity_values}},
                                {"faction_volume_state_ids": {"$in": identity_values}},
                            ],
                        },
                        session=session,
                    )
                    if count:
                        protected[collection_name] = int(count)
                if descendants or protected:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_REFERENCE_PROTECTED",
                        "状态仍被初始化后代或结构事件引用，不能永久删除",
                        status_code=409,
                        details={
                            "source_state_descendants": int(descendants),
                            "protected_references": protected,
                        },
                    )
                try:
                    deleted = await faction_volume_state_repo.hard_delete_from_snapshot(
                        current,
                        session=session,
                    )
                except Exception:
                    if session is not None:
                        raise
                    remaining = await faction_volume_state_repo.collection.find_one(
                        {"_id": current["_id"]}
                    )
                    if remaining is None:
                        return {"deleted": True, "state_id": str(state_obj_id)}
                    raise
                if not deleted:
                    raise _state_error(
                        "FACTION_VOLUME_STATE_VERSION_CONFLICT",
                        "势力卷状态在永久删除期间已变化",
                        status_code=409,
                    )
                return {"deleted": True, "state_id": str(state_obj_id)}
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        return await run_mongo_write_unit(write, "hard_delete_faction_volume_state")

    @staticmethod
    async def initialize_from_previous(
        novel_id: str,
        target_volume_id: str,
        request: Any,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """从上一活动正式卷按白名单整批初始化选中势力。

        Args:
            novel_id: 小说 ObjectId 字符串。
            target_volume_id: 目标卷 ObjectId 字符串。
            request: 含唯一势力 ID 与目标冲突零写策略的严格请求。
            idempotency_key: 调用方提供的批量初始化幂等键。

        Returns:
            源卷、目标卷及不可变首次成功状态快照。
        """
        model = FactionVolumeStateInitializeV1.model_validate(request)
        faction_ids = sorted(model.faction_ids)
        fingerprint = build_idempotency_fingerprint(
            idempotency_key,
            {
                "operation": "initialize_from_previous",
                "novel_id": novel_id,
                "target_volume_id": target_volume_id,
                "faction_ids": faction_ids,
                "skip_existing": False,
            },
        )
        receipt = await faction_volume_state_initialization_receipt_repo.find_receipt(novel_id, fingerprint.key_hash)
        if receipt is not None:
            if receipt.get("request_hash") != fingerprint.request_hash:
                raise IdempotencyConflictError("同一 Idempotency-Key 已用于不同的势力卷状态初始化请求")
            return _receipt_result(receipt)
        raise _state_error("FACTION_FACT_REQUIRED", "旧复制请求没有成功记录；请保留原请求，使用复制参与计划入口，实际资料按剧情位置记录", status_code=409)

    @staticmethod
    async def add_faction_deletion_source(
        novel_id: str,
        faction_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> list[StateChange]:
        """给势力的全部卷状态添加 faction 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 被软删除的稳定势力业务 ID。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await faction_volume_state_repo.list_for_faction_source(
            novel_id,
            faction_id,
            session=session,
        )
        return await _change_deletion_source(
            snapshots,
            "faction",
            add=True,
            session=session,
        )

    @staticmethod
    async def remove_faction_deletion_source(
        novel_id: str,
        faction_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> list[StateChange]:
        """仅移除势力全部卷状态中的 faction 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 被恢复的稳定势力业务 ID。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await faction_volume_state_repo.list_for_faction_source(
            novel_id,
            faction_id,
            session=session,
        )
        return await _change_deletion_source(
            snapshots,
            "faction",
            add=False,
            session=session,
        )

    @staticmethod
    async def add_volume_deletion_source(
        novel_id: str,
        volume_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> list[StateChange]:
        """给目标卷全部势力状态添加 volume 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 被软删除的卷 ObjectId 字符串。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await faction_volume_state_repo.list_for_volume_source(
            novel_id,
            volume_id,
            session=session,
        )
        return await _change_deletion_source(
            snapshots,
            "volume",
            add=True,
            session=session,
        )

    @staticmethod
    async def remove_volume_deletion_source(
        novel_id: str,
        volume_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> list[StateChange]:
        """仅移除目标卷全部势力状态中的 volume 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 被恢复的卷 ObjectId 字符串。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await faction_volume_state_repo.list_for_volume_source(
            novel_id,
            volume_id,
            session=session,
        )
        return await _change_deletion_source(
            snapshots,
            "volume",
            add=False,
            session=session,
        )



__all__ = [
    "FactionVolumeStateService",
    "FactionStateSourceCompensationError",
    "StateChange",
    "compensate_state_changes",
]
