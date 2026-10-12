"""角色主档领域服务。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError, DuplicateKeyError as PyMongoDuplicateKeyError, OperationFailure

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import DEPENDENCY_GUARD_FIELD
from backend.db.errors import DuplicateKeyError, NotFoundError, TransactionNotSupportedError
from backend.db.repositories.character_faction_binding_repository import (
    character_faction_binding_repo,
)
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.llm.schemas.character_pydantic import (
    CoreCharactersAIConfirmationRequestV1,
)
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import (
    checksum,
    hash_idempotency_key,
)
from backend.services.novel.character_name import normalize_character_name
from backend.services.novel.item_service import (
    acquire_item_write_lock,
    release_item_write_lock,
)
from backend.services.novel.character_volume_state_service import (
    CharacterVolumeStateService,
    StateSourceCompensationError,
    acquire_state_write_lock,
    compensate_state_changes,
    release_state_write_lock,
)


CHARACTER_CONTENT_FIELDS: tuple[str, ...] = (
    "name",
    "aliases",
    "role_type",
    "importance_level",
    "gender",
    "age_group",
    "race",
    "identity",
    "appearance",
    "personality",
    "core_desire",
    "core_fear",
    "strengths",
    "weaknesses",
    "abilities",
    "conflict_with_mainline",
    "relationship_with_protagonist",
    "initial_state",
    "growth_direction",
    "story_function",
    "arc_seed",
    "tags",
    "sort_order",
    "extra",
)

CHARACTER_EDITABLE_FIELDS: tuple[str, ...] = tuple(
    field for field in CHARACTER_CONTENT_FIELDS if field != "sort_order"
)

AI_CHARACTER_CONTENT_FIELDS: tuple[str, ...] = tuple(
    field for field in CHARACTER_CONTENT_FIELDS if field not in {"sort_order", "extra"}
)

_LIST_FIELDS: tuple[str, ...] = (
    "aliases",
    "strengths",
    "weaknesses",
    "abilities",
    "tags",
)

_TEXT_DEFAULTS: dict[str, str] = {
    "role_type": "supporting",
    "importance_level": "supporting",
    "gender": "",
    "age_group": "",
    "race": "",
    "identity": "",
    "appearance": "",
    "personality": "",
    "core_desire": "",
    "core_fear": "",
    "conflict_with_mainline": "",
    "relationship_with_protagonist": "",
    "initial_state": "",
    "growth_direction": "",
    "story_function": "",
    "arc_seed": "",
}

logger = logging.getLogger(__name__)

DEPENDENCY_RECONCILE_MAX_ATTEMPTS = 3


class _DependencyReconcileCasMiss(DuplicateKeyError):
    """标识依赖调和时可通过重新读取解决的乐观锁未命中。"""


async def _run_bounded_dependency_reconcile(
    reconcile_once: Callable[[], Awaitable[None]],
    *,
    label: str,
    max_attempts: int = DEPENDENCY_RECONCILE_MAX_ATTEMPTS,
) -> None:
    """对明确的依赖 CAS miss 执行有界重读，直至按主档真相收敛。

    Args:
        reconcile_once: 每次都重新读取依赖并执行单轮 CAS 调和的异步函数。
        label: 达到上限时用于错误信息的领域标签。
        max_attempts: 包含首次执行在内的最大尝试次数。

    Returns:
        无；任一轮完整调和成功即返回。

    Raises:
        ValueError: 最大尝试次数不是正整数。
        _DependencyReconcileCasMiss: 连续发生 CAS miss 并达到重试上限。
    """
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or max_attempts < 1
    ):
        raise ValueError("max_attempts 必须为正整数")

    for attempt in range(1, max_attempts + 1):
        try:
            await reconcile_once()
            return
        except _DependencyReconcileCasMiss as exc:
            if attempt >= max_attempts:
                raise _DependencyReconcileCasMiss(
                    f"{label}连续 {max_attempts} 次重读仍发生版本冲突，请重试"
                ) from exc
            # 仅 CAS miss 进入下一轮；唯一约束和业务冲突不会被盲目重试。
            continue

# 角色生命周期需要跨集合维护可用性；直接使用基础仓储可避免把角色级联规则散落到关系领域服务。
_character_relation_repo = BaseRepository("character_relations")
_character_binding_repo = BaseRepository("character_faction_bindings")


@dataclass(frozen=True)
class _CompensationRecord:
    """描述一次 standalone 写入完成后的可安全补偿条件。"""

    snapshot: dict[str, Any]
    operation: Literal["updated", "deleted"]
    expected_after_version: int | None = None
    expected_after_is_deleted: bool | None = None


def _updated_compensation_record(
    snapshot: dict[str, Any],
    written_document: Mapping[str, Any],
) -> _CompensationRecord:
    """构造更新类写入的 CAS 补偿记录。

    Args:
        snapshot: 写入前文档预镜像。
        written_document: 本次写入成功后返回或计算出的文档状态。

    Returns:
        仅允许从本次写后版本回滚的补偿记录。
    """
    return _CompensationRecord(
        snapshot=dict(snapshot),
        operation="updated",
        expected_after_version=int(written_document["version"]),
        expected_after_is_deleted=written_document["is_deleted"],
    )


def _deleted_compensation_record(snapshot: dict[str, Any]) -> _CompensationRecord:
    """构造物理删除写入的安全插回记录。

    Args:
        snapshot: 被本次物理删除的文档预镜像。

    Returns:
        仅允许在身份与业务键均未重建时插回的补偿记录。
    """
    return _CompensationRecord(snapshot=dict(snapshot), operation="deleted")


def _snapshot_version_query(document: Mapping[str, Any]) -> dict[str, Any]:
    """构造依赖文档预镜像对应的精确版本条件。

    Args:
        document: 写入前读取的关系或绑定文档。

    Returns:
        可用于检测并发修改的 MongoDB 查询片段。
    """
    return {"version": document["version"]}


def _normalized_blockers(document: Mapping[str, Any], field: str) -> list[str]:
    """读取并规范化自动阻断来源数组。

    Args:
        document: 关系或绑定预镜像。
        field: 需要读取的阻断来源字段。

    Returns:
        去空、去重并保持原顺序的业务 ID 数组。
    """
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        )
    )


def _has_any_automatic_blocker(
    document: Mapping[str, Any],
    character_blockers: Sequence[str],
) -> bool:
    """判断关系或绑定在移除当前角色来源后是否仍受自动阻断。

    Args:
        document: 关系或绑定预镜像。
        character_blockers: 本次计算后的角色阻断来源。

    Returns:
        存在任一角色或势力自动阻断来源时返回 True。
    """
    if character_blockers:
        return True
    return any(
        _normalized_blockers(document, field)
        for field in (
            "disabled_by_faction_ids",
            "disabled_by_faction_delete_ids",
        )
    )


async def _load_character_dependents(
    novel_id: str,
    character_id: str,
    *,
    include_deleted: bool,
    session: AsyncClientSession | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """读取角色参与的关系与势力绑定预镜像。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        include_deleted: 是否连同依赖对象回收站记录一起读取。
        session: 可选 MongoDB 会话。

    Returns:
        人物关系预镜像和势力绑定预镜像组成的二元组。
    """
    obj_id = to_object_id(novel_id)
    relations = await _character_relation_repo.find_many(
        {
            "novel_id": obj_id,
            "$or": [
                {"source_character_id": character_id},
                {"target_character_id": character_id},
            ],
        },
        include_deleted=include_deleted,
        session=session,
    )
    bindings = await _character_binding_repo.find_many(
        {"novel_id": obj_id, "character_id": character_id},
        include_deleted=include_deleted,
        session=session,
    )
    return relations, bindings


async def _apply_dependent_availability(
    repository: BaseRepository,
    snapshots: Sequence[dict[str, Any]],
    character_id: str,
    *,
    available: bool,
    applied_snapshots: list[_CompensationRecord],
    session: AsyncClientSession | None,
) -> int:
    """按用户意图和自动阻断来源派生依赖对象的有效状态。

    Args:
        repository: 人物关系或角色势力绑定基础仓储。
        snapshots: 本次操作前读取的依赖文档。
        character_id: 状态发生变化的角色业务 ID。
        available: 角色在操作后是否可作为有效端点。
        applied_snapshots: 用于记录已成功写入及其写后 CAS 状态的可变列表。
        session: 可选 MongoDB 会话。

    Returns:
        实际发生状态或来源更新的依赖文档数量。
    """
    updated_count = 0
    for snapshot in snapshots:
        if snapshot.get("is_deleted") is True:
            continue
        blockers = _normalized_blockers(snapshot, "disabled_by_character_ids")
        if available:
            next_blockers = [item for item in blockers if item != character_id]
        else:
            next_blockers = list(blockers)
            if character_id not in next_blockers:
                next_blockers.append(character_id)

        user_is_active = snapshot["user_is_active"]
        next_is_active = bool(
            user_is_active
            and not _has_any_automatic_blocker(snapshot, next_blockers)
        )
        if (
            blockers == next_blockers
            and snapshot.get("user_is_active") is user_is_active
            and snapshot.get("is_active") is next_is_active
        ):
            continue

        current_version = int(snapshot["version"])
        try:
            result = await repository.collection.update_one(
                {"_id": snapshot["_id"], **_snapshot_version_query(snapshot)},
                {
                    "$set": {
                        "user_is_active": user_is_active,
                        "disabled_by_character_ids": next_blockers,
                        "is_active": next_is_active,
                        "version": current_version + 1,
                        "updated_at": get_utc_now(),
                    }
                },
                session=session,
            )
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("角色恢复后依赖关系或绑定发生有效语义冲突") from exc
        if result.matched_count != 1:
            raise _DependencyReconcileCasMiss(
                "角色依赖对象已被其他请求修改，请重新读取后重试"
            )
        applied_snapshots.append(
            _updated_compensation_record(
                snapshot,
                {
                    "version": current_version + 1,
                    **(
                        {"is_deleted": bool(snapshot["is_deleted"])}
                        if "is_deleted" in snapshot
                        else {}
                    ),
                },
            )
        )
        updated_count += 1
    return updated_count


async def _apply_character_name_projection(
    snapshots: Sequence[dict[str, Any]],
    character_id: str,
    name: str,
    *,
    applied_snapshots: list[_CompensationRecord],
    session: AsyncClientSession | None,
) -> int:
    """同步角色关系中冗余保存的端点显示名称。

    Args:
        snapshots: 角色相关人物关系预镜像。
        character_id: 被改名的角色业务 ID。
        name: 新角色显示名。
        applied_snapshots: 用于记录已写入及其写后 CAS 状态的可变列表。
        session: 可选 MongoDB 会话。

    Returns:
        实际更新的人物关系数量。
    """
    updated_count = 0
    for snapshot in snapshots:
        updates: dict[str, Any] = {}
        if snapshot.get("source_character_id") == character_id:
            updates["source_character_name"] = name
        if snapshot.get("target_character_id") == character_id:
            updates["target_character_name"] = name
        if not updates or all(snapshot.get(key) == value for key, value in updates.items()):
            continue

        current_version = int(snapshot["version"])
        result = await _character_relation_repo.collection.update_one(
            {"_id": snapshot["_id"], **_snapshot_version_query(snapshot)},
            {
                "$set": {
                    **updates,
                    "version": current_version + 1,
                    "updated_at": get_utc_now(),
                }
            },
            session=session,
        )
        if result.matched_count != 1:
            raise _DependencyReconcileCasMiss(
                "角色关系已被其他请求修改，请重新读取后重试"
            )
        applied_snapshots.append(
            _updated_compensation_record(
                snapshot,
                {
                    "version": current_version + 1,
                    **(
                        {"is_deleted": bool(snapshot["is_deleted"])}
                        if "is_deleted" in snapshot
                        else {}
                    ),
                },
            )
        )
        updated_count += 1
    return updated_count


def _snapshot_business_identity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """提取跨集合补偿必须同时匹配的小说与稳定业务身份。

    Args:
        snapshot: 写入前读取的主档、关系或绑定预镜像。

    Returns:
        包含 ``novel_id`` 与当前集合稳定业务 ID 的精确查询片段。

    Raises:
        RuntimeError: 预镜像缺少小说 ID 或受支持的稳定业务 ID。
    """
    if snapshot.get("novel_id") is None:
        raise RuntimeError("standalone 补偿缺少 novel_id，拒绝修改文档")
    for business_key in (
        "relation_id",
        "binding_id",
        "character_id",
        "faction_id",
    ):
        if snapshot.get(business_key) is not None:
            return {
                "novel_id": snapshot["novel_id"],
                business_key: snapshot[business_key],
            }
    raise RuntimeError("standalone 补偿缺少可验证的稳定业务 ID，拒绝修改文档")


async def _restore_snapshots(
    repository: BaseRepository,
    records: Sequence[_CompensationRecord],
) -> None:
    """通过 CAS 回滚更新，或在身份未重建时插回硬删预镜像。

    Args:
        repository: 需要执行补偿的集合仓储。
        records: 携带写后状态的更新或物理删除补偿记录。

    Returns:
        无。
    """
    for record in reversed(list(records)):
        snapshot = record.snapshot
        business_query = _snapshot_business_identity(snapshot)
        if record.operation == "updated":
            # 只回滚仍精确停留在本次公开写后状态的同一业务实体；内部 guard 不参与主档 CAS。
            deletion_query: object = record.expected_after_is_deleted
            restore_fields = {
                field: value
                for field, value in snapshot.items()
                if field not in {"_id", DEPENDENCY_GUARD_FIELD}
            }
            cas_query = {
                "_id": snapshot["_id"],
                **business_query,
                "version": record.expected_after_version,
                "is_deleted": deletion_query,
            }
            current = await repository.collection.find_one(cas_query)
            if current is None:
                raise RuntimeError(
                    "standalone 更新补偿 CAS 失败：文档已被并发修改，未执行覆盖"
                )
            # 清除本次写新增而预镜像不存在的公开字段，但始终保留当前内部 contribution counter。
            unset_fields = {
                field: ""
                for field in current
                if field not in snapshot
                and field not in {"_id", DEPENDENCY_GUARD_FIELD}
            }
            restore_update: dict[str, Any] = {"$set": restore_fields}
            if unset_fields:
                restore_update["$unset"] = unset_fields
            try:
                result = await repository.collection.update_one(
                    cas_query,
                    restore_update,
                )
            except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
                raise RuntimeError("standalone 更新补偿发生唯一键冲突，未覆盖并发数据") from exc
            if result.matched_count != 1:
                raise RuntimeError(
                    "standalone 更新补偿 CAS 失败：文档已被并发修改，未执行覆盖"
                )
            continue

        # 预检 _id 和全历史业务键；任一身份已被重建都必须失败，不能 replace 或 upsert。
        conflict = await repository.collection.find_one(
            {"$or": [{"_id": snapshot["_id"]}, business_query]},
            projection={"_id": 1},
        )
        if conflict is not None:
            raise RuntimeError(
                "standalone 硬删补偿冲突：文档身份或业务键已被并发重建，未执行覆盖"
            )
        try:
            await repository.collection.insert_one(dict(snapshot))
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            # 预检与插入之间仍可能发生竞态，依赖唯一索引把竞态收敛为明确补偿失败。
            raise RuntimeError(
                "standalone 硬删补偿插回时发生并发唯一键冲突，未执行覆盖"
            ) from exc


async def _delete_snapshots_exact(
    repository: BaseRepository,
    snapshots: Sequence[dict[str, Any]],
    *,
    deleted_snapshots: list[_CompensationRecord],
    session: AsyncClientSession | None,
) -> int:
    """按预镜像版本逐条物理删除依赖文档。

    Args:
        repository: 人物关系或角色势力绑定仓储。
        snapshots: 待删除文档预镜像。
        deleted_snapshots: 记录已删除文档安全插回条件的可变列表。
        session: 可选 MongoDB 会话。

    Returns:
        实际删除的文档数量。
    """
    for snapshot in snapshots:
        result = await repository.collection.delete_one(
            {"_id": snapshot["_id"], **_snapshot_version_query(snapshot)},
            session=session,
        )
        if result.deleted_count != 1:
            raise DuplicateKeyError("角色依赖对象已被其他请求修改，请刷新后重试")
        deleted_snapshots.append(_deleted_compensation_record(snapshot))
    return len(snapshots)


async def _reconcile_character_dependents(
    character: Mapping[str, Any],
) -> None:
    """按当前角色主档重扫并调和全部晚到人物关系和势力绑定。

    Args:
        character: 已确认保留或恢复的当前角色主档。

    Returns:
        无。
    """
    novel_id = str(character["novel_id"])
    character_id = str(character["character_id"])
    relation_available = bool(
        character.get("is_deleted") is not True
        and character.get("status") == "active"
    )
    # 势力绑定仍只属于核心角色；人工人物关系则允许任意活动角色参与。
    binding_available = bool(
        relation_available and character.get("is_core_character") is True
    )
    projected_name = str(character.get("name") or "").strip()

    async def _reconcile_once() -> None:
        """重新读取当前全部角色依赖并执行一轮版本化调和。"""
        latest_relations, latest_bindings = await _load_character_dependents(
            novel_id,
            character_id,
            include_deleted=False,
            session=None,
        )
        # 每轮均使用最新依赖版本；CAS miss 由外层统一触发下一轮重读。
        await _apply_dependent_availability(
            _character_relation_repo,
            latest_relations,
            character_id,
            available=relation_available,
            applied_snapshots=[],
            session=None,
        )
        await _apply_dependent_availability(
            _character_binding_repo,
            latest_bindings,
            character_id,
            available=binding_available,
            applied_snapshots=[],
            session=None,
        )
        if projected_name:
            all_relations, _ = await _load_character_dependents(
                novel_id,
                character_id,
                include_deleted=True,
                session=None,
            )
            await _apply_character_name_projection(
                all_relations,
                character_id,
                projected_name,
                applied_snapshots=[],
                session=None,
            )

    await _run_bounded_dependency_reconcile(
        _reconcile_once,
        label="角色依赖调和",
    )


async def _compensate_character_write(
    character_record: _CompensationRecord | None,
    relation_records: Sequence[_CompensationRecord],
    binding_records: Sequence[_CompensationRecord],
) -> None:
    """恢复角色生命周期跨集合顺序写的全部已应用预镜像。

    Args:
        character_record: 角色写入记录；角色尚未写入时为 None。
        relation_records: 已修改或删除的人物关系补偿记录。
        binding_records: 已修改或删除的势力绑定补偿记录。

    Returns:
        无。
    """
    if character_record is None:
        await _restore_snapshots(_character_relation_repo, relation_records)
        await _restore_snapshots(_character_binding_repo, binding_records)
        return

    try:
        await _restore_snapshots(character_repo, [character_record])
    except Exception as master_exc:
        # 公开版本已经推进时绝不覆盖较新主档；依赖必须改以当前主档为真相重新调和。
        current = await character_repo.collection.find_one(
            {
                "_id": character_record.snapshot["_id"],
                **_snapshot_business_identity(character_record.snapshot),
            }
        )
        if current is not None:
            await _reconcile_character_dependents(current)
            raise RuntimeError(
                "standalone 角色主档补偿未完成：公开版本或删除态已推进；"
                "已保留较新主档并按当前状态调和依赖"
            ) from master_exc
        raise RuntimeError(
            "standalone 角色主档补偿未完成：原业务身份已不存在或被重建"
        ) from master_exc

    dependency_error: Exception | None = None
    try:
        await _restore_snapshots(_character_relation_repo, relation_records)
        await _restore_snapshots(_character_binding_repo, binding_records)
    except Exception as exc:
        dependency_error = exc

    # 主档回滚后无论旧依赖预镜像是否全部命中，都以恢复后的主档重扫晚到依赖。
    await _reconcile_character_dependents(character_record.snapshot)
    if dependency_error is not None:
        raise RuntimeError(
            "standalone 角色依赖预镜像补偿未完整命中；已按恢复后的主档调和最新依赖"
        ) from dependency_error


async def _get_versioned_character(
    novel_id: str,
    character_id: str,
    expected_version: int,
    *,
    deleted: bool,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """读取指定生命周期状态的角色并校验乐观锁版本。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        expected_version: 客户端基于的角色版本。
        deleted: True 时只读取回收站，否则只读取活动集合视图。
        session: 可选 MongoDB 会话。

    Returns:
        版本匹配的角色预镜像。
    """
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise ValueError("expected_version 必须为正整数")
    if expected_version < 1:
        raise ValueError("expected_version 必须大于等于 1")
    if deleted:
        character = await character_repo.get_deleted_character(
            novel_id,
            character_id,
            session=session,
        )
    else:
        character = await character_repo.get_character(
            novel_id,
            character_id,
            session=session,
        )
    current_version = int(character["version"])
    if current_version != expected_version:
        raise DuplicateKeyError(
            f"角色版本冲突：当前版本为 {current_version}，请求版本为 {expected_version}"
        )
    return character


def _to_plain_dict(value: Any) -> dict[str, Any]:
    """将请求模型或映射转换为普通字典。

    Args:
        value: Pydantic 模型或字典类对象。

    Returns:
        可由领域服务安全复制和过滤的普通字典。
    """
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(exclude_unset=True))
    raise TypeError("角色数据必须是映射或 Pydantic 模型")


def _build_character_document(
    source: Mapping[str, Any],
    *,
    novel_id: str,
    character_id: str,
    sort_order: int,
    is_core_character: bool,
) -> dict[str, Any]:
    """构造只包含角色主档白名单字段的数据库文档。

    Args:
        source: 已通过请求或生成结果 Schema 校验的角色业务字段。
        novel_id: 小说 ObjectId 字符串。
        character_id: 服务端分配的稳定角色业务 ID。
        sort_order: 服务端确定的非负排序权重。
        is_core_character: 是否属于全书级核心角色。

    Returns:
        可直接交给 CharacterRepository 写入的角色文档。
    """
    display_name, normalized_name = normalize_character_name(str(source.get("name") or ""))
    document: dict[str, Any] = {
        "novel_id": novel_id,
        "character_id": character_id,
        "name": display_name,
        "normalized_name": normalized_name,
    }

    for field in _LIST_FIELDS:
        raw_value = source.get(field)
        document[field] = list(raw_value) if isinstance(raw_value, (list, tuple)) else []
    for field, default_value in _TEXT_DEFAULTS.items():
        document[field] = str(source.get(field, default_value) or default_value).strip()

    document.update(
        {
            "sort_order": max(0, int(sort_order)),
            "extra": dict(source.get("extra") or {}),
            "status": "active",
            "is_core_character": is_core_character,
            # 全书角色初始化早于结构规划，首次出场引用必须保持为空。
            "first_appearance_volume_id": None,
            "first_appearance_chapter_id": None,
            "version": 1,
            "dependency_guard_revision": 0,
            "is_deleted": False,
            "deleted_at": None,
            "deletion_sources": [],
        }
    )
    return document


class CharacterService:
    """编排角色主档校验、业务 ID 分配和批量生成写入。"""

    @staticmethod
    async def create_character(
        novel_id: str,
        data: Any,
        *,
        idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """回放旧人工创建的成功结果；新建需确认人物资料起点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 已通过 CharacterCreateRequestV1 校验的请求模型或映射。
            idempotency_key: 调用方提供的创建幂等键。
            session: 可选外层事务，用于读取原创建结果。

        Returns:
            已创建的角色 BSON 文档。
        """
        source = _to_plain_dict(data)
        # 核心身份是创建时的一次性决策；显式 false 与省略默认值具有相同幂等语义。
        raw_core_flag = source.get("is_core_character", False)
        if not isinstance(raw_core_flag, bool):
            raise ValueError("is_core_character 必须为布尔值")
        source["is_core_character"] = raw_core_flag
        key_hash = hash_idempotency_key(idempotency_key)
        # 沿用原创建的 exclude_unset 规范载荷，不改成功请求的摘要。
        request_hash = checksum({"novel_id": novel_id, "payload": source})
        existing = await character_repo.find_by_creation_idempotency(
            novel_id, key_hash, session=session,
        )
        if existing is not None:
            if existing["creation_request_hash"] != request_hash:
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的角色创建请求",
                    status_code=409,
                )
            return existing
        raise DomainApiError(
            "CHARACTER_FACT_CONTRACT_REQUIRED",
            "新建人物需要先预览并确认人物资料的起点",
            status_code=409,
        )

    @staticmethod
    async def get_character(
        novel_id: str,
        character_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """获取小说内单个未删除角色。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 小说内稳定角色业务 ID。
            session: 可选 MongoDB 会话，用于上层聚合读取。

        Returns:
            匹配的角色 BSON 文档。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_repo.get_character(novel_id, character_id, session=session)

    @staticmethod
    async def get_characters_by_novel(
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """获取小说内全部未删除角色。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，用于上层聚合读取。

        Returns:
            按排序权重和业务 ID 稳定排序的角色文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_repo.get_characters_by_novel(novel_id, session=session)

    @staticmethod
    async def count_active_protagonists(
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """返回小说当前可用于初始化门禁的活动主角数量。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，供 readiness 聚合复用。

        Returns:
            活动、未删除主角的数量；允许大于一。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_repo.count_active_protagonists(
            novel_id,
            session=session,
        )

    @staticmethod
    async def get_characters_by_ids(
        novel_id: str,
        character_ids: Sequence[str],
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按输入顺序批量解析小说内角色。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_ids: 待解析的稳定角色业务 ID 序列。
            session: 可选 MongoDB 会话，用于上层聚合读取。

        Returns:
            已找到的角色 BSON 文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_repo.get_characters_by_ids(
            novel_id,
            character_ids,
            session=session,
        )

    @staticmethod
    async def get_deleted_characters_by_novel(
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """获取小说角色回收站列表。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            已软删除角色文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_repo.get_deleted_characters_by_novel(
            novel_id,
            session=session,
        )

    @staticmethod
    async def update_character(novel_id: str, character_id: str, data: Any, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """使用 CAS 更新角色档案并同步关系端点名称投影。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            data: 含 expected_version 的严格角色更新请求。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            更新后的完整角色文档。
        """
        source = _to_plain_dict(data)
        expected_version = source.pop("expected_version", None)
        if expected_version is None:
            raise ValueError("角色更新必须提供 expected_version")
        update_data = {
            key: value for key, value in source.items() if key in CHARACTER_EDITABLE_FIELDS
        }
        if not update_data:
            raise ValueError("角色更新至少需要提供一个可编辑字段")

        async def _update(session: AsyncClientSession | None) -> dict[str, Any]:
            """在同一写入单元更新角色并维护关系名称投影。"""
            if session is None or not session.in_transaction:
                raise TransactionNotSupportedError("人物档案更新必须使用事务")
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await _get_versioned_character(
                novel_id,
                character_id,
                expected_version,
                deleted=False,
                session=session,
            )
            from backend.services.novel.character_fact_contract import CHARACTER_FACT_FIELDS
            from backend.services.novel.character_fact_service import ensure_character_fields_unmanaged

            try:
                await ensure_character_fields_unmanaged(
                    novel_id, [character_id], sorted(source.keys() & CHARACTER_FACT_FIELDS), session=session,
                )
            except OperationFailure as exc:
                if exc.code != 112 or not exc.has_error_label("TransientTransactionError"):
                    raise
                raise DuplicateKeyError("角色版本已变化，请刷新后重试") from exc
            next_data = dict(update_data)
            name_changed = False
            if "name" in next_data:
                display_name, normalized_name = normalize_character_name(
                    str(next_data["name"])
                )
                existing = await character_repo.get_active_by_normalized_name(
                    novel_id,
                    normalized_name,
                    session=session,
                )
                if existing is not None and existing.get("character_id") != character_id:
                    raise DuplicateKeyError(f"同一小说下已存在活动角色: {display_name}")
                next_data["name"] = display_name
                next_data["normalized_name"] = normalized_name
                name_changed = display_name != current.get("name")

            relation_snapshots: list[dict[str, Any]] = []
            if name_changed:
                relation_snapshots, _ = await _load_character_dependents(
                    novel_id,
                    character_id,
                    # 回收站关系也保留端点显示名投影，恢复后无需额外修复陈旧名称。
                    include_deleted=True,
                    session=session,
                )
            applied_relations: list[_CompensationRecord] = []
            character_record: _CompensationRecord | None = None
            try:
                updated = await character_repo.update_character(
                    novel_id,
                    character_id,
                    next_data,
                    expected_version=expected_version,
                    session=session,
                )
                if updated is None:
                    raise DuplicateKeyError("角色版本已变化，请刷新后重试")
                character_record = _updated_compensation_record(current, updated)
                if name_changed:
                    await _apply_character_name_projection(
                        relation_snapshots,
                        character_id,
                        str(updated["name"]),
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    # 主档改名后再次扫描，覆盖首次快照之后才创建的关系投影。
                    latest_relations, _ = await _load_character_dependents(
                        novel_id,
                        character_id,
                        include_deleted=True,
                        session=session,
                    )
                    await _apply_character_name_projection(
                        latest_relations,
                        character_id,
                        str(updated["name"]),
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                return updated
            except Exception:
                if session is None and character_record is not None:
                    try:
                        await _compensate_character_write(
                            character_record,
                            applied_relations,
                            [],
                        )
                    except Exception as compensation_exc:
                        logger.exception("角色档案更新失败且预镜像补偿失败")
                        raise RuntimeError("角色档案更新失败，且 standalone 补偿未完成") from compensation_exc
                raise

        if session is not None:
            return await _update(session)

        return await run_mongo_write_unit(_update, "update_character", require_transaction=True)

    @staticmethod
    async def update_character_status(novel_id: str, character_id: str, status: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """切换角色状态并维护人物关系与势力绑定有效态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            status: active 或 inactive。
            expected_version: 客户端基于的角色版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            状态更新后的完整角色文档。
        """
        if status not in {"active", "inactive"}:
            raise ValueError("角色 status 只能是 active 或 inactive")

        async def _update(session: AsyncClientSession | None) -> dict[str, Any]:
            """在同一写入单元切换角色及其依赖有效态。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                current = await _get_versioned_character(
                    novel_id,
                    character_id,
                    expected_version,
                    deleted=False,
                    session=session,
                )
                relation_snapshots, binding_snapshots = await _load_character_dependents(
                    novel_id,
                    character_id,
                    include_deleted=False,
                    session=session,
                )
                if status == "inactive":
                    await CharacterVolumeStateService.ensure_relations_can_be_disabled(
                        novel_id,
                        [
                            str(relation["relation_id"])
                            for relation in relation_snapshots
                        ],
                        session=session,
                    )
                applied_relations: list[_CompensationRecord] = []
                applied_bindings: list[_CompensationRecord] = []
                character_record: _CompensationRecord | None = None
                try:
                    updated = await character_repo.update_character_status(
                        novel_id,
                        character_id,
                        status,
                        expected_version=expected_version,
                        session=session,
                    )
                    if updated is None:
                        raise DuplicateKeyError("角色版本已变化，请刷新后重试")
                    character_record = _updated_compensation_record(current, updated)
                    available = status == "active"
                    await _apply_dependent_availability(
                        _character_relation_repo,
                        relation_snapshots,
                        character_id,
                        available=available,
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_binding_repo,
                        binding_snapshots,
                        character_id,
                        available=available,
                        applied_snapshots=applied_bindings,
                        session=session,
                    )
                    # 主档 CAS 后二次扫描，消除首次快照与状态写入之间插入的活动依赖。
                    latest_relations, latest_bindings = await _load_character_dependents(
                        novel_id,
                        character_id,
                        include_deleted=False,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_relation_repo,
                        latest_relations,
                        character_id,
                        available=available,
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_binding_repo,
                        latest_bindings,
                        character_id,
                        available=available,
                        applied_snapshots=applied_bindings,
                        session=session,
                    )
                    return updated
                except Exception as exc:
                    if isinstance(exc, StateSourceCompensationError):
                        state_lock_releasable = False
                    if session is None and character_record is not None:
                        try:
                            await _compensate_character_write(
                                character_record,
                                applied_relations,
                                applied_bindings,
                            )
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            logger.exception("角色状态切换失败且预镜像补偿失败")
                            raise RuntimeError(
                                "角色状态切换失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        if session is not None:
            return await _update(session)

        return await run_mongo_write_unit(_update, "update_character_status")

    @staticmethod
    async def soft_delete_character(novel_id: str, character_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """软删除角色并自动阻断其人物关系与势力绑定。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            expected_version: 客户端基于的角色版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已进入回收站的完整角色文档。
        """

        async def _delete(session: AsyncClientSession | None) -> dict[str, Any]:
            """在同一写入单元软删除角色并阻断依赖对象。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                current = await _get_versioned_character(
                    novel_id,
                    character_id,
                    expected_version,
                    deleted=False,
                    session=session,
                )
                relation_snapshots, binding_snapshots = await _load_character_dependents(
                    novel_id,
                    character_id,
                    include_deleted=False,
                    session=session,
                )
                await CharacterVolumeStateService.ensure_relations_can_be_disabled(
                    novel_id,
                    [str(relation["relation_id"]) for relation in relation_snapshots],
                    session=session,
                )
                applied_relations: list[_CompensationRecord] = []
                applied_bindings: list[_CompensationRecord] = []
                state_changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                character_record: _CompensationRecord | None = None
                try:
                    deleted = await character_repo.soft_delete_character(
                        novel_id,
                        character_id,
                        expected_version=expected_version,
                        session=session,
                    )
                    if deleted is None:
                        raise DuplicateKeyError("角色版本已变化，请刷新后重试")
                    character_record = _updated_compensation_record(current, deleted)
                    await _apply_dependent_availability(
                        _character_relation_repo,
                        relation_snapshots,
                        character_id,
                        available=False,
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_binding_repo,
                        binding_snapshots,
                        character_id,
                        available=False,
                        applied_snapshots=applied_bindings,
                        session=session,
                    )
                    latest_relations, latest_bindings = await _load_character_dependents(
                        novel_id,
                        character_id,
                        include_deleted=False,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_relation_repo,
                        latest_relations,
                        character_id,
                        available=False,
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_binding_repo,
                        latest_bindings,
                        character_id,
                        available=False,
                        applied_snapshots=applied_bindings,
                        session=session,
                    )
                    state_changes = (
                        await CharacterVolumeStateService.add_character_deletion_source(
                            novel_id,
                            character_id,
                            session=session,
                        )
                    )
                    return deleted
                except Exception as exc:
                    if isinstance(exc, StateSourceCompensationError):
                        state_lock_releasable = False
                    if session is None and character_record is not None:
                        try:
                            if state_changes:
                                await compensate_state_changes(state_changes)
                            await _compensate_character_write(
                                character_record,
                                applied_relations,
                                applied_bindings,
                            )
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            logger.exception("角色软删除失败且预镜像补偿失败")
                            raise RuntimeError(
                                "角色软删除失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        if session is not None:
            return await _delete(session)

        return await run_mongo_write_unit(_delete, "soft_delete_character")

    @staticmethod
    async def restore_character(novel_id: str, character_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """恢复回收站角色并按用户意图重新计算依赖有效态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            expected_version: 客户端基于的角色版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            恢复后的完整角色文档。
        """

        async def _restore(session: AsyncClientSession | None) -> dict[str, Any]:
            """在同一写入单元恢复角色并清理对应自动阻断来源。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                current = await _get_versioned_character(
                    novel_id,
                    character_id,
                    expected_version,
                    deleted=True,
                    session=session,
                )
                existing = await character_repo.get_active_by_normalized_name(
                    novel_id,
                    current["normalized_name"],
                    session=session,
                )
                if existing is not None:
                    raise DuplicateKeyError(
                        f"同一小说下已存在活动角色: {current.get('name', character_id)}"
                    )
                relation_snapshots, binding_snapshots = await _load_character_dependents(
                    novel_id,
                    character_id,
                    include_deleted=False,
                    session=session,
                )
                applied_relations: list[_CompensationRecord] = []
                applied_bindings: list[_CompensationRecord] = []
                state_changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                character_record: _CompensationRecord | None = None
                try:
                    restored = await character_repo.restore_character(
                        novel_id,
                        character_id,
                        expected_version=expected_version,
                        session=session,
                    )
                    if restored is None:
                        raise DuplicateKeyError("角色版本已变化，请刷新后重试")
                    character_record = _updated_compensation_record(current, restored)
                    available = restored.get("status", "active") == "active"
                    await _apply_dependent_availability(
                        _character_relation_repo,
                        relation_snapshots,
                        character_id,
                        available=available,
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_binding_repo,
                        binding_snapshots,
                        character_id,
                        available=available,
                        applied_snapshots=applied_bindings,
                        session=session,
                    )
                    latest_relations, latest_bindings = await _load_character_dependents(
                        novel_id,
                        character_id,
                        include_deleted=False,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_relation_repo,
                        latest_relations,
                        character_id,
                        available=available,
                        applied_snapshots=applied_relations,
                        session=session,
                    )
                    await _apply_dependent_availability(
                        _character_binding_repo,
                        latest_bindings,
                        character_id,
                        available=available,
                        applied_snapshots=applied_bindings,
                        session=session,
                    )
                    state_changes = await (
                        CharacterVolumeStateService.remove_character_deletion_source(
                            novel_id,
                            character_id,
                            session=session,
                        )
                    )
                    return restored
                except Exception as exc:
                    if isinstance(exc, StateSourceCompensationError):
                        state_lock_releasable = False
                    if session is None and character_record is not None:
                        try:
                            if state_changes:
                                await compensate_state_changes(state_changes)
                            await _compensate_character_write(
                                character_record,
                                applied_relations,
                                applied_bindings,
                            )
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            logger.exception("角色恢复失败且预镜像补偿失败")
                            raise RuntimeError(
                                "角色恢复失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        if session is not None:
            return await _restore(session)

        return await run_mongo_write_unit(_restore, "restore_character")

    @staticmethod
    async def hard_delete_character(
        novel_id: str,
        character_id: str,
        *,
        expected_version: int,
    ) -> dict[str, int]:
        """物理删除回收站角色及其全部人物关系和势力绑定。

        Args:
            novel_id: 小说 ObjectId 字符串。
            character_id: 稳定角色业务 ID。
            expected_version: 客户端基于的角色版本。

        Returns:
            角色、人物关系和势力绑定的精确删除计数。
        """

        async def _delete(session: AsyncClientSession | None) -> dict[str, int]:
            """在同一写入单元按预镜像版本逐条硬删除角色依赖。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                item_lock = await acquire_item_write_lock(novel_id, session=session)
                item_lock_releasable = True
                try:
                    current = await _get_versioned_character(
                        novel_id,
                        character_id,
                        expected_version,
                        deleted=True,
                        session=session,
                    )
                    # 回收站篇章仍可恢复，必须保留它引用的角色。
                    referencing_arcs = await BaseRepository("arcs").find_many(
                        {
                            "novel_id": to_object_id(novel_id),
                            "planning.character_ids": character_id,
                        },
                        include_deleted=True,
                        sort=[("_id", 1)],
                        session=session,
                    )
                    if referencing_arcs:
                        arc_ids = [str(arc["_id"]) for arc in referencing_arcs]
                        raise DomainApiError(
                            "ARC_CHARACTER_REFERENCE_PROTECTED",
                            "角色仍被篇章引用，请先移除引用再永久删除",
                            status_code=409,
                            details={"arc_ids": arc_ids, "count": len(arc_ids)},
                        )
                    # 场景中的角色和章节视角也包含回收站，恢复时仍需要原对象。
                    for collection, field in (
                        ("scenes", "planning.character_ids"),
                        ("chapters", "planning.pov_character_id"),
                    ):
                        references = await BaseRepository(collection).find_many(
                            {"novel_id": to_object_id(novel_id), field: character_id},
                            include_deleted=True, sort=[("_id", 1)], session=session,
                        )
                        if references:
                            raise DomainApiError(
                                f"{collection[:-1].upper()}_CHARACTER_REFERENCE_PROTECTED",
                                "角色仍被场景或章节引用，请先移除引用再永久删除",
                                status_code=409,
                                details={f"{collection[:-1]}_ids": [str(item["_id"]) for item in references], "count": len(references)},
                            )
                    state_references = await BaseRepository(
                        "character_volume_states"
                    ).find_many(
                        {
                            "novel_id": to_object_id(novel_id),
                            "character_id": character_id,
                        },
                        include_deleted=True,
                        sort=[("state_id", 1)],
                        session=session,
                    )
                    if state_references:
                        raise DomainApiError(
                            "CHARACTER_VOLUME_STATE_REFERENCE_PROTECTED",
                            "角色仍有卷级状态记录，不能永久删除",
                            status_code=409,
                            details={
                                "state_ids": [
                                    str(state["state_id"]) for state in state_references
                                ],
                                "count": len(state_references),
                            },
                        )
                    pending_item_references = await BaseRepository(
                        "items"
                    ).count_documents(
                        {
                            "novel_id": to_object_id(novel_id),
                            "owner_character_id": character_id,
                            "item_write_pending_token": {"$type": "string"},
                        },
                        session=session,
                    )
                    if pending_item_references:
                        raise DomainApiError(
                            "CHARACTER_ITEM_WRITE_CONFLICT",
                            "物品写入正在使用该角色，请稍后重试",
                            status_code=409,
                        )
                    referencing_items = await BaseRepository("items").find_many(
                        {
                            "novel_id": to_object_id(novel_id),
                            "owner_character_id": character_id,
                            "item_write_pending_token": None,
                        },
                        sort=[("item_id", 1)],
                        session=session,
                    )
                    if referencing_items:
                        item_ids = [str(item["item_id"]) for item in referencing_items]
                        raise DomainApiError(
                            "CHARACTER_ITEM_REFERENCE_PROTECTED",
                            "角色仍被正式物品引用，不能永久删除",
                            status_code=409,
                            details={"item_ids": item_ids, "count": len(item_ids)},
                        )
                    relation_snapshots, binding_snapshots = await _load_character_dependents(
                        novel_id,
                        character_id,
                        include_deleted=True,
                        session=session,
                    )
                    relation_ids = [
                        str(relation["relation_id"])
                        for relation in relation_snapshots
                    ]
                    if relation_ids:
                        focus_references = await BaseRepository(
                            "character_volume_states"
                        ).find_many(
                            {
                                "novel_id": to_object_id(novel_id),
                                "relationship_focus_ids": {"$in": relation_ids},
                            },
                            include_deleted=True,
                            sort=[("state_id", 1)],
                            session=session,
                        )
                        if focus_references:
                            raise DomainApiError(
                                "CHARACTER_RELATION_STATE_REFERENCE_PROTECTED",
                                "角色关系仍被卷级状态引用，不能随角色永久删除",
                                status_code=409,
                                details={
                                    "state_ids": [
                                        str(state["state_id"])
                                        for state in focus_references
                                    ],
                                    "count": len(focus_references),
                                },
                            )
                    deleted_relations: list[_CompensationRecord] = []
                    deleted_bindings: list[_CompensationRecord] = []
                    character_record: _CompensationRecord | None = None
                    try:
                        relations_deleted = await _delete_snapshots_exact(
                            _character_relation_repo,
                            relation_snapshots,
                            deleted_snapshots=deleted_relations,
                            session=session,
                        )
                        bindings_deleted = await _delete_snapshots_exact(
                            _character_binding_repo,
                            binding_snapshots,
                            deleted_snapshots=deleted_bindings,
                            session=session,
                        )
                        deleted_character = await character_repo.hard_delete_character(
                            novel_id,
                            character_id,
                            expected_version=expected_version,
                            session=session,
                        )
                        if deleted_character is None:
                            raise DuplicateKeyError("角色版本已变化，请刷新后重试")
                        character_record = _deleted_compensation_record(current)
                        return {
                            "character_deleted": 1,
                            "relations_deleted": relations_deleted,
                            "bindings_deleted": bindings_deleted,
                        }
                    except Exception:
                        if session is None and (
                            character_record is not None
                            or deleted_relations
                            or deleted_bindings
                        ):
                            try:
                                await _compensate_character_write(
                                    character_record,
                                    deleted_relations,
                                    deleted_bindings,
                                )
                            except Exception as compensation_exc:
                                item_lock_releasable = False
                                state_lock_releasable = False
                                logger.exception("角色硬删除失败且预镜像补偿失败")
                                raise RuntimeError(
                                    "角色硬删除失败，且 standalone 补偿未完成"
                                ) from compensation_exc
                        raise
                finally:
                    if item_lock_releasable:
                        await release_item_write_lock(
                            novel_id,
                            item_lock,
                            session=session,
                        )
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        return await run_mongo_write_unit(_delete, "hard_delete_character")

    @staticmethod
    async def bulk_create_core_with_bindings(
        novel_id: str,
        result: Any,
        *,
        idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """回放完整旧批次；新批次及旧部分批次需另行确认人物资料起点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            result: 已通过严格 AI 确认 Schema 校验的请求。
            idempotency_key: 调用方提交的确认幂等键。
            session: 可选外层事务，用于读取原批次结果。

        Returns:
            所选角色的稳定 ref 映射、正式角色与非空绑定。
        """
        source = CoreCharactersAIConfirmationRequestV1.model_validate(
            _to_plain_dict(result)
        ).model_dump(mode="json")
        if source.get("request_type") != "ai_confirmation":
            raise ValueError("核心角色批量接口只接受严格 AI 确认请求")
        candidate = dict(source.get("candidate") or {})
        selected_refs = list(source.get("selected_character_refs") or [])
        bindings_by_ref = {
            str(item["character_ref"]): dict(item)
            for item in candidate.get("binding_candidates") or []
        }
        selected_binding_refs = [
            ref for ref in selected_refs
            if bindings_by_ref[ref].get("faction_id") is not None
        ]

        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "request": source})

        async def _load_existing(
            active_session: AsyncClientSession | None,
        ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
            """读取并校验同键已写入的角色和绑定 local ref。"""
            existing_characters = await character_repo.find_by_core_batch_idempotency(
                novel_id,
                key_hash,
                session=active_session,
            )
            existing_bindings = (
                await character_faction_binding_repo.find_by_core_batch_idempotency(
                    novel_id,
                    key_hash,
                    session=active_session,
                )
            )
            all_documents = [*existing_characters, *existing_bindings]
            if any(
                item.get("core_batch_request_hash") != request_hash
                for item in all_documents
            ):
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的核心角色确认请求",
                    status_code=409,
                )
            characters_by_ref = {
                str(item.get("core_batch_local_ref")): item
                for item in existing_characters
                if item.get("core_batch_local_ref")
            }
            bindings_by_local_ref = {
                str(item.get("core_batch_local_ref")): item
                for item in existing_bindings
                if item.get("core_batch_local_ref")
            }
            if (
                len(characters_by_ref) != len(existing_characters)
                or len(bindings_by_local_ref) != len(existing_bindings)
                or set(characters_by_ref) - set(selected_refs)
                or set(bindings_by_local_ref) - set(selected_binding_refs)
            ):
                raise DuplicateKeyError("核心角色确认批次 local ref 元数据冲突")
            for ref, binding in bindings_by_local_ref.items():
                character = characters_by_ref.get(ref)
                if (
                    character is None
                    or binding.get("character_id") != character.get("character_id")
                ):
                    raise DuplicateKeyError("核心角色确认批次绑定映射冲突")
            return characters_by_ref, bindings_by_local_ref

        characters_by_ref, bindings_by_local_ref = await _load_existing(session)
        if (
            set(characters_by_ref) == set(selected_refs)
            and set(bindings_by_local_ref) == set(selected_binding_refs)
        ):
            return {
                "character_ref_map": {
                    ref: str(characters_by_ref[ref]["character_id"])
                    for ref in selected_refs
                },
                "characters": [characters_by_ref[ref] for ref in selected_refs],
                "character_faction_bindings": [
                    bindings_by_local_ref[ref] for ref in selected_binding_refs
                ],
            }
        # 旧批次只写了一部分时不能续写或借原键改成人物事实确认。
        raise DomainApiError(
            "CHARACTER_FACT_CONTRACT_REQUIRED",
            "新建人物需要先预览并确认人物资料的起点；旧批次未完整成功，不能继续写入",
            status_code=409,
        )
