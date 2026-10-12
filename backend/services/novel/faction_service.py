import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError, DuplicateKeyError as PyMongoDuplicateKeyError

from backend.api.error_protocol import DomainApiError
from backend.db.endpoint_guard import DEPENDENCY_GUARD_FIELD
from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.repositories.character_faction_binding_repository import (
    character_faction_binding_repo,
)
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo, normalize_faction_name
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.llm.exceptions import LLMSchemaError
from backend.llm.schemas.novel_pydantic import (
    CORE_FACTIONS_RESULT_SCHEMA_ID,
    CORE_FACTIONS_RESULT_SCHEMA_VERSION,
    CoreFactionsResultSchema,
    GenerateCoreFactionsRequestV2,
)
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.llm.faction_generation_contract import (
    CORE_FACTIONS_STEP,
    CORE_FACTIONS_WORKFLOW,
    compute_core_factions_input_fingerprint,
)
from backend.services.novel.character_service import (
    _CompensationRecord,
    _DependencyReconcileCasMiss,
    _delete_snapshots_exact,
    _deleted_compensation_record,
    _normalized_blockers,
    _restore_snapshots,
    _run_bounded_dependency_reconcile,
    _snapshot_version_query,
    _updated_compensation_record,
)
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import (
    checksum,
    hash_idempotency_key,
)
from backend.services.novel.faction_relation_service import FactionRelationService
from backend.services.novel.character_volume_state_service import (
    acquire_state_write_lock,
    release_state_write_lock,
)
from backend.services.novel.faction_volume_state_service import (
    FactionStateSourceCompensationError,
    FactionVolumeStateService,
    compensate_state_changes as compensate_faction_state_changes,
)
from backend.services.novel.item_service import (
    acquire_item_write_lock,
    release_item_write_lock,
)

logger = logging.getLogger(__name__)

FACTION_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "alias",
        "faction_type",
        "parent_faction_id",
        "positioning",
        "public_stance",
        "core_goal",
        "hidden_goal",
        "resources_and_advantages",
        "organization_style",
        "core_values",
        "conflict_with_mainline",
        "is_public",
        "influence_scope",
        "active_status",
        "expandability",
        "tags",
        "first_appearance_volume_id",
        "first_appearance_chapter_id",
        "sort_order",
        "extra",
    }
)

_faction_relation_base_repo = BaseRepository("faction_relations")
_faction_binding_base_repo = BaseRepository("character_faction_bindings")


def _snapshot_deleted_query(snapshot: Mapping[str, Any]) -> object:
    """构造预镜像删除态的精确 CAS 条件。

    Args:
        snapshot: 写入前的势力、关系、绑定或子势力文档。

    Returns:
        精确布尔删除态。
    """
    return bool(snapshot["is_deleted"])


def _dependency_user_intent(snapshot: Mapping[str, Any]) -> bool:
    """读取依赖对象的用户启停选择。

    Args:
        snapshot: 人物—势力绑定或阵营关系预镜像。

    Returns:
        独立于实体 blocker 的用户启停意图。
    """
    return snapshot["user_is_active"]


async def _load_faction_relations(
    novel_id: str,
    faction_id: str,
    *,
    include_deleted: bool,
    session: AsyncClientSession | None,
) -> list[dict[str, Any]]:
    """读取势力参与的全部阵营关系预镜像。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 稳定势力业务 ID。
        include_deleted: 是否包含关系回收站记录。
        session: 可选 MongoDB 会话。

    Returns:
        当前势力作为任一端点的阵营关系预镜像。
    """
    return await _faction_relation_base_repo.find_many(
        {
            "novel_id": to_object_id(novel_id),
            "$or": [
                {"source_faction_id": faction_id},
                {"target_faction_id": faction_id},
            ],
        },
        include_deleted=include_deleted,
        session=session,
    )


async def _load_faction_bindings(
    novel_id: str,
    faction_id: str,
    *,
    include_deleted: bool,
    session: AsyncClientSession | None,
) -> list[dict[str, Any]]:
    """读取引用势力的角色—势力绑定预镜像。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 稳定势力业务 ID。
        include_deleted: 是否包含绑定回收站记录。
        session: 可选 MongoDB 会话。

    Returns:
        当前势力下的角色—势力绑定预镜像。
    """
    return await _faction_binding_base_repo.find_many(
        {"novel_id": to_object_id(novel_id), "faction_id": faction_id},
        include_deleted=include_deleted,
        session=session,
    )


async def _load_child_factions(
    novel_id: str,
    faction_id: str,
    *,
    session: AsyncClientSession | None,
) -> list[dict[str, Any]]:
    """读取仍直接挂靠当前父级的全部子势力。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 父势力业务 ID。
        session: 可选 MongoDB 会话。

    Returns:
        当前仍挂靠在该势力下的活动与回收站子势力。
    """
    return await faction_repo.find_many(
        {
            "novel_id": to_object_id(novel_id),
            "parent_faction_id": faction_id,
        },
        include_deleted=True,
        sort=[("faction_id", 1)],
        session=session,
    )


def _raise_if_has_child_factions(children: Sequence[Mapping[str, Any]]) -> None:
    """在父级生命周期或停用命令前阻断仍有直接子级的势力。

    Args:
        children: 同一写锁内读取的活动与回收站直接子势力。

    Returns:
        无；没有子势力时允许调用方继续。
    """
    if not children:
        return
    child_ids = [str(child["faction_id"]) for child in children]
    raise DomainApiError(
        "FACTION_CHILD_REFERENCE_PROTECTED",
        "势力仍有直接子势力，不能停用或删除",
        status_code=409,
        details={"child_ids": child_ids, "count": len(child_ids)},
    )


def _validate_expected_faction_version(expected_version: Any) -> int:
    """校验并返回客户端提交的势力乐观锁版本。

    Args:
        expected_version: 客户端基于的势力版本。

    Returns:
        大于等于 1 的严格整数版本。
    """
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise ValueError("expected_version 必须为正整数")
    if expected_version < 1:
        raise ValueError("expected_version 必须大于等于 1")
    return expected_version


async def _get_versioned_faction(
    novel_id: str,
    faction_id: str,
    expected_version: int,
    *,
    deleted: bool,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """读取指定生命周期状态的势力并校验客户端版本。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 稳定势力业务 ID。
        expected_version: 客户端基于的势力版本。
        deleted: True 时只读取回收站，否则读取未删除势力。
        session: 可选 MongoDB 会话。

    Returns:
        与客户端版本一致的势力预镜像。
    """
    normalized_version = _validate_expected_faction_version(expected_version)
    if deleted:
        faction = await faction_repo.get_deleted_faction(
            novel_id,
            faction_id,
            session=session,
        )
    else:
        faction = await faction_repo.get_faction(
            novel_id,
            faction_id,
            session=session,
        )
    current_version = int(faction["version"])
    if current_version != normalized_version:
        raise DuplicateKeyError(
            "势力版本冲突："
            f"当前版本为 {current_version}，请求版本为 {normalized_version}"
        )
    return faction


async def _cas_update_faction_snapshot(
    snapshot: Mapping[str, Any],
    update_fields: Mapping[str, Any],
    *,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """按预镜像版本与删除态更新势力并返回本次精确写后文档。

    Args:
        snapshot: 势力写入前预镜像。
        update_fields: 已经过势力编辑白名单过滤的字段。
        session: 可选 MongoDB 会话。

    Returns:
        递增内部版本后的势力文档。
    """
    current_version = int(snapshot["version"])
    try:
        updated = await faction_repo.collection.find_one_and_update(
            {
                "_id": snapshot["_id"],
                **_snapshot_version_query(snapshot),
                "is_deleted": _snapshot_deleted_query(snapshot),
                DEPENDENCY_GUARD_FIELD: snapshot.get(DEPENDENCY_GUARD_FIELD, 0),
            },
            {
                "$set": {
                    **dict(update_fields),
                    "version": current_version + 1,
                    "updated_at": get_utc_now(),
                }
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
    except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
        raise DuplicateKeyError("势力更新与现有业务约束冲突") from exc
    if updated is None:
        raise DuplicateKeyError("势力已被其他请求修改，请刷新后重试")
    return updated


async def _apply_faction_relation_changes(
    snapshots: Sequence[dict[str, Any]],
    faction_id: str,
    *,
    projected_name: str | None,
    available: bool | None,
    applied_snapshots: list[_CompensationRecord],
    session: AsyncClientSession | None,
) -> int:
    """逐条 CAS 更新阵营关系名称投影与势力 blocker。

    Args:
        snapshots: 本次操作前读取的阵营关系预镜像。
        faction_id: 名称或可用性发生变化的势力 ID。
        projected_name: 新显示名；None 表示不更新名称投影。
        available: 新可用性；None 表示不改 blocker。
        applied_snapshots: 记录已经成功写入的补偿记录。
        session: 可选 MongoDB 会话。

    Returns:
        实际修改的阵营关系数量。
    """
    updated_count = 0
    for snapshot in snapshots:
        updates: dict[str, Any] = {}
        if projected_name is not None:
            if (
                snapshot.get("source_faction_id") == faction_id
                and snapshot.get("source_faction_name") != projected_name
            ):
                updates["source_faction_name"] = projected_name
            if (
                snapshot.get("target_faction_id") == faction_id
                and snapshot.get("target_faction_name") != projected_name
            ):
                updates["target_faction_name"] = projected_name

        if available is not None and snapshot.get("is_deleted") is not True:
            blockers = _normalized_blockers(snapshot, "disabled_by_faction_ids")
            next_blockers = [item for item in blockers if item != faction_id]
            if not available and faction_id not in next_blockers:
                next_blockers.append(faction_id)
            user_is_active = _dependency_user_intent(snapshot)
            next_is_active = bool(user_is_active and not next_blockers)
            updates.update(
                {
                    "user_is_active": user_is_active,
                    "disabled_by_faction_ids": next_blockers,
                    "is_active": next_is_active,
                }
            )

        changed = {
            field: value for field, value in updates.items() if snapshot.get(field) != value
        }
        if not changed:
            continue
        current_version = int(snapshot["version"])
        changed.update({"version": current_version + 1, "updated_at": get_utc_now()})
        try:
            result = await faction_relation_repo.collection.update_one(
                {
                    "_id": snapshot["_id"],
                    **_snapshot_version_query(snapshot),
                    "is_deleted": _snapshot_deleted_query(snapshot),
                },
                {"$set": changed},
                session=session,
            )
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("势力恢复后阵营关系发生活动语义冲突") from exc
        if result.matched_count != 1:
            raise _DependencyReconcileCasMiss(
                "阵营关系已被其他请求修改，请重新读取后重试"
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


async def _apply_faction_binding_availability(
    snapshots: Sequence[dict[str, Any]],
    faction_id: str,
    *,
    available: bool,
    applied_snapshots: list[_CompensationRecord],
    session: AsyncClientSession | None,
) -> int:
    """逐条 CAS 更新角色—势力绑定的势力 blocker 与有效态。

    Args:
        snapshots: 本次操作前读取的绑定预镜像。
        faction_id: 可用性发生变化的势力 ID。
        available: 势力操作后的可用性。
        applied_snapshots: 记录已经成功写入的补偿记录。
        session: 可选 MongoDB 会话。

    Returns:
        实际修改的绑定数量。
    """
    updated_count = 0
    for snapshot in snapshots:
        if snapshot.get("is_deleted") is True:
            continue
        blockers = _normalized_blockers(snapshot, "disabled_by_faction_ids")
        next_blockers = [item for item in blockers if item != faction_id]
        if not available and faction_id not in next_blockers:
            next_blockers.append(faction_id)
        user_is_active = _dependency_user_intent(snapshot)
        next_is_active = bool(
            user_is_active
            and not next_blockers
            and not _normalized_blockers(snapshot, "disabled_by_character_ids")
        )
        updates = {
            "user_is_active": user_is_active,
            "disabled_by_faction_ids": next_blockers,
            "is_active": next_is_active,
        }
        if all(snapshot.get(field) == value for field, value in updates.items()):
            continue
        current_version = int(snapshot["version"])
        updates.update({"version": current_version + 1, "updated_at": get_utc_now()})
        try:
            result = await character_faction_binding_repo.collection.update_one(
                {
                    "_id": snapshot["_id"],
                    **_snapshot_version_query(snapshot),
                    "is_deleted": _snapshot_deleted_query(snapshot),
                },
                {"$set": updates},
                session=session,
            )
        except (PyMongoDuplicateKeyError, BulkWriteError) as exc:
            raise DuplicateKeyError("势力恢复后角色—势力绑定发生活动唯一冲突") from exc
        if result.matched_count != 1:
            raise _DependencyReconcileCasMiss(
                "角色—势力绑定已被其他请求修改，请重新读取后重试"
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


async def _validate_faction_binding_unblock(
    novel_id: str,
    faction_id: str,
    *,
    session: AsyncClientSession | None,
) -> int:
    """预检势力恢复可用后将重新启用的角色—势力绑定唯一性。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 即将恢复可用的势力 ID。
        session: 可选 MongoDB 会话。

    Returns:
        预检通过后将重新启用的绑定数量。
    """
    bindings = await _load_faction_bindings(
        novel_id,
        faction_id,
        include_deleted=False,
        session=session,
    )
    semantic_candidates: dict[tuple[str, str, str], str] = {}
    primary_candidates: dict[str, str] = {}
    for binding in bindings:
        blockers = _normalized_blockers(binding, "disabled_by_faction_ids")
        if faction_id not in blockers or _dependency_user_intent(binding) is not True:
            continue
        remaining = [item for item in blockers if item != faction_id]
        if remaining or _normalized_blockers(binding, "disabled_by_character_ids"):
            continue
        semantic = (
            str(binding["character_id"]),
            str(binding["faction_id"]),
            str(binding["membership_type"]),
        )
        if semantic in semantic_candidates:
            raise DuplicateKeyError("势力恢复后角色—势力绑定语义重复")
        semantic_candidates[semantic] = str(binding["binding_id"])
        if binding.get("membership_type") == "primary":
            character_id = str(binding["character_id"])
            if character_id in primary_candidates:
                raise DuplicateKeyError("势力恢复后同一角色出现多个主归属")
            primary_candidates[character_id] = str(binding["binding_id"])

    semantic_conflicts = await character_faction_binding_repo.find_active_semantic_bindings(
        novel_id,
        list(semantic_candidates),
        session=session,
    )
    if semantic_conflicts:
        raise DuplicateKeyError("势力恢复会与现有活动角色—势力绑定语义冲突")
    primary_conflicts = await character_faction_binding_repo.find_active_primary_bindings(
        novel_id,
        list(primary_candidates),
        session=session,
    )
    if primary_conflicts:
        raise DuplicateKeyError("势力恢复会导致同一角色存在多个活动主归属")
    return len(semantic_candidates)


async def _reconcile_faction_dependents(faction: Mapping[str, Any]) -> None:
    """按当前势力主档重扫并调和阵营关系、角色绑定与晚到子势力。

    Args:
        faction: 已确认保留或恢复的当前势力主档。

    Returns:
        无。
    """
    novel_id = str(faction["novel_id"])
    faction_id = str(faction["faction_id"])
    relation_available = bool(
        faction.get("is_deleted") is not True
        and faction.get("active_status") == "active"
    )
    binding_available = bool(
        relation_available and faction["level_type"] == "core"
    )
    projected_name = str(faction.get("name") or "").strip()

    async def _reconcile_once() -> None:
        """重新读取当前全部势力依赖并执行一轮版本化调和。"""
        latest_relations = await _load_faction_relations(
            novel_id,
            faction_id,
            include_deleted=True,
            session=None,
        )
        latest_bindings = await _load_faction_bindings(
            novel_id,
            faction_id,
            include_deleted=False,
            session=None,
        )
        # 关系名称投影与 blocker 共用同一轮最新版本 CAS。
        await _apply_faction_relation_changes(
            latest_relations,
            faction_id,
            projected_name=projected_name or None,
            available=relation_available,
            applied_snapshots=[],
            session=None,
        )
        await _apply_faction_binding_availability(
            latest_bindings,
            faction_id,
            available=binding_available,
            applied_snapshots=[],
            session=None,
        )
    await _run_bounded_dependency_reconcile(
        _reconcile_once,
        label="势力依赖调和",
    )


async def _compensate_faction_write(
    faction_record: _CompensationRecord | None,
    relation_records: Sequence[_CompensationRecord],
    binding_records: Sequence[_CompensationRecord],
) -> None:
    """恢复势力生命周期 standalone 顺序写已经应用的全部预镜像。

    Args:
        faction_record: 势力主档更新或删除补偿记录。
        relation_records: 已修改或删除的阵营关系补偿记录。
        binding_records: 已修改或删除的角色—势力绑定补偿记录。
    Returns:
        无。
    """
    if faction_record is None:
        await _restore_snapshots(_faction_relation_base_repo, relation_records)
        await _restore_snapshots(_faction_binding_base_repo, binding_records)
        return

    try:
        await _restore_snapshots(faction_repo, [faction_record])
    except Exception as master_exc:
        # 公开版本已推进时保留较新势力，仅按当前真相调和依赖并明确报告补偿未完成。
        current = await faction_repo.collection.find_one(
            {
                "_id": faction_record.snapshot["_id"],
                "novel_id": faction_record.snapshot["novel_id"],
                "faction_id": faction_record.snapshot["faction_id"],
            }
        )
        if current is not None:
            await _reconcile_faction_dependents(current)
            raise RuntimeError(
                "standalone 势力主档补偿未完成：公开版本或删除态已推进；"
                "已保留较新主档并按当前状态调和依赖"
            ) from master_exc
        raise RuntimeError(
            "standalone 势力主档补偿未完成：原业务身份已不存在或被重建"
        ) from master_exc

    dependency_error: Exception | None = None
    try:
        await _restore_snapshots(_faction_relation_base_repo, relation_records)
        await _restore_snapshots(_faction_binding_base_repo, binding_records)
    except Exception as exc:
        dependency_error = exc

    await _reconcile_faction_dependents(faction_record.snapshot)
    if dependency_error is not None:
        raise RuntimeError(
            "standalone 势力依赖预镜像补偿未完整命中；已按恢复后的主档调和最新依赖"
        ) from dependency_error


class FactionService:
    """
    阵营（Faction）服务层，编排跨集合的业务逻辑。
    纯集合内操作由 FactionRepository 负责，跨集合联动由此处编排。
    """

    @staticmethod
    def validate_core_factions_result(
        result: CoreFactionsResultSchema,
        req: GenerateCoreFactionsRequestV2,
        existing_core_factions: list[dict[str, Any]],
    ) -> CoreFactionsResultSchema:
        """校验核心阵营模型结果中的领域数量、名称和关系引用。

        Args:
            result: 已通过结构 Schema 的 Provider 结果。
            req: 本次生成数量与本批不建立直接关系的势力数量。
            existing_core_factions: 可作为关系端点但不得重复生成的正式阵营。

        Returns:
            通过业务后验校验的原结果。

        Raises:
            LLMSchemaError: 数量、名称或关系引用不满足要求时抛出。
        """
        if len(result.core_factions) != req.faction_count:
            raise LLMSchemaError(f"core_factions 数量必须等于 {req.faction_count}")

        try:
            generated_name_pairs = [
                normalize_faction_name(item.name) for item in result.core_factions
            ]
        except (TypeError, ValueError) as exc:
            raise LLMSchemaError(f"生成核心势力名称不合法: {exc}") from exc
        generated_name_keys = [normalized_name for _, normalized_name in generated_name_pairs]
        if len(generated_name_keys) != len(set(generated_name_keys)):
            raise LLMSchemaError("生成核心势力名称经规范化后不能重复")
        generated_refs = {item.faction_ref for item in result.core_factions}
        existing_name_pairs = {
            normalize_faction_name(str(item.get("name") or ""))
            for item in existing_core_factions
            if str(item.get("name") or "").strip()
        }
        existing_name_keys = {normalized_name for _, normalized_name in existing_name_pairs}
        overlap = [
            display_name
            for display_name, normalized_name in generated_name_pairs
            if normalized_name in existing_name_keys
        ]
        if overlap:
            raise LLMSchemaError(
                f"生成阵营不得与已有阵营重名: {', '.join(sorted(overlap))}"
            )

        existing_ids = {
            str(item.get("faction_id") or "").strip()
            for item in existing_core_factions
            if str(item.get("faction_id") or "").strip()
        }
        connected_generated_refs: set[str] = set()
        for relation in result.faction_relations:
            endpoints = (relation.source, relation.target)
            candidate_refs = {
                endpoint.faction_ref
                for endpoint in endpoints
                if endpoint.kind == "candidate"
            }
            formal_ids = {
                endpoint.faction_id
                for endpoint in endpoints
                if endpoint.kind == "existing"
            }
            if not candidate_refs <= generated_refs or not formal_ids <= existing_ids:
                raise LLMSchemaError("阵营关系端点必须引用本次 faction_ref 或已有 faction_id")
            if not candidate_refs:
                raise LLMSchemaError("新增关系至少有一个端点属于本次生成阵营")
            connected_generated_refs.update(candidate_refs)

        independent_count = len(generated_refs - connected_generated_refs)
        if independent_count != req.independent_faction_count:
            raise LLMSchemaError(
                "本批不建立直接关系的势力数量与请求不一致: "
                f"期望 {req.independent_faction_count}，实际 {independent_count}"
            )
        return result

    @staticmethod
    def _normalize_generated_core_faction(data: Dict[str, Any], *, faction_id: str, sort_order: int) -> Dict[str, Any]:
        """将 AI 生成的核心阵营转换为 factions 集合可写入文档。

        Args:
            data: 单个核心阵营生成结果。
            faction_id: 后端分配的业务阵营 ID。
            sort_order: 阵营排序权重。

        Returns:
            可写入 factions 集合的阵营文档片段。
        """
        payload = dict(data)
        payload["name"], payload["normalized_name"] = normalize_faction_name(
            payload.get("name")
        )
        payload["faction_id"] = faction_id
        payload["level_type"] = "core"
        payload["parent_faction_id"] = None
        payload["volume_id"] = None
        payload["active_status"] = "active"
        payload["sort_order"] = sort_order
        payload.setdefault("alias", [])
        payload.setdefault("first_appearance_volume_id", None)
        payload.setdefault("first_appearance_chapter_id", None)
        payload.setdefault("extra", {})
        return payload

    @staticmethod
    def _normalize_generated_relation(
        data: Dict[str, Any],
        *,
        faction_ref_map: Dict[str, str],
        existing_faction_ids: set[str],
    ) -> Dict[str, Any]:
        """将严格判别候选端点映射为正式 faction_id 关系。

        Args:
            data: 单条 AI 生成关系，端点使用候选 ref 或正式 ID。
            faction_ref_map: 本次所选候选 ref 到正式势力 ID 的映射。
            existing_faction_ids: 生成时已存在且确认时仍可用的正式势力 ID。

        Returns:
            可写入 faction_relations 集合的关系文档片段。
        """
        def _resolve(endpoint: Mapping[str, Any]) -> tuple[str, bool]:
            """把单个判别端点解析为正式 ID 和是否本批新势力。"""
            if endpoint.get("kind") == "candidate":
                faction_ref = str(endpoint.get("faction_ref") or "")
                if faction_ref not in faction_ref_map:
                    raise ValueError("关系引用了未选择或不存在的新势力")
                return faction_ref_map[faction_ref], True
            if endpoint.get("kind") == "existing":
                faction_id = str(endpoint.get("faction_id") or "")
                if faction_id not in existing_faction_ids:
                    raise ValueError(f"关系引用的已有势力不存在或已变化: {faction_id}")
                return faction_id, False
            raise ValueError("阵营关系端点类型不合法")

        source_id, source_is_new = _resolve(data.get("source") or {})
        target_id, target_is_new = _resolve(data.get("target") or {})
        if not source_is_new and not target_is_new:
            raise ValueError("新增关系至少需要连接一个本次生成的核心阵营")

        payload = {
            "source_faction_id": source_id,
            "target_faction_id": target_id,
            "relation_type": data.get("relation_type"),
            "current_state": data.get("current_state", ""),
            "core_conflict": data.get("core_conflict", ""),
            "hidden_tension": data.get("hidden_tension", ""),
            "possible_change": data.get("possible_change", ""),
            "intensity": data.get("intensity", 3),
            "is_active": data.get("is_active", True),
        }
        return payload

    @staticmethod
    async def _ensure_unique_active_name(
        novel_id: str,
        name: str,
        *,
        level_type: str = "core",
        volume_id: str | ObjectId | None = None,
        exclude_faction_id: str | None = None,
        session=None,
    ) -> None:
        """校验同一小说同一层级下未删除阵营名称不重复。

        Args:
            novel_id: 小说 ObjectId 字符串。
            name: 待校验阵营名称。
            level_type: 势力层级。
            volume_id: volume/local 的归属卷；core 必须为 None。
            exclude_faction_id: 更新时需要排除的当前阵营 ID。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            无。

        Raises:
            DuplicateKeyError: 已存在同名未删除阵营时抛出。
        """
        _, normalized_name = normalize_faction_name(name)
        query: Dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "level_type": level_type,
            "volume_id": to_object_id(volume_id) if volume_id is not None else None,
            "active_status": "active",
            "normalized_name": normalized_name,
        }
        if exclude_faction_id:
            query["faction_id"] = {"$ne": exclude_faction_id}
        existing = await faction_repo.find_one(query, session=session)
        if existing:
            raise DuplicateKeyError(f"同一小说同一势力层级下已存在同名阵营: {name}")

    @staticmethod
    async def _validate_scope_and_parent(
        novel_id: str,
        *,
        level_type: str,
        volume_id: str | None,
        parent_faction_id: str | None,
        faction_id: str | None = None,
        session: AsyncClientSession | None,
    ) -> ObjectId | None:
        """校验人工势力的归属卷与父级作用域。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: core、volume 或 local。
            volume_id: volume/local 的正式归属卷。
            parent_faction_id: 可选父势力业务 ID。
            faction_id: 更新或恢复时当前势力 ID，用于拒绝自环和祖先环。
            session: 可选 MongoDB 会话。

        Returns:
            可直接持久化的归属卷 ObjectId；core 返回 None。
        """
        if level_type not in {"core", "volume", "local"}:
            raise ValueError("level_type 仅允许 core、volume 或 local")
        owned_volume_id = None
        if level_type == "core":
            if volume_id is not None:
                raise ValueError("core 势力不能设置 volume_id")
        else:
            if volume_id is None:
                raise ValueError("volume/local 势力必须设置 volume_id")
            volume = await volume_repo.get_volume_by_id(
                volume_id,
                session=session,
            )
            if volume.get("novel_id") != to_object_id(novel_id):
                raise NotFoundError("归属卷不存在、已删除或不属于当前小说")
            owned_volume_id = volume["_id"]

        if parent_faction_id is None:
            return owned_volume_id
        if faction_id is not None and parent_faction_id == faction_id:
            raise ValueError("父势力不能指向自身")
        parent = await faction_repo.get_faction(
            novel_id,
            parent_faction_id,
            session=session,
        )
        if parent["active_status"] != "active":
            raise NotFoundError("父势力不存在、已删除或已停用")
        parent_level = parent["level_type"]
        parent_volume_id = parent.get("volume_id")
        if level_type == "core":
            if parent_level != "core" or parent_volume_id is not None:
                raise ValueError("core 势力只能挂在 core 父势力下")
            valid_parent_scope = True
        elif level_type != "core" and parent_level == "core" and parent_volume_id is None:
            valid_parent_scope = True
        elif (
            level_type != "core"
            and parent_level in {"volume", "local"}
            and parent_volume_id is not None
            and to_object_id(parent_volume_id) == owned_volume_id
        ):
            valid_parent_scope = True
        else:
            valid_parent_scope = False
        if not valid_parent_scope:
            if level_type == "core":
                raise ValueError("core 势力只能挂在 core 父势力下")
            raise ValueError("volume/local 势力只能挂 core 或同归属卷父势力")

        if faction_id is not None:
            visited: set[str] = set()
            cursor = parent
            while cursor.get("parent_faction_id") is not None:
                cursor_id = str(cursor.get("faction_id") or "")
                if cursor_id in visited:
                    raise ValueError("现有父势力链已经成环，不能继续重挂")
                visited.add(cursor_id)
                next_parent_id = str(cursor["parent_faction_id"])
                if next_parent_id == faction_id:
                    raise ValueError("父势力不能是当前势力的下级")
                cursor = await faction_repo.get_faction(
                    novel_id,
                    next_parent_id,
                    session=session,
                )
        return owned_volume_id

    @staticmethod
    async def has_core_factions_initialized(novel_id: str, *, session=None) -> bool:
        """判断小说是否已经存在核心阵营初始化记录。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            存在未删除或已软删除核心阵营时返回 True。
        """
        count = await faction_repo.count_factions_by_level_type(
            novel_id,
            "core",
            include_deleted=True,
            session=session,
        )
        return count > 0

    @staticmethod
    async def create_faction(
        novel_id: str,
        data: Dict[str, Any],
        *,
        idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Any]:
        """幂等创建 core、volume 或 local 正式势力。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 阵营基础字段，不包含 novel_id。
            idempotency_key: 调用方提供的创建幂等键。
            session: 可选外层事务；提供时在同一事务内创建，不另开写入单元。

        Returns:
            新创建或同键回放的完整势力文档。
        """
        novel_id = str(to_object_id(novel_id))
        payload = dict(data)
        payload.pop("faction_ref", None)
        payload["name"], payload["normalized_name"] = normalize_faction_name(
            payload.get("name")
        )
        payload["level_type"] = str(payload.get("level_type") or "core")
        payload["parent_faction_id"] = payload.get("parent_faction_id")
        raw_volume_id = payload.get("volume_id")
        payload["volume_id"] = (
            str(to_object_id(raw_volume_id)) if raw_volume_id is not None else None
        )
        payload["active_status"] = "active"
        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "payload": payload})

        async def _find_replay(
            session: AsyncClientSession | None,
        ) -> dict[str, Any] | None:
            """读取并校验同一幂等键的既有人工势力创建结果。"""
            existing = await faction_repo.find_by_creation_idempotency(
                novel_id,
                key_hash,
                session=session,
            )
            if existing is None:
                return None
            if existing.get("creation_request_hash") != request_hash:
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的势力创建请求",
                    status_code=409,
                )
            return existing

        async def _create(session: AsyncClientSession | None) -> dict[str, Any]:
            """在同一个写入单元内校验小说、生成业务 ID 并插入阵营。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                replay = await _find_replay(session)
                if replay is not None:
                    return replay
                owned_volume_id = await FactionService._validate_scope_and_parent(
                    novel_id,
                    level_type=payload["level_type"],
                    volume_id=payload["volume_id"],
                    parent_faction_id=payload["parent_faction_id"],
                    session=session,
                )
                await FactionService._ensure_unique_active_name(
                    novel_id,
                    payload["name"],
                    level_type=payload["level_type"],
                    volume_id=owned_volume_id,
                    session=session,
                )
                create_payload = dict(payload)
                create_payload["novel_id"] = novel_id
                create_payload["volume_id"] = owned_volume_id
                # 正式业务 ID 只能由可靠序列分配，禁止客户端绕过终身不复用约束。
                create_payload["faction_id"] = await faction_repo._get_next_faction_id(
                    novel_id,
                    session=session,
                )
                if create_payload.get("sort_order") is None:
                    # 同一父级与归属卷内尾部追加，避免不同工作台层级互相影响顺序。
                    sibling_count = await faction_repo.count_documents(
                        {
                            "novel_id": to_object_id(novel_id),
                            "level_type": payload["level_type"],
                            "parent_faction_id": payload["parent_faction_id"],
                            "volume_id": owned_volume_id,
                        },
                        session=session,
                    )
                    create_payload["sort_order"] = (sibling_count + 1) * 10
                create_payload["creation_idempotency_key_hash"] = key_hash
                create_payload["creation_request_hash"] = request_hash
                await faction_repo.create_faction(create_payload, session=session)
                return await faction_repo.get_faction(
                    novel_id,
                    create_payload["faction_id"],
                    session=session,
                )
            finally:
                await release_state_write_lock(
                    novel_id,
                    state_lock,
                    session=session,
                )

        if session is not None:
            return await _create(session)
        try:
            return await run_mongo_write_unit(_create, "create_faction")
        except DuplicateKeyError:
            # 唯一索引决定并发赢家；输家只回放，不执行第二次业务创建。
            replay = await _find_replay(None)
            if replay is not None:
                return replay
            raise

    @staticmethod
    async def bulk_create_core_factions_with_relations(novel_id: str, data: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """幂等确认所选核心势力及关系候选。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 已通过严格 AI 确认 Schema 校验的请求。
            idempotency_key: 调用方提交的确认幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            完整 ref 映射、势力和关系正式文档。
        """
        source = (
            data.model_dump(mode="json")
            if hasattr(data, "model_dump")
            else dict(data)
        )
        candidate = dict(source.get("candidate") or {})
        selected_faction_refs = list(source.get("selected_faction_refs") or [])
        selected_relation_refs = list(source.get("selected_relation_refs") or [])
        faction_by_ref = {
            str(item["faction_ref"]): dict(item)
            for item in candidate.get("core_factions") or []
        }
        relation_by_ref = {
            str(item["relation_ref"]): dict(item)
            for item in candidate.get("faction_relations") or []
        }
        selected_factions = [faction_by_ref[ref] for ref in selected_faction_refs]
        selected_relations = [relation_by_ref[ref] for ref in selected_relation_refs]
        selected_name_keys = [
            normalize_faction_name(faction.get("name"))[1]
            for faction in selected_factions
        ]
        if len(selected_name_keys) != len(set(selected_name_keys)):
            raise ValueError("所选核心势力名称经规范化后不能重复")
        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "request": source})

        async def _load_existing(
            session: AsyncClientSession | None,
        ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
            """读取同键已写入的势力和关系本地 ref 映射。"""
            existing_factions = await faction_repo.find_by_core_batch_idempotency(
                novel_id,
                key_hash,
                session=session,
            )
            existing_relations = await faction_relation_repo.find_by_batch_idempotency(
                novel_id,
                key_hash,
                session=session,
            )
            all_documents = [*existing_factions, *existing_relations]
            if any(
                item.get("core_batch_request_hash", item.get("batch_request_hash"))
                != request_hash
                for item in all_documents
            ):
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的核心势力确认请求",
                    status_code=409,
                )
            factions_by_ref = {
                str(item.get("core_batch_local_ref")): item
                for item in existing_factions
                if item.get("core_batch_local_ref")
            }
            relations_by_ref = {
                str(item.get("batch_local_ref")): item
                for item in existing_relations
                if item.get("batch_local_ref")
            }
            if (
                len(factions_by_ref) != len(existing_factions)
                or len(relations_by_ref) != len(existing_relations)
                or set(factions_by_ref) - set(selected_faction_refs)
                or set(relations_by_ref) - set(selected_relation_refs)
            ):
                raise DuplicateKeyError("核心势力确认批次本地 ref 元数据冲突")
            return factions_by_ref, relations_by_ref

        def _build_result(
            factions_by_ref: dict[str, dict[str, Any]],
            relations_by_ref: dict[str, dict[str, Any]],
        ) -> Dict[str, Any]:
            """按用户选择顺序组装核心势力确认的公开映射。

            Args:
                factions_by_ref: 候选 faction_ref 到正式势力文档的映射。
                relations_by_ref: 候选 relation_ref 到正式关系文档的映射。

            Returns:
                两类 ref 映射及顺序稳定的正式势力、关系文档。
            """
            return {
                "faction_ref_map": {
                    ref: str(factions_by_ref[ref]["faction_id"])
                    for ref in selected_faction_refs
                },
                "relation_ref_map": {
                    ref: str(relations_by_ref[ref]["relation_id"])
                    for ref in selected_relation_refs
                },
                "factions": [
                    factions_by_ref[ref] for ref in selected_faction_refs
                ],
                "faction_relations": [
                    relations_by_ref[ref] for ref in selected_relation_refs
                ],
            }

        async def _confirm(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在单个 Mongo 写入单元内校验依据并续写缺失 ref。"""
            basis = source["basis"]
            generation_input = source["generation_input"]
            if (
                basis.get("novel_id") != novel_id
                or generation_input.get("novel_id") != novel_id
            ):
                raise NotFoundError("核心势力候选不属于当前小说")
            if (
                basis.get("workflow") != CORE_FACTIONS_WORKFLOW
                or basis.get("step") != CORE_FACTIONS_STEP
                or basis.get("schema_id") != CORE_FACTIONS_RESULT_SCHEMA_ID
                or basis.get("schema_version") != CORE_FACTIONS_RESULT_SCHEMA_VERSION
            ):
                raise ValueError("核心势力确认的 workflow/step/schema 契约不匹配")

            existing_by_ref, existing_relations_by_ref = await _load_existing(session)
            if (
                set(existing_by_ref) == set(selected_faction_refs)
                and set(existing_relations_by_ref) == set(selected_relation_refs)
            ):
                return _build_result(existing_by_ref, existing_relations_by_ref)
            novel = await novel_repo.get_novel_by_id(novel_id, session=session)
            current_versions: dict[tuple[str, str], int] = {
                ("novel", novel_id): int(novel["version"])
            }
            basis_faction_ids: set[str] = set()
            basis_relation_ids: set[str] = set()
            for item in basis.get("source_refs", []):
                resource_type = str(item["resource_type"])
                resource_id = str(item["id"])
                if resource_type == "novel":
                    if resource_id != novel_id:
                        raise NotFoundError("核心势力候选引用了其他小说")
                    current = novel
                elif resource_type == "faction":
                    basis_faction_ids.add(resource_id)
                    current = await faction_repo.get_faction(
                        novel_id,
                        resource_id,
                        session=session,
                    )
                elif resource_type == "faction_relation":
                    basis_relation_ids.add(resource_id)
                    current = await faction_relation_repo.get_relation(
                        novel_id,
                        resource_id,
                        session=session,
                    )
                else:
                    raise ValueError(f"不支持的 basis resource_type={resource_type}")
                current_versions[(resource_type, resource_id)] = int(
                    current["version"]
                )

            for item in basis.get("source_refs", []):
                identity = (str(item["resource_type"]), str(item["id"]))
                if current_versions.get(identity) != int(item["version"]):
                    raise DuplicateKeyError("核心势力候选依据版本冲突")
            current_fingerprint = compute_core_factions_input_fingerprint(
                generation_input,
                basis.get("source_refs", []),
                flow_snapshot=basis.get("flow_snapshot"),
            )
            if current_fingerprint != basis.get("input_fingerprint"):
                raise DuplicateKeyError("核心势力候选输入指纹冲突")

            all_core_factions = await faction_repo.get_active_core_factions(
                novel_id,
                session=session,
            )
            batch_faction_ids = {
                str(item["faction_id"]) for item in existing_by_ref.values()
            }
            current_formal_factions = [
                item
                for item in all_core_factions
                if str(item.get("faction_id")) not in batch_faction_ids
            ]
            if {
                str(item["faction_id"]) for item in current_formal_factions
            } != basis_faction_ids:
                raise DuplicateKeyError("核心势力候选依据中的正式势力集合已变化")
            current_formal_relations = [
                item
                for item in await faction_relation_repo.get_relations_by_novel(
                    novel_id,
                    active_only=True,
                    session=session,
                )
                if item.get("batch_idempotency_key_hash") != key_hash
                and item.get("source_faction_id") in basis_faction_ids
                and item.get("target_faction_id") in basis_faction_ids
            ]
            if {
                str(item["relation_id"]) for item in current_formal_relations
            } != basis_relation_ids:
                raise DuplicateKeyError("核心势力候选依据中的正式关系集合已变化")

            existing_name_keys = {
                item["normalized_name"] for item in current_formal_factions
            }
            missing_factions = [
                item
                for item in selected_factions
                if item["faction_ref"] not in existing_by_ref
            ]
            missing_name_pairs = [
                normalize_faction_name(item.get("name")) for item in missing_factions
            ]
            duplicate_names = [
                display_name
                for display_name, normalized_name in missing_name_pairs
                if normalized_name in existing_name_keys
            ]
            if duplicate_names:
                raise DuplicateKeyError(
                    f"同一小说下已存在同名核心势力: {', '.join(sorted(duplicate_names))}"
                )

            allocated_ids = await id_sequence_repo.allocate_many(
                novel_id,
                "faction",
                "fac",
                len(missing_factions),
                session=session,
            ) if missing_factions else []
            faction_ref_map = {
                ref: str(item["faction_id"])
                for ref, item in existing_by_ref.items()
            }
            faction_ref_map.update(
                {
                    faction["faction_ref"]: faction_id
                    for faction, faction_id in zip(missing_factions, allocated_ids)
                }
            )

            relation_payloads = [
                FactionService._normalize_generated_relation(
                    relation,
                    faction_ref_map=faction_ref_map,
                    existing_faction_ids=basis_faction_ids,
                )
                for relation in selected_relations
            ]
            created_faction_records: list[dict[str, Any]] = []
            relations_committed_this_attempt = False
            try:
                has_faction_marker = any(
                    item.get("core_batch_command_marker") is True
                    for item in existing_by_ref.values()
                )
                candidate_position = {
                    ref: index
                    for index, ref in enumerate(selected_faction_refs, start=1)
                }
                for index, (faction, faction_id) in enumerate(
                    zip(missing_factions, allocated_ids)
                ):
                    faction_ref = str(faction["faction_ref"])
                    payload = FactionService._normalize_generated_core_faction(
                        faction,
                        faction_id=faction_id,
                        sort_order=(
                            len(current_formal_factions)
                            + candidate_position[faction_ref]
                        ) * 10,
                    )
                    payload.update(
                        {
                            "novel_id": novel_id,
                            "core_batch_idempotency_key_hash": key_hash,
                            "core_batch_request_hash": request_hash,
                            "core_batch_local_ref": faction_ref,
                        }
                    )
                    if not has_faction_marker and index == 0:
                        payload["core_batch_command_marker"] = True
                    faction_oid = await faction_repo.create_faction(
                        payload,
                        session=session,
                    )
                    created_faction_records.append(
                        {
                            "_id": to_object_id(faction_oid),
                            "novel_id": to_object_id(novel_id),
                            "faction_id": faction_id,
                            "version": 1,
                        }
                    )
                    existing_by_ref[faction_ref] = await faction_repo.get_faction(
                        novel_id,
                        faction_id,
                        session=session,
                    )

                missing_relation_payloads: list[dict[str, Any]] = []
                has_relation_marker = any(
                    item.get("batch_command_marker") is True
                    for item in existing_relations_by_ref.values()
                )
                for relation, payload in zip(selected_relations, relation_payloads):
                    relation_ref = str(relation["relation_ref"])
                    if relation_ref in existing_relations_by_ref:
                        continue
                    payload.update(
                        {
                            "batch_idempotency_key_hash": key_hash,
                            "batch_request_hash": request_hash,
                            "batch_local_ref": relation_ref,
                            "batch_request_kind": "core_ai_confirmation",
                        }
                    )
                    if not has_relation_marker and not missing_relation_payloads:
                        payload["batch_command_marker"] = True
                    missing_relation_payloads.append(payload)
                if missing_relation_payloads:
                    created_relations = await FactionRelationService.bulk_create_relations(
                        novel_id,
                        missing_relation_payloads,
                        session=session,
                    )
                    # standalone 下关系已成功返回后，端点护栏也已推进；若后续组装
                    # 响应异常，保留带批次元数据的完整事实供同键精确续写。
                    relations_committed_this_attempt = True
                    for relation in created_relations:
                        existing_relations_by_ref[
                            str(relation["batch_local_ref"])
                        ] = relation
            except Exception:
                if (
                    session is None
                    and created_faction_records
                    and not relations_committed_this_attempt
                ):
                    await faction_repo.delete_factions_created_exact(
                        list(reversed(created_faction_records))
                    )
                raise

            if (
                set(existing_by_ref) != set(selected_faction_refs)
                or set(existing_relations_by_ref) != set(selected_relation_refs)
            ):
                raise DuplicateKeyError("核心势力确认批次未形成完整 ref 映射")
            return _build_result(existing_by_ref, existing_relations_by_ref)

        if session is not None:
            return await _confirm(session)

        try:
            return await run_mongo_write_unit(
                _confirm,
                "bulk_create_core_factions_with_relations",
            )
        except DuplicateKeyError:
            factions_by_ref, relations_by_ref = await _load_existing(None)
            if (
                set(factions_by_ref) == set(selected_faction_refs)
                and set(relations_by_ref) == set(selected_relation_refs)
            ):
                return _build_result(factions_by_ref, relations_by_ref)
            raise

    @staticmethod
    async def get_factions_by_novel(novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下所有阵营列表。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_factions_by_novel(novel_id)

    @staticmethod
    async def get_faction(novel_id: str, faction_id: str) -> Dict[str, Any]:
        """获取指定小说下的单个阵营详情。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。

        Returns:
            阵营文档。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_faction(novel_id, faction_id)

    @staticmethod
    async def get_factions_by_level_type(novel_id: str, level_type: str) -> List[Dict[str, Any]]:
        """获取指定小说下特定层级类型的阵营列表。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 阵营层级类型。

        Returns:
            阵营文档列表。
        """
        if level_type not in {"core", "volume", "local"}:
            raise ValueError("level_type 仅允许 core、volume 或 local")
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_factions_by_level_type(novel_id, level_type)

    @staticmethod
    async def get_deleted_factions_by_level_type(
        novel_id: str,
        level_type: str | None = None,
    ) -> List[Dict[str, Any]]:
        """获取指定小说下已软删除阵营列表，可按层级过滤。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 可选阵营层级类型。

        Returns:
            已软删除阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        if level_type is not None and level_type not in {"core", "volume", "local"}:
            raise ValueError("level_type 仅允许 core、volume 或 local")
        return await faction_repo.get_deleted_factions_by_level_type(novel_id, level_type)

    @staticmethod
    async def get_child_factions(novel_id: str, parent_faction_id: str) -> List[Dict[str, Any]]:
        """获取指定父级阵营的所有直接子阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_faction_id: 父级业务阵营 ID。

        Returns:
            子阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_child_factions(novel_id, parent_faction_id)

    @staticmethod
    async def update_faction_info(novel_id: str, faction_id: str, update_data: Dict[str, Any], *, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """更新阵营基础信息。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            update_data: 含 expected_version 的待更新字段。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            递增版本后的完整势力文档。
        """
        source = dict(update_data)
        expected_version = _validate_expected_faction_version(
            source.pop("expected_version", None)
        )
        forbidden_fields = {
            "novel_id",
            "faction_id",
            "level_type",
            "volume_id",
        }
        attempted_identity_changes = sorted(forbidden_fields & source.keys())
        if attempted_identity_changes:
            raise ValueError(
                "阶段 1 势力更新不得修改身份或层级字段: "
                + ", ".join(attempted_identity_changes)
            )
        unknown_fields = sorted(source.keys() - FACTION_EDITABLE_FIELDS)
        if unknown_fields:
            raise ValueError("势力更新包含未登记字段: " + ", ".join(unknown_fields))
        filtered_update = {
            key: value for key, value in source.items() if key in FACTION_EDITABLE_FIELDS
        }
        if not filtered_update:
            raise ValueError("势力更新至少需要一个可修改字段")
        if "name" in filtered_update:
            display_name, normalized_name = normalize_faction_name(
                filtered_update["name"]
            )
            filtered_update["name"] = display_name
            filtered_update["normalized_name"] = normalized_name
        for field in ("alias", "resources_and_advantages", "core_values", "tags"):
            if field in filtered_update and filtered_update[field] is None:
                filtered_update[field] = []
        for field in (
            "faction_type",
            "positioning",
            "public_stance",
            "core_goal",
            "hidden_goal",
            "organization_style",
            "conflict_with_mainline",
            "influence_scope",
            "expandability",
        ):
            if field in filtered_update and filtered_update[field] is None:
                filtered_update[field] = ""
        if "extra" in filtered_update and filtered_update["extra"] is None:
            filtered_update["extra"] = {}
        if "is_public" in filtered_update and filtered_update["is_public"] is None:
            raise ValueError("is_public 不能为 null")
        if "sort_order" in filtered_update and filtered_update["sort_order"] is None:
            raise ValueError("sort_order 不能为 null")
        if "active_status" in filtered_update and filtered_update["active_status"] not in {
            "active",
            "inactive",
        }:
            raise ValueError("active_status 仅允许 active 或 inactive")

        async def _update(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在同一个写入单元内更新阵营及其关系、绑定派生状态。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                current = await _get_versioned_faction(
                    novel_id,
                    faction_id,
                    expected_version,
                    deleted=False,
                    session=session,
                )
                await FactionService._validate_scope_and_parent(
                    novel_id,
                    level_type=current["level_type"],
                    volume_id=(
                        str(current["volume_id"])
                        if current.get("volume_id") is not None
                        else None
                    ),
                    parent_faction_id=filtered_update.get(
                        "parent_faction_id",
                        current.get("parent_faction_id"),
                    ),
                    faction_id=faction_id,
                    session=session,
                )
                next_data = dict(filtered_update)
                next_name = str(next_data.get("name", current.get("name", ""))).strip()
                if "name" in next_data:
                    next_data["name"] = next_name
                current_active_status = current["active_status"]
                next_active_status = str(
                    next_data.get("active_status", current_active_status)
                )
                name_changed = "name" in next_data and next_name != current.get("name")
                current_relation_available = current_active_status == "active"
                next_relation_available = next_active_status == "active"
                if current_relation_available and not next_relation_available:
                    children = await _load_child_factions(
                        novel_id,
                        faction_id,
                        session=session,
                    )
                    _raise_if_has_child_factions(children)
                current_binding_available = (
                    current_relation_available
                )
                next_binding_available = (
                    next_relation_available
                )
                relation_availability_changed = (
                    current_relation_available != next_relation_available
                )
                binding_availability_changed = (
                    current_binding_available != next_binding_available
                )
                if next_relation_available:
                    await FactionService._ensure_unique_active_name(
                        novel_id,
                        next_name,
                        level_type=current["level_type"],
                        volume_id=current.get("volume_id"),
                        exclude_faction_id=faction_id,
                        session=session,
                    )

                if not current_relation_available and next_relation_available:
                    # 在实体状态写入前预检所有将解除 blocker 的关系，避免恢复时才触发唯一索引冲突。
                    await FactionRelationService.validate_faction_unblock(
                        novel_id,
                        faction_id,
                        session=session,
                    )
                if not current_binding_available and next_binding_available:
                    await _validate_faction_binding_unblock(
                        novel_id,
                        faction_id,
                        session=session,
                    )

                relation_snapshots = (
                    await _load_faction_relations(
                        novel_id,
                        faction_id,
                        # 改名需要同步回收站关系；纯状态切换只处理未删除关系。
                        include_deleted=name_changed,
                        session=session,
                    )
                    if name_changed or relation_availability_changed
                    else []
                )
                binding_snapshots = (
                    await _load_faction_bindings(
                        novel_id,
                        faction_id,
                        include_deleted=False,
                        session=session,
                    )
                    if binding_availability_changed
                    else []
                )
                faction_record: _CompensationRecord | None = None
                relation_records: list[_CompensationRecord] = []
                binding_records: list[_CompensationRecord] = []
                try:
                    updated = await _cas_update_faction_snapshot(
                        current,
                        next_data,
                        session=session,
                    )
                    faction_record = _updated_compensation_record(current, updated)
                    if relation_snapshots:
                        await _apply_faction_relation_changes(
                            relation_snapshots,
                            faction_id,
                            projected_name=next_name if name_changed else None,
                            available=(
                                next_relation_available
                                if relation_availability_changed
                                else None
                            ),
                            applied_snapshots=relation_records,
                            session=session,
                        )
                    if binding_snapshots:
                        await _apply_faction_binding_availability(
                            binding_snapshots,
                            faction_id,
                            available=next_binding_available,
                            applied_snapshots=binding_records,
                            session=session,
                        )
                    # 主档 CAS 后再次扫描，覆盖“首次快照之后才插入”的并发依赖。
                    if name_changed or relation_availability_changed:
                        latest_relations = await _load_faction_relations(
                            novel_id,
                            faction_id,
                            include_deleted=name_changed,
                            session=session,
                        )
                        await _apply_faction_relation_changes(
                            latest_relations,
                            faction_id,
                            projected_name=next_name if name_changed else None,
                            available=(
                                next_relation_available
                                if relation_availability_changed
                                else None
                            ),
                            applied_snapshots=relation_records,
                            session=session,
                        )
                    if binding_availability_changed:
                        latest_bindings = await _load_faction_bindings(
                            novel_id,
                            faction_id,
                            include_deleted=False,
                            session=session,
                        )
                        await _apply_faction_binding_availability(
                            latest_bindings,
                            faction_id,
                            available=next_binding_available,
                            applied_snapshots=binding_records,
                            session=session,
                        )
                    return updated
                except Exception:
                    if session is None and faction_record is not None:
                        try:
                            await _compensate_faction_write(
                                faction_record,
                                relation_records,
                                binding_records,
                            )
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            logger.exception("势力更新失败且预镜像补偿失败")
                            raise RuntimeError(
                                "势力更新失败，且 standalone 补偿未完成"
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

        return await run_mongo_write_unit(_update, "update_faction_info")

    @staticmethod
    async def batch_update_sort_order(novel_id: str, items: list[dict[str, int | str]], *, session: AsyncClientSession | None=None) -> list[Dict[str, Any]]:
        """全有或全无地重排小说内完整活动核心势力集合。

        Args:
            novel_id: 小说 ObjectId 字符串。
            items: faction_id、expected_version 与 sort_order 组成的完整列表。

            session: 调用方事务；提供时不另开事务。

        Returns:
            按请求顺序返回递增版本后的完整势力列表。
        """
        normalized_items: list[dict[str, int | str]] = []
        for item in items:
            source = dict(item)
            faction_id = source.get("faction_id")
            expected_version = _validate_expected_faction_version(
                source.get("expected_version")
            )
            sort_order = source.get("sort_order")
            if (
                not isinstance(faction_id, str)
                or re.fullmatch(FACTION_BUSINESS_ID_PATTERN, faction_id) is None
            ):
                raise ValueError("排序 items 包含非法 faction_id")
            if (
                isinstance(sort_order, bool)
                or not isinstance(sort_order, int)
                or sort_order < 0
            ):
                raise ValueError("sort_order 必须为非负整数")
            normalized_items.append(
                {
                    "faction_id": faction_id,
                    "expected_version": expected_version,
                    "sort_order": sort_order,
                }
            )
        requested_ids = [str(item["faction_id"]) for item in normalized_items]
        if len(requested_ids) != len(set(requested_ids)):
            raise DuplicateKeyError("排序 items 不能重复 faction_id")
        requested_orders = [int(item["sort_order"]) for item in normalized_items]
        if len(requested_orders) != len(set(requested_orders)):
            raise DuplicateKeyError("活动核心势力 sort_order 必须互不重复")

        async def _update(
            session: AsyncClientSession | None,
        ) -> list[Dict[str, Any]]:
            """在一个写入单元内预检完整集合并逐项执行 CAS 排序。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await faction_repo.get_active_core_factions(
                novel_id,
                session=session,
            )
            current_by_id = {
                str(faction["faction_id"]): faction for faction in current
            }
            if set(requested_ids) != set(current_by_id):
                raise DuplicateKeyError(
                    "排序请求必须覆盖当前全部活动核心势力："
                    f"expected={sorted(current_by_id)}, actual={sorted(requested_ids)}"
                )
            for item in normalized_items:
                faction_id = str(item["faction_id"])
                expected_version = _validate_expected_faction_version(
                    item["expected_version"]
                )
                actual_version = int(current_by_id[faction_id]["version"])
                if expected_version != actual_version:
                    raise DuplicateKeyError(
                        f"势力 '{faction_id}' 版本冲突："
                        f"expected={expected_version}, actual={actual_version}"
                    )

            records: list[_CompensationRecord] = []
            updated_by_id: dict[str, dict[str, Any]] = {}
            try:
                for item in sorted(
                    normalized_items,
                    key=lambda value: str(value["faction_id"]),
                ):
                    faction_id = str(item["faction_id"])
                    written = await faction_repo.update_sort_order_cas(
                        novel_id,
                        faction_id,
                        int(item["expected_version"]),
                        int(item["sort_order"]),
                        session=session,
                    )
                    records.append(
                        _updated_compensation_record(
                            current_by_id[faction_id],
                            written,
                        )
                    )
                    updated_by_id[faction_id] = written

                after = await faction_repo.get_active_core_factions(
                    novel_id,
                    session=session,
                )
                after_by_id = {
                    str(faction["faction_id"]): faction for faction in after
                }
                expected_after = {
                    str(item["faction_id"]): (
                        int(item["expected_version"]) + 1,
                        int(item["sort_order"]),
                    )
                    for item in normalized_items
                }
                actual_after = {
                    faction_id: (
                        int(faction["version"]),
                        int(faction.get("sort_order") or 0),
                    )
                    for faction_id, faction in after_by_id.items()
                }
                if actual_after != expected_after:
                    raise DuplicateKeyError(
                        "势力排序期间活动核心集合已并发变化，请刷新后重试"
                    )
                return [updated_by_id[faction_id] for faction_id in requested_ids]
            except Exception:
                if session is None and records:
                    try:
                        await _restore_snapshots(faction_repo, records)
                    except Exception as compensation_exc:
                        raise RuntimeError(
                            "势力排序失败，且 standalone 补偿未完成"
                        ) from compensation_exc
                raise

        if session is not None:
            return await _update(session)

        return await run_mongo_write_unit(_update, "batch_update_faction_sort_order")

    @staticmethod
    async def soft_delete_faction(novel_id: str, faction_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """软删除阵营，并解除同小说下子阵营挂靠。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            expected_version: 客户端基于的势力版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            软删除并递增版本后的完整势力文档。
        """
        async def _delete(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在同一个写入单元内软删除势力并阻断全部未删除依赖。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                current = await _get_versioned_faction(
                    novel_id,
                    faction_id,
                    expected_version,
                    deleted=False,
                    session=session,
                )
                relation_snapshots = await _load_faction_relations(
                    novel_id,
                    faction_id,
                    include_deleted=False,
                    session=session,
                )
                binding_snapshots = await _load_faction_bindings(
                    novel_id,
                    faction_id,
                    include_deleted=False,
                    session=session,
                )
                child_snapshots = await _load_child_factions(
                    novel_id,
                    faction_id,
                    session=session,
                )
                _raise_if_has_child_factions(child_snapshots)
                faction_record: _CompensationRecord | None = None
                relation_records: list[_CompensationRecord] = []
                binding_records: list[_CompensationRecord] = []
                state_changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                try:
                    now = get_utc_now()
                    deleted = await _cas_update_faction_snapshot(
                        current,
                        {
                            "is_deleted": True,
                            "deleted_at": now,
                            "deletion_sources": list(
                                dict.fromkeys(
                                    [
                                        *(
                                            current.get("deletion_sources")
                                            if isinstance(
                                                current.get("deletion_sources"),
                                                list,
                                            )
                                            else []
                                        ),
                                        "user",
                                    ]
                                )
                            ),
                        },
                        session=session,
                    )
                    faction_record = _updated_compensation_record(current, deleted)
                    await _apply_faction_relation_changes(
                        relation_snapshots,
                        faction_id,
                        projected_name=None,
                        available=False,
                        applied_snapshots=relation_records,
                        session=session,
                    )
                    await _apply_faction_binding_availability(
                        binding_snapshots,
                        faction_id,
                        available=False,
                        applied_snapshots=binding_records,
                        session=session,
                    )
                    latest_relations = await _load_faction_relations(
                        novel_id,
                        faction_id,
                        include_deleted=False,
                        session=session,
                    )
                    latest_bindings = await _load_faction_bindings(
                        novel_id,
                        faction_id,
                        include_deleted=False,
                        session=session,
                    )
                    await _apply_faction_relation_changes(
                        latest_relations,
                        faction_id,
                        projected_name=None,
                        available=False,
                        applied_snapshots=relation_records,
                        session=session,
                    )
                    await _apply_faction_binding_availability(
                        latest_bindings,
                        faction_id,
                        available=False,
                        applied_snapshots=binding_records,
                        session=session,
                    )
                    state_changes = (
                        await FactionVolumeStateService.add_faction_deletion_source(
                            novel_id,
                            faction_id,
                            session=session,
                        )
                    )
                    logger.info("软删除势力 %s 完成", faction_id)
                    return deleted
                except Exception as exc:
                    if isinstance(exc, FactionStateSourceCompensationError):
                        state_lock_releasable = False
                    if session is None and faction_record is not None:
                        try:
                            if state_changes:
                                await compensate_faction_state_changes(state_changes)
                            await _compensate_faction_write(
                                faction_record,
                                relation_records,
                                binding_records,
                            )
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            logger.exception("势力软删除失败且预镜像补偿失败")
                            raise RuntimeError(
                                "势力软删除失败，且 standalone 补偿未完成"
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

        return await run_mongo_write_unit(_delete, "soft_delete_faction")

    @staticmethod
    async def restore_faction(novel_id: str, faction_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """恢复已软删除的阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            expected_version: 客户端基于的势力版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            恢复并递增版本后的完整势力文档。
        """
        async def _restore(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在同一个写入单元内恢复势力并重算全部依赖有效态。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                deleted_faction = await _get_versioned_faction(
                    novel_id,
                    faction_id,
                    expected_version,
                    deleted=True,
                    session=session,
                )
                await FactionService._validate_scope_and_parent(
                    novel_id,
                    level_type=deleted_faction["level_type"],
                    volume_id=(
                        str(deleted_faction["volume_id"])
                        if deleted_faction.get("volume_id") is not None
                        else None
                    ),
                    parent_faction_id=deleted_faction.get("parent_faction_id"),
                    faction_id=faction_id,
                    session=session,
                )
                deletion_sources = list(
                    dict.fromkeys(deleted_faction.get("deletion_sources") or [])
                )
                if "user" not in deletion_sources:
                    raise DomainApiError(
                        "FACTION_USER_SOURCE_MISSING",
                        "势力没有可恢复的用户删除来源",
                        status_code=409,
                    )
                remaining_sources = [
                    source for source in deletion_sources if source != "user"
                ]
                relation_should_unblock = bool(
                    not remaining_sources
                    and deleted_faction.get("active_status") == "active"
                )
                if relation_should_unblock:
                    await FactionService._ensure_unique_active_name(
                        novel_id,
                        str(deleted_faction.get("name", "")),
                        level_type=deleted_faction["level_type"],
                        volume_id=deleted_faction.get("volume_id"),
                        session=session,
                    )
                binding_should_unblock = bool(
                    relation_should_unblock
                    and deleted_faction["level_type"] == "core"
                )
                if relation_should_unblock:
                    await FactionRelationService.validate_faction_unblock(
                        novel_id,
                        faction_id,
                        session=session,
                    )
                if binding_should_unblock:
                    await _validate_faction_binding_unblock(
                        novel_id,
                        faction_id,
                        session=session,
                    )
                relation_snapshots = await _load_faction_relations(
                    novel_id,
                    faction_id,
                    include_deleted=False,
                    session=session,
                )
                binding_snapshots = await _load_faction_bindings(
                    novel_id,
                    faction_id,
                    include_deleted=False,
                    session=session,
                )
                faction_record: _CompensationRecord | None = None
                relation_records: list[_CompensationRecord] = []
                binding_records: list[_CompensationRecord] = []
                state_changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                try:
                    restored = await _cas_update_faction_snapshot(
                        deleted_faction,
                        {
                            "is_deleted": bool(remaining_sources),
                            "deleted_at": (
                                deleted_faction.get("deleted_at")
                                if remaining_sources
                                else None
                            ),
                            "deletion_sources": remaining_sources,
                        },
                        session=session,
                    )
                    faction_record = _updated_compensation_record(deleted_faction, restored)
                    await _apply_faction_relation_changes(
                        relation_snapshots,
                        faction_id,
                        projected_name=None,
                        available=relation_should_unblock,
                        applied_snapshots=relation_records,
                        session=session,
                    )
                    await _apply_faction_binding_availability(
                        binding_snapshots,
                        faction_id,
                        available=binding_should_unblock,
                        applied_snapshots=binding_records,
                        session=session,
                    )
                    latest_relations = await _load_faction_relations(
                        novel_id,
                        faction_id,
                        include_deleted=False,
                        session=session,
                    )
                    latest_bindings = await _load_faction_bindings(
                        novel_id,
                        faction_id,
                        include_deleted=False,
                        session=session,
                    )
                    await _apply_faction_relation_changes(
                        latest_relations,
                        faction_id,
                        projected_name=None,
                        available=relation_should_unblock,
                        applied_snapshots=relation_records,
                        session=session,
                    )
                    await _apply_faction_binding_availability(
                        latest_bindings,
                        faction_id,
                        available=binding_should_unblock,
                        applied_snapshots=binding_records,
                        session=session,
                    )
                    state_changes = (
                        await FactionVolumeStateService.remove_faction_deletion_source(
                            novel_id,
                            faction_id,
                            session=session,
                        )
                    )
                    logger.info("恢复势力 %s 完成", faction_id)
                    return restored
                except Exception as exc:
                    if isinstance(exc, FactionStateSourceCompensationError):
                        state_lock_releasable = False
                    if session is None and faction_record is not None:
                        try:
                            if state_changes:
                                await compensate_faction_state_changes(state_changes)
                            await _compensate_faction_write(
                                faction_record,
                                relation_records,
                                binding_records,
                            )
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            logger.exception("势力恢复失败且预镜像补偿失败")
                            raise RuntimeError(
                                "势力恢复失败，且 standalone 补偿未完成"
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

        return await run_mongo_write_unit(_restore, "restore_faction")

    @staticmethod
    async def hard_delete_faction(
        novel_id: str,
        faction_id: str,
        *,
        expected_version: int,
    ) -> Dict[str, Any]:
        """物理删除已软删除的阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            expected_version: 客户端基于的势力版本。

        Returns:
            删除统计。
        """
        async def _delete(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在同一个写入单元内按预镜像版本物理删除势力及全部引用。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                pending_location_references = await BaseRepository(
                    "locations"
                ).count_documents(
                    {
                        "novel_id": to_object_id(novel_id),
                        "associated_faction_ids": faction_id,
                        "location_order_pending_token": {"$type": "string"},
                    },
                    session=session,
                )
                if pending_location_references:
                    # 待提交地点不是公开事实，只阻断删除而不返回其数量或业务 ID。
                    raise DomainApiError(
                        "FACTION_LOCATION_WRITE_CONFLICT",
                        "地点写入正在使用该势力，请稍后重试",
                        status_code=409,
                    )
                referencing_locations = await BaseRepository("locations").find_many(
                    {
                        "novel_id": to_object_id(novel_id),
                        "associated_faction_ids": faction_id,
                        "location_order_pending_token": None,
                    },
                    sort=[("location_id", 1)],
                    session=session,
                )
                if referencing_locations:
                    location_ids = [
                        str(item["location_id"]) for item in referencing_locations
                    ]
                    raise DomainApiError(
                        "FACTION_LOCATION_REFERENCE_PROTECTED",
                        "势力仍被正式地点引用，不能永久删除",
                        status_code=409,
                        details={
                            "location_ids": location_ids,
                            "count": len(location_ids),
                        },
                    )
                item_lock = await acquire_item_write_lock(novel_id, session=session)
                item_lock_releasable = True
                try:
                    deleted_faction = await _get_versioned_faction(
                        novel_id,
                        faction_id,
                        expected_version,
                        deleted=True,
                        session=session,
                    )
                    # 回收站篇章仍可恢复，必须保留它引用的势力。
                    referencing_arcs = await BaseRepository("arcs").find_many(
                        {
                            "novel_id": to_object_id(novel_id),
                            "planning.faction_ids": faction_id,
                        },
                        include_deleted=True,
                        sort=[("_id", 1)],
                        session=session,
                    )
                    if referencing_arcs:
                        arc_ids = [str(arc["_id"]) for arc in referencing_arcs]
                        raise DomainApiError(
                            "ARC_FACTION_REFERENCE_PROTECTED",
                            "势力仍被篇章引用，请先移除引用再永久删除",
                            status_code=409,
                            details={"arc_ids": arc_ids, "count": len(arc_ids)},
                        )
                    referencing_scenes = await BaseRepository("scenes").find_many(
                        {"novel_id": to_object_id(novel_id), "planning.faction_ids": faction_id},
                        include_deleted=True, sort=[("_id", 1)], session=session,
                    )
                    if referencing_scenes:
                        raise DomainApiError(
                            "SCENE_FACTION_REFERENCE_PROTECTED",
                            "势力仍被场景引用，请先移除引用再永久删除",
                            status_code=409,
                            details={"scene_ids": [str(item["_id"]) for item in referencing_scenes], "count": len(referencing_scenes)},
                        )
                    state_references = await BaseRepository(
                        "faction_volume_states"
                    ).find_many(
                        {
                            "novel_id": to_object_id(novel_id),
                            "faction_id": faction_id,
                        },
                        include_deleted=True,
                        sort=[("state_id", 1)],
                        session=session,
                    )
                    if state_references:
                        raise DomainApiError(
                            "FACTION_VOLUME_STATE_REFERENCE_PROTECTED",
                            "势力仍有卷级状态，不能永久删除",
                            status_code=409,
                            details={
                                "state_ids": [
                                    str(state["state_id"]) for state in state_references
                                ],
                                "count": len(state_references),
                            },
                        )
                    pending_item_references = await BaseRepository("items").count_documents(
                        {
                            "novel_id": to_object_id(novel_id),
                            "controlling_faction_id": faction_id,
                            "item_write_pending_token": {"$type": "string"},
                        },
                        session=session,
                    )
                    if pending_item_references:
                        raise DomainApiError(
                            "FACTION_ITEM_WRITE_CONFLICT",
                            "物品写入正在使用该势力，请稍后重试",
                            status_code=409,
                        )
                    referencing_items = await BaseRepository("items").find_many(
                        {
                            "novel_id": to_object_id(novel_id),
                            "controlling_faction_id": faction_id,
                            "item_write_pending_token": None,
                        },
                        sort=[("item_id", 1)],
                        session=session,
                    )
                    if referencing_items:
                        item_ids = [str(item["item_id"]) for item in referencing_items]
                        raise DomainApiError(
                            "FACTION_ITEM_REFERENCE_PROTECTED",
                            "势力仍被正式物品引用，不能永久删除",
                            status_code=409,
                            details={"item_ids": item_ids, "count": len(item_ids)},
                        )
                    relation_snapshots = await _load_faction_relations(
                        novel_id,
                        faction_id,
                        include_deleted=True,
                        session=session,
                    )
                    binding_snapshots = await _load_faction_bindings(
                        novel_id,
                        faction_id,
                        include_deleted=True,
                        session=session,
                    )
                    child_snapshots = await _load_child_factions(
                        novel_id,
                        faction_id,
                        session=session,
                    )
                    _raise_if_has_child_factions(child_snapshots)
                    deleted_relations: list[_CompensationRecord] = []
                    deleted_bindings: list[_CompensationRecord] = []
                    faction_record: _CompensationRecord | None = None
                    try:
                        relations_deleted = await _delete_snapshots_exact(
                            _faction_relation_base_repo,
                            relation_snapshots,
                            deleted_snapshots=deleted_relations,
                            session=session,
                        )
                        bindings_deleted = await _delete_snapshots_exact(
                            _faction_binding_base_repo,
                            binding_snapshots,
                            deleted_snapshots=deleted_bindings,
                            session=session,
                        )
                        delete_result = await faction_repo.collection.delete_one(
                            {
                                "_id": deleted_faction["_id"],
                                **_snapshot_version_query(deleted_faction),
                                "is_deleted": True,
                                DEPENDENCY_GUARD_FIELD: deleted_faction.get(
                                    DEPENDENCY_GUARD_FIELD,
                                    0,
                                ),
                            },
                            session=session,
                        )
                        if delete_result.deleted_count != 1:
                            raise DuplicateKeyError("势力已被其他请求修改，请刷新后重试")
                        faction_record = _deleted_compensation_record(deleted_faction)
                        stats = {
                            "faction_deleted": 1,
                            "children_unlinked": 0,
                            "relations_deleted": relations_deleted,
                            "bindings_deleted": bindings_deleted,
                        }
                        logger.info("硬删除势力 %s 完成: %s", faction_id, stats)
                        return stats
                    except Exception:
                        if session is None and (
                            faction_record is not None
                            or deleted_relations
                            or deleted_bindings
                        ):
                            try:
                                await _compensate_faction_write(
                                    faction_record,
                                    deleted_relations,
                                    deleted_bindings,
                                )
                            except Exception as compensation_exc:
                                item_lock_releasable = False
                                state_lock_releasable = False
                                logger.exception("势力硬删除失败且预镜像补偿失败")
                                raise RuntimeError(
                                    "势力硬删除失败，且 standalone 补偿未完成"
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

        return await run_mongo_write_unit(_delete, "hard_delete_faction")
