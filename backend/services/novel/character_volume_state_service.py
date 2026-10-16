"""角色卷级参与状态的领域编排、幂等、CAS 与生命周期服务。"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any, Literal

from bson import ObjectId
from pydantic import ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import (
    DuplicateKeyError,
    IdempotencyConflictError,
    TransactionNotSupportedError,
)
from backend.db.repositories.character_relation_repository import (
    character_relation_repo,
)
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.character_volume_state_repository import (
    character_volume_state_initialization_receipt_repo,
    character_volume_state_repo,
)
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.repositories.volume_command_receipt_repository import volume_command_receipt_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import (
    IdempotencyFingerprint,
    build_idempotency_fingerprint,
    resolve_idempotent_replay,
    validate_expected_version,
)
from backend.llm.schemas.character_volume_state_pydantic import (
    CharacterVolumePlanCreateV1,
    CharacterVolumePlanUpdateV1,
    CharacterVolumeStateFieldsV1,
    CharacterVolumeStateInitializeV1,
    CharacterVolumeStateUpdateV1,
    CharacterVolumeStateUpsertV1,
)


logger = logging.getLogger(__name__)

STATE_CONTENT_FIELDS = (
    "participation_scope",
    "current_goal",
    "start_state",
    "planned_end_state",
    "psychological_state",
    "public_state",
    "hidden_state",
    "relationship_focus_ids",
    "arc_progress",
)
INITIALIZATION_COPY_FIELDS = STATE_CONTENT_FIELDS
STATE_FACT_FIELDS = ("psychological_state", "public_state", "hidden_state")
StateChange = tuple[dict[str, Any], dict[str, Any]]


class StateSourceCompensationError(RuntimeError):
    """父级删除来源传播失败且 standalone 状态补偿未完整完成。"""


def _state_error(
    code: str,
    message: str,
    *,
    status_code: int = 422,
    field_errors: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> DomainApiError:
    """构造角色卷状态领域错误。"""
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
    """校验并规范一条完整角色卷状态内容。"""
    try:
        model = (
            value
            if isinstance(value, CharacterVolumeStateFieldsV1)
            else CharacterVolumeStateFieldsV1.model_validate(value)
        )
    except ValidationError as exc:
        raise _state_error(
            "CHARACTER_VOLUME_STATE_VALIDATION_FAILED",
            "角色卷状态字段校验失败",
            field_errors=_validation_details(exc),
        ) from exc
    content = model.model_dump(mode="json")
    for field in (
        "current_goal",
        "start_state",
        "planned_end_state",
        "psychological_state",
        "public_state",
        "hidden_state",
    ):
        content[field] = _normalize_text(content[field])
    try:
        return CharacterVolumeStateFieldsV1.model_validate(content).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        raise _state_error(
            "CHARACTER_VOLUME_STATE_VALIDATION_FAILED",
            "角色卷状态规范化后的字段不合法",
            field_errors=_validation_details(exc),
        ) from exc


def _state_matches_fields(
    document: Mapping[str, Any],
    fields: Mapping[str, Any],
) -> bool:
    """判断写后文档是否精确包含目标字段。"""
    return all(document.get(field) == value for field, value in fields.items())


async def acquire_state_write_lock(
    novel_id: str,
    *,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """取得小说级角色卷状态写互斥。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        session: 可选 MongoDB 会话。

    Returns:
        含当前锁标记与修订号的小说文档。
    """
    command_token = str(ObjectId())
    try:
        locked = await novel_repo.acquire_state_write_lock(
            novel_id,
            command_token,
            session=session,
        )
    except Exception as exc:
        if session is not None:
            if (
                isinstance(exc, OperationFailure)
                and exc.code == 112
                and exc.has_error_label("TransientTransactionError")
            ):
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_WRITE_CONFLICT",
                    "当前小说正由另一个状态或生命周期命令修改，请刷新后重试",
                    status_code=409,
                ) from exc
            raise
        current = await novel_repo.collection.find_one(
            {"_id": to_object_id(novel_id)}
        )
        if (
            current is not None
            and current.get("is_deleted") is False
            and current.get("hard_delete_claim") is None
            and current.get("state_write_lock_token") == command_token
        ):
            return current
        raise
    if locked is not None:
        return locked
    current = await novel_repo.collection.find_one({"_id": to_object_id(novel_id)})
    if current is None or current.get("is_deleted") is True:
        raise _state_error("NOVEL_NOT_FOUND", "小说不存在或已删除", status_code=404)
    raise _state_error(
        "CHARACTER_VOLUME_STATE_WRITE_CONFLICT",
        "当前小说正由另一个状态或生命周期命令修改，请刷新后重试",
        status_code=409,
    )


async def release_state_write_lock(
    novel_id: str,
    lock: Mapping[str, Any],
    *,
    session: AsyncClientSession | None,
) -> None:
    """精确释放当前命令持有的小说级状态写互斥。

    Args:
        novel_id: 小说 ObjectId 字符串。
        lock: 取得互斥时返回的小说文档。
        session: 可选 MongoDB 会话。

    Returns:
        无。
    """
    token = str(lock["state_write_lock_token"])
    revision = int(lock["state_write_lock_revision"])
    release_error: Exception | None = None
    try:
        released = await novel_repo.release_state_write_lock(
            novel_id,
            token,
            revision,
            session=session,
        )
    except Exception as exc:
        if session is not None:
            raise
        released = False
        release_error = exc
    if released:
        return
    current = await novel_repo.collection.find_one(
        {"_id": to_object_id(novel_id)},
        session=session,
    )
    if current is None:
        return
    current_revision = int(current.get("state_write_lock_revision", 0))
    if (
        current_revision == revision
        and current.get("state_write_lock_token") is None
    ) or current_revision > revision:
        return
    if (
        current_revision == revision
        and current.get("state_write_lock_token") == token
    ):
        try:
            released = await novel_repo.release_state_write_lock(
                novel_id,
                token,
                revision,
                session=session,
            )
        except Exception as exc:
            if session is not None:
                raise
            released = False
            release_error = exc
        if released:
            return
        current = await novel_repo.collection.find_one(
            {"_id": to_object_id(novel_id)},
            session=session,
        )
        if current is None:
            return
        current_revision = int(current.get("state_write_lock_revision", 0))
        if (
            current_revision == revision
            and current.get("state_write_lock_token") is None
        ) or current_revision > revision:
            return
    raise _state_error(
        "CHARACTER_VOLUME_STATE_WRITE_GUARD_UNAVAILABLE",
        "状态写入已结束，但小说级内部互斥无法精确释放",
        status_code=503,
    ) from release_error


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


async def _get_character_in_novel(
    novel_id: str,
    character_id: str,
    *,
    include_deleted: bool,
    require_active: bool,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """读取并验证角色作用域与可用状态。"""
    character = await character_repo.get_character(
        novel_id,
        character_id,
        include_deleted=include_deleted,
        session=session,
    )
    if require_active and character.get("status", "active") != "active":
        raise _state_error(
            "CHARACTER_NOT_ACTIVE",
            "角色已停用，不能建立或更新卷级状态",
            status_code=404,
            details={"character_id": character_id},
        )
    return character


async def _validate_relationship_focus(
    novel_id: str,
    character_id: str,
    relation_ids: Sequence[str],
    *,
    session: AsyncClientSession | None,
) -> None:
    """批量全等解析活动关系并要求每条关系涉及当前角色。"""
    ordered_ids = list(relation_ids)
    relations = await character_relation_repo.get_relations_by_ids(
        novel_id,
        ordered_ids,
        session=session,
    )
    resolved_ids = [str(relation["relation_id"]) for relation in relations]
    if len(relations) != len(ordered_ids) or set(resolved_ids) != set(ordered_ids):
        missing = sorted(set(ordered_ids) - set(resolved_ids))
        raise _state_error(
            "CHARACTER_RELATION_NOT_FOUND",
            "关系焦点包含不存在、已删除或跨小说的角色关系",
            status_code=404,
            details={"relation_ids": missing},
        )
    invalid: list[str] = []
    for relation in relations:
        relation_id = str(relation["relation_id"])
        if relation.get("is_active") is not True or character_id not in {
            str(relation.get("source_character_id") or ""),
            str(relation.get("target_character_id") or ""),
        }:
            invalid.append(relation_id)
    if invalid:
        raise _state_error(
            "CHARACTER_RELATION_FOCUS_INVALID",
            "关系焦点必须是涉及当前角色的活动同书关系",
            field_errors={"relationship_focus_ids": ["存在不涉及当前角色或未启用的关系"]},
            details={"relation_ids": invalid},
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
        updated = await character_volume_state_repo.update_from_snapshot(
            snapshot,
            fields,
            increment_version=True,
            write_time=write_time,
            session=session,
        )
    except Exception:
        if session is not None:
            raise
        current = await character_volume_state_repo.collection.find_one(
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
            "CHARACTER_VOLUME_STATE_VERSION_CONFLICT",
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
        restored = await character_volume_state_repo.restore_snapshot(after, before)
        if not restored:
            raise RuntimeError("角色卷状态 standalone 补偿未精确命中")


async def _change_deletion_source(
    snapshots: Sequence[Mapping[str, Any]],
    source: Literal["volume", "character"],
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
                conflict_message="父级生命周期传播期间角色卷状态已变化",
            )
        return changes
    except Exception:
        if session is None and changes:
            try:
                await compensate_state_changes(changes)
            except Exception as compensation_exc:
                raise StateSourceCompensationError(
                    "角色卷状态删除来源传播失败，且 standalone 补偿未完成"
                ) from compensation_exc
        raise


def _receipt_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """复制不可变初始化回执中的公开业务结果。"""
    return {
        "source_volume_id": str(receipt["source_volume_id"]),
        "target_volume_id": str(receipt["target_volume_id"]),
        "states": [dict(item) for item in receipt.get("states") or []],
    }


async def _check_state_command_novel(novel_id: str, *, session: AsyncClientSession) -> None:
    """在回放前保留原状态锁要求的小说可用性，不提前取得写锁。

    Args:
        novel_id: 当前小说 ID。
        session: 当前保存事务。
    Returns:
        无；小说不可用时保留原领域错误。
    """
    novel = await novel_repo.collection.find_one({"_id": to_object_id(novel_id)}, session=session)
    if novel is None or novel.get("is_deleted") is True:
        raise _state_error("NOVEL_NOT_FOUND", "小说不存在或已删除", status_code=404)
    if (novel.get("is_deleted") is not False or "hard_delete_claim" in novel
            or novel.get("state_write_lock_token") is not None):
        raise _state_error(
            "CHARACTER_VOLUME_STATE_WRITE_CONFLICT",
            "当前小说正由另一个状态或生命周期命令修改，请刷新后重试",
            status_code=409,
        )


async def _protect_unmanaged_state_fields(
    novel_id: str, character_ids: list[str], fields: Sequence[str], *, session: AsyncClientSession,
) -> None:
    """在状态锁前保护认领结果，并保留原卷状态的并发冲突错误。

    Args:
        novel_id: 当前小说 ID。
        character_ids: 此次状态保存涉及的人物。
        fields: 原请求包含的实际处境字段；纯计划为空。
        session: 调用方已开启的事务。
    Returns:
        无；发生并发写入时返回原状态冲突，不自动重跑请求。
    """
    from backend.services.novel.character_fact_service import ensure_character_fields_unmanaged

    try:
        await ensure_character_fields_unmanaged(novel_id, character_ids, list(fields), session=session)
    except OperationFailure as exc:
        if exc.code != 112 or not exc.has_error_label("TransientTransactionError"):
            raise
        raise _state_error(
            "CHARACTER_VOLUME_STATE_WRITE_CONFLICT",
            "当前小说正由另一个状态或生命周期命令修改，请刷新后重试",
            status_code=409,
        ) from exc


async def _save_volume_state(
    novel_id: str,
    volume_id: str,
    character_id: str,
    content: dict[str, Any],
    expected_version: int | None,
    fingerprint: IdempotencyFingerprint | None,
    *,
    managed_fields: Sequence[str],
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """保存旧完整状态或新的参与计划，共用回放、事实门禁和状态锁顺序。

    Args:
        novel_id: 当前小说 ID。
        volume_id: 当前卷 ID。
        character_id: 稳定人物业务 ID。
        content: 已严格校验及规范化的九字段存储内容。
        expected_version: 已有状态版本；None 表示新建。
        fingerprint: 新建入口按各自操作产生的固定指纹。
        managed_fields: 原请求实际涉及的处境字段，窄计划为空。
        session: 调用方事务；未提供时只开启一次必需事务。
    Returns:
        保存结果或原成功创建结果。
    """
    async def write(session: AsyncClientSession | None) -> dict[str, Any]:
        if session is None or not session.in_transaction:
            raise TransactionNotSupportedError("角色卷状态保存必须使用事务")
        replay = None
        if expected_version is None:
            assert fingerprint is not None
            replay = resolve_idempotent_replay(
                await character_volume_state_repo.find_by_creation_idempotency(
                    novel_id, fingerprint.key_hash, session=session,
                ),
                fingerprint.request_hash,
                label="角色卷状态创建",
            )
        await _check_state_command_novel(novel_id, session=session)
        if replay is not None:
            return replay
        await _get_volume_in_novel(novel_id, volume_id, include_deleted=False, session=session)
        await _get_character_in_novel(
            novel_id, character_id, include_deleted=False, require_active=True, session=session,
        )
        await _validate_relationship_focus(
            novel_id, character_id, content["relationship_focus_ids"], session=session,
        )
        current = await character_volume_state_repo.find_active_by_pair(
            novel_id, volume_id, character_id, session=session,
        )
        if expected_version is None and current is not None:
            raise _state_error(
                "CHARACTER_VOLUME_STATE_ALREADY_EXISTS",
                "该角色在本卷已有活动状态；更新必须提交 expected_version",
                status_code=409,
                details={"state_id": str(current["state_id"]), "current_version": int(current["version"])},
            )
        if expected_version is not None:
            if current is None:
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_NOT_FOUND", "该角色在本卷没有可更新的活动状态", status_code=404,
                )
            if int(current["version"]) != validate_expected_version(expected_version):
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_VERSION_CONFLICT", "角色卷状态版本已变化，请刷新后重试",
                    status_code=409, details={"current_version": int(current["version"])},
                )
        # 空字段的参与计划也保护小说，防止认领与新建参与行交错提交。
        await _protect_unmanaged_state_fields(novel_id, [character_id], managed_fields, session=session)
        lock = await acquire_state_write_lock(novel_id, session=session)
        try:
            if expected_version is None:
                assert fingerprint is not None
                state_id = ObjectId()
                now = _mongo_write_time()
                return await character_volume_state_repo.create_state({
                    "_id": state_id, "state_id": state_id,
                    "novel_id": to_object_id(novel_id), "volume_id": to_object_id(volume_id),
                    "character_id": character_id, **content, "source_state_id": None,
                    "version": 1, "dependency_guard_revision": 0,
                    "is_deleted": False, "deleted_at": None, "deletion_sources": [],
                    "created_at": now, "updated_at": now, **fingerprint.as_creation_fields(),
                }, session=session)
            assert current is not None
            return await _apply_state_change(
                current, content, changes=[], session=session,
                conflict_message="角色卷状态在更新期间已变化",
            )
        finally:
            await release_state_write_lock(novel_id, lock, session=session)

    if session is not None:
        return await write(session)
    return await run_mongo_write_unit(write, "save_character_volume_state", require_transaction=True)


class CharacterVolumeStateService:
    """编排角色卷状态及其跨父级生命周期不变量。"""

    @staticmethod
    async def upsert_state(
        novel_id: str,
        volume_id: str,
        character_id: str,
        request: Any,
        *,
        idempotency_key: str | None,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按旧完整请求创建或更新状态，已认领的实际处境须从人物入口修改。

        Args:
            novel_id: 当前小说 ID。
            volume_id: 当前卷 ID。
            character_id: 稳定人物业务 ID。
            request: 保留原形状的完整状态请求。
            idempotency_key: 新建必须提供；成功旧请求仍先按原指纹回放。
            session: 调用方的必需事务，提供时不另开事务。
        Returns:
            当前保存结果或原成功创建结果。
        """
        payload = CharacterVolumeStateUpsertV1.model_validate(request).model_dump(mode="json")
        expected_version = payload.pop("expected_version")
        content = _prepare_content(payload)
        fingerprint = None
        if expected_version is None:
            if idempotency_key is None:
                raise _state_error("IDEMPOTENCY_KEY_REQUIRED", "创建角色卷状态必须提供 Idempotency-Key")
            fingerprint = build_idempotency_fingerprint(idempotency_key, {
                "operation": "create", "novel_id": novel_id, "volume_id": volume_id,
                "character_id": character_id, "content": content,
            })
        return await _save_volume_state(
            novel_id, volume_id, character_id, content, expected_version, fingerprint,
            managed_fields=STATE_FACT_FIELDS, session=session,
        )

    @staticmethod
    async def create_plan(
        novel_id: str,
        volume_id: str,
        character_id: str,
        request: Any,
        *,
        idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """建立本卷参与与计划，三个旧处境字段只保留空的兼容位置。

        Args:
            novel_id: 当前小说 ID。
            volume_id: 当前卷 ID。
            character_id: 稳定人物业务 ID。
            request: 只含六个参与和计划字段的严格请求。
            idempotency_key: 此次新建固定的请求键，不能复用旧完整状态请求。
            session: 调用方的必需事务，提供时不另开事务。
        Returns:
            新建状态或同键原成功结果，不复制人物事实。
        """
        plan = CharacterVolumePlanCreateV1.model_validate(request).model_dump(mode="json")
        content = _prepare_content({**plan, **dict.fromkeys(STATE_FACT_FIELDS, "")})
        fingerprint = build_idempotency_fingerprint(idempotency_key, {
            "operation": "create_participation_plan", "novel_id": novel_id,
            "volume_id": volume_id, "character_id": character_id,
            "content": {name: content[name] for name in plan},
        })
        return await _save_volume_state(
            novel_id, volume_id, character_id, content, None, fingerprint,
            managed_fields=(), session=session,
        )

    @staticmethod
    async def update_plan(
        novel_id: str,
        state_id: str,
        request: Any,
        *,
        idempotency_key: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """局部修改本卷参与和计划，保留已有三个处境字段的原值。

        Args:
            novel_id: 当前小说 ID。
            state_id: 当前状态物理 ID。
            request: 预期版本及明确提交的参与或计划字段。
            idempotency_key: 人工保存的原请求键；已有内部事务调用可省略。
            session: 调用方的必需事务，提供时不另开事务。
        Returns:
            CAS 后状态；没有实际变化时返回原状态。
        """
        payload = CharacterVolumePlanUpdateV1.model_validate(request).model_dump(mode="json", exclude_unset=True)
        if idempotency_key is None:
            return await CharacterVolumeStateService.update_state(novel_id, state_id, payload, session=session)
        original = {"operation": "update_character_volume_plan", "novel_id": novel_id,
                    "state_id": state_id, "changes": payload}
        fingerprint = build_idempotency_fingerprint(idempotency_key, original)

        async def write(current_session):
            if current_session is None or not current_session.in_transaction:
                raise TransactionNotSupportedError("人物计划保存必须使用事务")
            # 原成功先于当前版本和目标读取；回放不再修改计划。
            receipt = await volume_command_receipt_repo.find_receipt(novel_id, fingerprint.key_hash, session=current_session)
            await _check_state_command_novel(novel_id, session=current_session)
            if receipt is not None:
                if receipt.get("operation") != original["operation"] or receipt.get("request_hash") != fingerprint.request_hash:
                    raise IdempotencyConflictError("本次人物计划请求键已用于其他内容，请保留原请求")
                return deepcopy(receipt["result"])
            saved = await CharacterVolumeStateService.update_state(novel_id, state_id, payload, session=current_session)
            await volume_command_receipt_repo.create_receipt({"novel_id": novel_id, "volume_id": saved["volume_id"],
                "operation": original["operation"], "idempotency_key_hash": fingerprint.key_hash,
                "request_hash": fingerprint.request_hash, "request": original, "result": deepcopy(saved)}, session=current_session)
            return saved

        if session is not None:
            return await write(session)
        return await run_mongo_write_unit(write, "update_character_volume_plan", require_transaction=True)

    @staticmethod
    async def get_state(novel_id: str, state_id: str) -> dict[str, Any]:
        """读取小说内一条活动或回收站角色卷状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            state_id: 状态 ObjectId 字符串。

        Returns:
            指定状态的完整正式文档。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await character_volume_state_repo.get_state(
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
            按稳定领域顺序排列的角色卷状态列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        await _get_volume_in_novel(
            novel_id,
            volume_id,
            include_deleted=status != "active",
            session=None,
        )
        states = await character_volume_state_repo.list_by_volume(
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
                str(state["character_id"]),
                str(state["state_id"]),
            ),
        )

    @staticmethod
    async def list_character_history(
        novel_id: str,
        character_id: str,
    ) -> list[dict[str, Any]]:
        """读取角色跨卷的活动与回收站状态历史。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。

        Returns:
            该角色全部卷级状态的稳定列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        await _get_character_in_novel(
            novel_id,
            character_id,
            include_deleted=True,
            require_active=False,
            session=None,
        )
        return await character_volume_state_repo.list_by_character(
            novel_id,
            character_id,
        )

    @staticmethod
    async def update_state(novel_id: str, state_id: str, request: Any, *, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """按原版本局部更新；涉及已认领处境的旧请求整笔拒绝。

        Args:
            novel_id: 当前小说 ID。
            state_id: 状态物理 ID。
            request: 含 expected_version 与显式业务字段的严格请求。
            session: 调用方的必需事务，提供时不另开事务。
        Returns:
            CAS 后状态；没有实际变化时保留原版本。
        """
        payload = CharacterVolumeStateUpdateV1.model_validate(request).model_dump(mode="json", exclude_unset=True)
        expected = int(payload.pop("expected_version"))
        for field in ("current_goal", "start_state", "planned_end_state", *STATE_FACT_FIELDS):
            if field in payload:
                payload[field] = _normalize_text(payload[field])

        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            if session is None or not session.in_transaction:
                raise TransactionNotSupportedError("角色卷状态保存必须使用事务")
            current = await character_volume_state_repo.get_state(
                novel_id, state_id, include_deleted=False, session=session,
            )
            if int(current["version"]) != expected:
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_VERSION_CONFLICT", "角色卷状态版本已变化，请刷新后重试",
                    status_code=409, details={"current_version": int(current["version"])},
                )
            await _get_volume_in_novel(novel_id, str(current["volume_id"]), include_deleted=False, session=session)
            await _get_character_in_novel(
                novel_id, str(current["character_id"]), include_deleted=False, require_active=True, session=session,
            )
            target_content = _prepare_content({field: payload.get(field, current[field]) for field in STATE_CONTENT_FIELDS})
            await _validate_relationship_focus(
                novel_id, str(current["character_id"]), target_content["relationship_focus_ids"], session=session,
            )
            write_fields = {field: target_content[field] for field in payload if field in STATE_CONTENT_FIELDS}
            # 同值夹带也属于修改已认领字段，必须在旧 no-op 判断和状态锁之前拒绝。
            await _protect_unmanaged_state_fields(
                novel_id, [str(current["character_id"])],
                [field for field in STATE_FACT_FIELDS if field in payload], session=session,
            )
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                if all(current[field] == value for field, value in write_fields.items()):
                    return current
                return await _apply_state_change(
                    current, write_fields, changes=[], session=session,
                    conflict_message="角色卷状态在更新期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)
        return await run_mongo_write_unit(write, "update_character_volume_state", require_transaction=True)

    @staticmethod
    async def soft_delete_state(novel_id: str, state_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """给角色卷状态添加 user 删除来源。

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
                current = await character_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=True,
                    session=session,
                )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_VERSION_CONFLICT",
                        "角色卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                sources = list(dict.fromkeys(current.get("deletion_sources") or []))
                if "user" in sources:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_ALREADY_DELETED",
                        "角色卷状态已包含用户删除来源",
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
                    conflict_message="角色卷状态在删除期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)

        return await run_mongo_write_unit(write, "soft_delete_character_volume_state")

    @staticmethod
    async def restore_state(novel_id: str, state_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """仅移除角色卷状态的 user 删除来源。

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
                current = await character_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=True,
                    session=session,
                )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_VERSION_CONFLICT",
                        "角色卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                sources = list(dict.fromkeys(current.get("deletion_sources") or []))
                if "user" not in sources:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_USER_SOURCE_MISSING",
                        "角色卷状态没有可恢复的用户删除来源",
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
                    conflict_message="角色卷状态在恢复期间已变化",
                )
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)

        return await run_mongo_write_unit(write, "restore_character_volume_state")

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
                current = await character_volume_state_repo.get_state(
                    novel_id,
                    state_id,
                    include_deleted=True,
                    session=session,
                )
                if current.get("is_deleted") is not True:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_NOT_IN_TRASH",
                        "只有回收站状态可以永久删除",
                        status_code=409,
                    )
                if int(current["version"]) != expected:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_VERSION_CONFLICT",
                        "角色卷状态版本已变化，请刷新后重试",
                        status_code=409,
                        details={"current_version": int(current["version"])},
                    )
                state_obj_id = current["state_id"]
                descendants = await character_volume_state_repo.collection.count_documents(
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
                                {"character_volume_state_id": {"$in": identity_values}},
                                {"character_volume_state_ids": {"$in": identity_values}},
                            ],
                        },
                        session=session,
                    )
                    if count:
                        protected[collection_name] = int(count)
                if descendants or protected:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_REFERENCE_PROTECTED",
                        "状态仍被初始化后代或结构事件引用，不能永久删除",
                        status_code=409,
                        details={
                            "source_state_descendants": int(descendants),
                            "protected_references": protected,
                        },
                    )
                try:
                    deleted = await character_volume_state_repo.hard_delete_from_snapshot(
                        current,
                        session=session,
                    )
                except Exception:
                    if session is not None:
                        raise
                    remaining = await character_volume_state_repo.collection.find_one(
                        {"_id": current["_id"]}
                    )
                    if remaining is None:
                        return {"deleted": True, "state_id": str(state_obj_id)}
                    raise
                if not deleted:
                    raise _state_error(
                        "CHARACTER_VOLUME_STATE_VERSION_CONFLICT",
                        "角色卷状态在永久删除期间已变化",
                        status_code=409,
                    )
                return {"deleted": True, "state_id": str(state_obj_id)}
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        return await run_mongo_write_unit(write, "hard_delete_character_volume_state")

    @staticmethod
    async def initialize_from_previous(
        novel_id: str,
        target_volume_id: str,
        request: Any,
        *,
        idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """从上一活动正式卷按白名单整批初始化选中角色。

        Args:
            novel_id: 小说 ObjectId 字符串。
            target_volume_id: 目标卷 ObjectId 字符串。
            request: 含唯一角色 ID 与目标冲突零写策略的严格请求。
            idempotency_key: 调用方提供的批量初始化幂等键。
            session: 调用方的必需事务，提供时不另开事务。

        Returns:
            源卷、目标卷及不可变首次成功状态快照。
        """
        model = CharacterVolumeStateInitializeV1.model_validate(request)
        character_ids = sorted(model.character_ids)
        fingerprint = build_idempotency_fingerprint(
            idempotency_key,
            {
                "operation": "initialize_from_previous",
                "novel_id": novel_id,
                "target_volume_id": target_volume_id,
                "character_ids": character_ids,
                "skip_existing": False,
            },
        )

        async def write(session: AsyncClientSession | None) -> dict[str, Any]:
            if session is None or not session.in_transaction:
                raise TransactionNotSupportedError("角色卷状态初始化必须使用事务")
            receipt = await character_volume_state_initialization_receipt_repo.find_receipt(
                novel_id,
                fingerprint.key_hash,
                session=session,
            )
            await _check_state_command_novel(novel_id, session=session)
            if receipt is not None:
                if receipt.get("request_hash") != fingerprint.request_hash:
                    raise IdempotencyConflictError(
                        "同一 Idempotency-Key 已用于不同的角色卷状态初始化请求"
                    )
                active_volumes = await volume_repo.get_volumes_by_novel(
                    novel_id,
                    session=session,
                )
                target_volume = next(
                    (
                        volume
                        for volume in active_volumes
                        if volume["_id"] == receipt.get("target_volume_id")
                        and volume["_id"] == to_object_id(target_volume_id)
                    ),
                    None,
                )
                if target_volume is None:
                    raise _state_error(
                        "VOLUME_NOT_FOUND",
                        "初始化回放的目标卷不存在、已删除或不属于当前小说",
                        status_code=404,
                    )

                receipt_character_ids = sorted(
                    str(state["character_id"]) for state in receipt["states"]
                )
                characters = await character_repo.get_characters_by_ids(
                    novel_id,
                    receipt_character_ids,
                    session=session,
                )
                found_ids = {
                    str(character["character_id"]) for character in characters
                }
                invalid_characters = sorted(
                    set(receipt_character_ids) - found_ids
                    | {
                        str(character["character_id"])
                        for character in characters
                        if character.get("status") != "active"
                    }
                )
                if invalid_characters:
                    raise _state_error(
                        "CHARACTER_NOT_FOUND",
                        "初始化回放的角色包含不存在、已删除或停用的角色",
                        status_code=404,
                        details={"character_ids": invalid_characters},
                    )
                return _receipt_result(receipt)

            await novel_repo.get_novel_by_id(novel_id, session=session)
            volumes = await volume_repo.get_volumes_by_novel(
                novel_id,
                session=session,
            )
            target_index = next(
                (
                    index
                    for index, volume in enumerate(volumes)
                    if str(volume["_id"]) == target_volume_id
                ),
                None,
            )
            if target_index is None:
                raise _state_error(
                    "VOLUME_NOT_FOUND",
                    "目标卷不存在、已删除或不属于当前小说",
                    status_code=404,
                )
            if target_index == 0:
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_PREVIOUS_VOLUME_MISSING",
                    "首卷没有可用于初始化的上一正式卷",
                )
            source_volume = volumes[target_index - 1]
            target_volume = volumes[target_index]
            source_states = await character_volume_state_repo.list_by_volume(
                novel_id,
                source_volume["_id"],
                status="active",
                session=session,
            )
            source_by_character = {
                str(state["character_id"]): state for state in source_states
            }
            missing = [
                character_id
                for character_id in character_ids
                if character_id not in source_by_character
            ]
            if missing:
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_SOURCE_MISSING",
                    "选中角色在上一正式卷没有活动状态",
                    details={"character_ids": missing},
                )
            characters = await character_repo.get_characters_by_ids(
                novel_id,
                character_ids,
                session=session,
            )
            found_ids = {str(character["character_id"]) for character in characters}
            invalid_characters = sorted(
                set(character_ids) - found_ids
                | {
                    str(character["character_id"])
                    for character in characters
                    if character.get("status", "active") != "active"
                }
            )
            if invalid_characters:
                raise _state_error(
                    "CHARACTER_NOT_FOUND",
                    "初始化角色包含不存在、已删除或停用的角色",
                    status_code=404,
                    details={"character_ids": invalid_characters},
                )
            conflicts: list[str] = []
            for character_id in character_ids:
                existing = await character_volume_state_repo.find_any_by_pair(
                    novel_id,
                    target_volume["_id"],
                    character_id,
                    session=session,
                )
                if existing is not None:
                    conflicts.append(character_id)
                await _validate_relationship_focus(
                    novel_id,
                    character_id,
                    source_by_character[character_id]["relationship_focus_ids"],
                    session=session,
                )
            if conflicts:
                raise _state_error(
                    "CHARACTER_VOLUME_STATE_INITIALIZATION_CONFLICT",
                    "目标卷已有选中角色的状态，整批未写入",
                    status_code=409,
                    details={"character_ids": conflicts},
                )

            # 原成功回执及其可用性检查优先；整批新复制才检查受管字段。
            await _protect_unmanaged_state_fields(novel_id, character_ids, STATE_FACT_FIELDS, session=session)
            lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                now = _mongo_write_time()
                documents: list[dict[str, Any]] = []
                for character_id in character_ids:
                    source = source_by_character[character_id]
                    state_id = ObjectId()
                    documents.append(
                        {
                            "_id": state_id,
                            "state_id": state_id,
                            "novel_id": to_object_id(novel_id),
                            "volume_id": target_volume["_id"],
                            "character_id": character_id,
                            **{
                                field: source[field]
                                for field in INITIALIZATION_COPY_FIELDS
                            },
                            "source_state_id": source["state_id"],
                            "version": 1,
                            "dependency_guard_revision": 0,
                            "is_deleted": False,
                            "deleted_at": None,
                            "deletion_sources": [],
                            "created_at": now,
                            "updated_at": now,
                            "initialization_idempotency_key_hash": fingerprint.key_hash,
                            "initialization_request_hash": fingerprint.request_hash,
                        }
                    )
                created = await character_volume_state_repo.create_states(documents, session=session)
                receipt = await character_volume_state_initialization_receipt_repo.create_receipt({
                    "novel_id": to_object_id(novel_id),
                    "source_volume_id": source_volume["_id"],
                    "target_volume_id": target_volume["_id"],
                    "idempotency_key_hash": fingerprint.key_hash,
                    "request_hash": fingerprint.request_hash,
                    "state_ids": [state["state_id"] for state in created],
                    "states": [dict(state) for state in created],
                }, session=session)
                return _receipt_result(receipt)
            finally:
                await release_state_write_lock(novel_id, lock, session=session)

        if session is not None:
            return await write(session)
        return await run_mongo_write_unit(
            write, "initialize_character_volume_states_from_previous", require_transaction=True,
        )

    @staticmethod
    async def ensure_relations_can_be_disabled(
        novel_id: str,
        relation_ids: Sequence[str],
        *,
        session: AsyncClientSession | None,
    ) -> None:
        """阻止仍被任一状态焦点引用的关系失效。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_ids: 即将禁用、软删除或随端点角色失效的关系 ID。
            session: 当前生命周期写入单元的可选 MongoDB 会话。

        Returns:
            无；不存在活动或回收站状态引用时正常返回。
        """
        unique_ids = list(dict.fromkeys(relation_ids))
        if not unique_ids:
            return
        references = await character_volume_state_repo.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "relationship_focus_ids": {"$in": unique_ids},
            },
            include_deleted=True,
            sort=[("state_id", 1)],
            session=session,
        )
        if references:
            raise _state_error(
                "CHARACTER_RELATION_STATE_REFERENCE_PROTECTED",
                "角色关系仍被卷级状态焦点引用，不能禁用或删除",
                status_code=409,
                details={
                    "relation_ids": unique_ids,
                    "state_ids": [str(state["state_id"]) for state in references],
                    "count": len(references),
                },
            )

    @staticmethod
    async def add_character_deletion_source(
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> list[StateChange]:
        """给角色的全部卷状态添加 character 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 被软删除的稳定角色业务 ID。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await character_volume_state_repo.list_for_character_source(
            novel_id,
            character_id,
            session=session,
        )
        return await _change_deletion_source(
            snapshots,
            "character",
            add=True,
            session=session,
        )

    @staticmethod
    async def remove_character_deletion_source(
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> list[StateChange]:
        """仅移除角色全部卷状态中的 character 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 被恢复的稳定角色业务 ID。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await character_volume_state_repo.list_for_character_source(
            novel_id,
            character_id,
            session=session,
        )
        return await _change_deletion_source(
            snapshots,
            "character",
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
        """给目标卷全部角色状态添加 volume 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 被软删除的卷 ObjectId 字符串。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await character_volume_state_repo.list_for_volume_source(
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
        """仅移除目标卷全部角色状态中的 volume 删除来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 被恢复的卷 ObjectId 字符串。
            session: 父级生命周期写入单元的可选 MongoDB 会话。

        Returns:
            当前命令实际修改的前镜像与写后镜像。
        """
        snapshots = await character_volume_state_repo.list_for_volume_source(
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

    @staticmethod
    async def get_arc_readiness(
        novel_id: str,
        volume_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """计算一卷进入人物弧规划前的活动主角状态门禁。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 当前规划卷 ObjectId 字符串。
            session: 可选 MongoDB 会话，供后续 Arc 写入单元复用。

        Returns:
            活动主角、已有状态主角及 ready 布尔值。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        await _get_volume_in_novel(
            novel_id,
            volume_id,
            include_deleted=False,
            session=session,
        )
        protagonists = await character_repo.find_many(
            {
                "novel_id": to_object_id(novel_id),
                "role_type": "protagonist",
                "status": "active",
            },
            sort=[("sort_order", 1), ("character_id", 1)],
            session=session,
        )
        protagonist_ids = [str(item["character_id"]) for item in protagonists]
        states = await character_volume_state_repo.list_by_volume(
            novel_id,
            volume_id,
            status="active",
            session=session,
        )
        state_character_ids = sorted(
            {
                str(state["character_id"])
                for state in states
                if str(state["character_id"]) in set(protagonist_ids)
            }
        )
        return {
            "novel_id": novel_id,
            "volume_id": volume_id,
            "ready": bool(protagonist_ids and state_character_ids),
            "active_protagonist_ids": protagonist_ids,
            "protagonist_state_character_ids": state_character_ids,
        }

    @staticmethod
    async def ensure_arc_readiness(
        novel_id: str,
        volume_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """要求当前卷至少一个活动主角已建立活动卷状态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            volume_id: 当前规划卷 ObjectId 字符串。
            session: 可选 MongoDB 会话，供 Arc 创建事务复用。

        Returns:
            门禁通过时返回完整 readiness 结果。
        """
        readiness = await CharacterVolumeStateService.get_arc_readiness(
            novel_id,
            volume_id,
            session=session,
        )
        if not readiness["ready"]:
            raise _state_error(
                "ARC_CHARACTER_VOLUME_STATE_NOT_READY",
                "当前卷至少需要一个活动主角的活动卷状态才能规划人物弧",
                status_code=409,
                details=readiness,
            )
        return readiness


__all__ = [
    "CharacterVolumeStateService",
    "StateSourceCompensationError",
    "StateChange",
    "acquire_state_write_lock",
    "compensate_state_changes",
    "release_state_write_lock",
]
