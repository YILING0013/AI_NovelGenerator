"""全书级角色关系领域服务。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError, VersionConflictError
from backend.db.endpoint_guard import (
    DependencyGuardContribution,
    rollback_dependency_endpoint_guards,
    touch_dependency_endpoint_guards,
)
from backend.db.repositories.character_relation_repository import character_relation_repo
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import to_object_id
from backend.llm.schemas.character_relation_pydantic import (
    CharacterRelationDesignUpdateRequestV1,
    CharacterRelationsAIConfirmationRequestV1,
)
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import (
    checksum,
    hash_idempotency_key,
)
from backend.services.novel.character_service import (
    _restore_snapshots,
    _updated_compensation_record,
)
from backend.services.novel.character_volume_state_service import (
    CharacterVolumeStateService,
    acquire_state_write_lock,
    release_state_write_lock,
)
from backend.services.novel.chapter_record_source import protect_chapter_record_sources


RELATION_TYPES = frozenset(
    {
        "friend",
        "romantic",
        "ally",
        "rival",
        "enemy",
        "parent_of",
        "mentor_of",
        "superior_of",
        "protector_of",
        "debtor_to",
    }
)
SYMMETRIC_RELATION_TYPES = frozenset({"friend", "romantic", "ally", "rival", "enemy"})
RELATION_CONTENT_FIELDS = (
    "relation_type",
    "current_state",
    "core_conflict",
    "hidden_tension",
    "possible_change",
    "story_value",
    "intensity",
)


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    """将 Pydantic 模型或普通映射转换为独立字典。

    Args:
        payload: Pydantic V2 模型或可转换为 dict 的关系载荷。

    Returns:
        不与调用方共享可变状态的字典。
    """
    if hasattr(payload, "model_dump"):
        return dict(payload.model_dump(mode="json"))
    return dict(payload)


def _normalize_scalar(value: Any) -> Any:
    """把枚举值转换为其公开字符串值。

    Args:
        value: 任意字段值。

    Returns:
        Enum 的 value 或原始值。
    """
    return value.value if isinstance(value, Enum) else value


def normalize_relation_endpoints(
    source_character_id: str,
    target_character_id: str,
    relation_type: str,
) -> tuple[str, str]:
    """按关系方向规则生成稳定语义端点。

    Args:
        source_character_id: 来源角色业务 ID。
        target_character_id: 目标角色业务 ID。
        relation_type: 角色关系类型。

    Returns:
        用于去重与唯一索引的规范化 source、target 元组。
    """
    if relation_type in SYMMETRIC_RELATION_TYPES:
        return tuple(sorted((source_character_id, target_character_id)))
    return source_character_id, target_character_id


def _character_endpoint_signature(
    character: dict[str, Any],
) -> tuple[Any, Any, str, bool, bool]:
    """生成不含内部 guard revision 的角色端点业务签名。

    Args:
        character: 同小说作用域内的角色主档。

    Returns:
        身份、公开版本、状态、核心标记和删除态组成的签名。
    """
    return (
        character.get("_id"),
        character["version"],
        str(character.get("status")),
        character.get("is_core_character") is True,
        character.get("is_deleted") is True,
    )


async def _load_character_endpoint_signatures(
    novel_id: str,
    character_ids: list[str],
    *,
    require_usable: bool,
    session: AsyncClientSession | None,
) -> dict[str, tuple[Any, Any, str, bool, bool]]:
    """读取人物关系端点并生成可用于写后复核的业务签名。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        character_ids: 稳定角色业务 ID。
        require_usable: 是否要求端点为未删除 active 角色。
        session: 可选 MongoDB 会话。

    Returns:
        角色 ID 到业务签名的映射。
    """
    by_id: dict[str, dict[str, Any]] = {}
    for character_id in character_ids:
        try:
            by_id[character_id] = await character_repo.get_character(
                novel_id,
                character_id,
                include_deleted=True,
                session=session,
            )
        except NotFoundError as exc:
            raise NotFoundError(f"角色端点 {character_id} 不存在于当前小说") from exc
    invalid = [
        character_id
        for character_id, character in by_id.items()
        if require_usable
        and (
            character.get("status") != "active"
            or character.get("is_deleted") is True
        )
    ]
    if invalid:
        raise ValueError("角色关系端点当前不可用: " + ", ".join(invalid))
    return {
        character_id: _character_endpoint_signature(by_id[character_id])
        for character_id in character_ids
    }


async def _touch_character_endpoint_signatures(
    signatures: dict[
        str,
        tuple[Any, Any, str, bool, bool],
    ],
    *,
    session: AsyncClientSession | None,
) -> list[DependencyGuardContribution]:
    """按角色端点业务签名推进内部依赖护栏。

    Args:
        signatures: 写入前读取的角色端点业务签名。
        session: 可选 MongoDB 会话。

    Returns:
        每个端点业务查询及其 touch 前 guard 基线，供失败补偿使用。
    """
    queries = [
        {
            "_id": signature[0],
            "character_id": character_id,
            "version": signature[1],
            "status": signature[2],
            "is_core_character": True if signature[3] else {"$ne": True},
            "is_deleted": True if signature[4] else {"$ne": True},
        }
        for character_id, signature in signatures.items()
    ]
    return await touch_dependency_endpoint_guards(
        character_repo.collection,
        queries,
        session=session,
    )


async def _compensate_character_relation_update(
    snapshot: dict[str, Any],
    written: dict[str, Any],
) -> None:
    """精确回滚 standalone 人物关系写入且不覆盖并发新版本。

    Args:
        snapshot: 人物关系写入前预镜像。
        written: 本次 CAS 写入返回的写后文档。

    Returns:
        无；仍处于本次写后版本时恢复预镜像。
    """
    await _restore_snapshots(
        character_relation_repo,
        [_updated_compensation_record(snapshot, written)],
    )


class CharacterRelationService:
    """校验全书级角色端点并维护规范化关系边。"""

    @staticmethod
    def _ensure_expected_version(relation: dict[str, Any], expected_version: int) -> None:
        """在执行引用校验前快速拒绝明显过期的关系版本。

        Args:
            relation: 当前数据库关系文档。
            expected_version: 调用方提交的版本。

        Returns:
            无；版本一致时正常返回。
        """
        actual_version = int(relation["version"])
        if actual_version != expected_version:
            raise VersionConflictError(
                f"角色关系 '{relation.get('relation_id')}' 版本冲突："
                f"expected={expected_version}, actual={actual_version}"
            )

    @staticmethod
    async def validate_generation_candidates(
        novel_id: str,
        candidates: list[Any],
        selected_character_ids: list[str] | tuple[str, ...],
        *,
        raise_on_conflict: bool = False,
        require_active: bool = True,
        require_core_endpoints: bool = True,
        check_active_semantic: bool = True,
        exclude_relation_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[str]:
        """执行生成关系候选的端点、枚举、覆盖范围和语义冲突校验。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            candidates: 待校验的关系候选或正式创建载荷。
            selected_character_ids: 本次请求锁定的角色 ID 白名单。
            raise_on_conflict: 是否把重复语义边立即作为 409 领域冲突抛出。
            require_active: 是否要求每个载荷的用户启停意图必须为 true。
            require_core_endpoints: 是否要求每个端点同时具备核心角色身份。
            check_active_semantic: 是否检查与现有活动语义边的冲突。
            exclude_relation_id: 更新时从冲突查询中排除的当前关系 ID。
            session: 可选 MongoDB 会话。

        Returns:
            稳定顺序的业务校验错误列表；空列表表示全部通过。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        payloads = [_payload_to_dict(candidate) for candidate in candidates]
        selected_ids = set(dict.fromkeys(selected_character_ids))
        endpoint_ids = {
            str(payload.get(field) or "")
            for payload in payloads
            for field in ("source_character_id", "target_character_id")
            if payload.get(field)
        }
        characters = await character_repo.get_characters_by_ids(
            novel_id,
            sorted(endpoint_ids),
            session=session,
        )
        characters_by_id = {str(character["character_id"]): character for character in characters}
        missing_endpoint_ids = sorted(endpoint_ids - set(characters_by_id))
        if missing_endpoint_ids:
            raise NotFoundError(
                "角色关系端点不存在于当前小说: " + ", ".join(missing_endpoint_ids)
            )

        errors: list[str] = []
        conflict_errors: list[str] = []
        semantic_owner: dict[tuple[str, str, str], str] = {}
        candidate_semantics: list[tuple[str, str, str]] = []
        semantic_labels: list[str] = []

        for index, payload in enumerate(payloads):
            label = str(payload.get("relation_ref") or f"relations[{index}]")
            source_id = str(payload.get("source_character_id") or "")
            target_id = str(payload.get("target_character_id") or "")
            relation_type = str(_normalize_scalar(payload.get("relation_type")) or "")
            intensity = payload.get("intensity")

            if not source_id or not target_id:
                errors.append(f"{label}: source_character_id 与 target_character_id 均为必填")
                continue
            if source_id == target_id:
                errors.append(f"{label}: 角色关系不允许自引用 {source_id}")
            if source_id not in selected_ids or target_id not in selected_ids:
                errors.append(f"{label}: 关系端点必须来自本次锁定的角色白名单")
            if relation_type not in RELATION_TYPES:
                errors.append(f"{label}: 不支持的 relation_type={relation_type}")
            if isinstance(intensity, bool) or not isinstance(intensity, int) or not 1 <= intensity <= 5:
                errors.append(f"{label}: intensity 必须为 1 至 5 的整数")
            candidate_is_active = payload.get("is_active", True) is True
            if require_active and not candidate_is_active:
                errors.append(f"{label}: 新生成关系的 is_active 必须为 true")
            for field_name in (
                "current_state",
                "core_conflict",
                "hidden_tension",
                "possible_change",
                "story_value",
            ):
                text_value = payload.get(field_name)
                if not isinstance(text_value, str) or not 1 <= len(text_value.strip()) <= 2000:
                    errors.append(f"{label}: {field_name} 必须为 1 至 2000 字符的非空文本")

            for endpoint_id in (source_id, target_id):
                character = characters_by_id.get(endpoint_id)
                if character is None:
                    errors.append(f"{label}: 角色端点 {endpoint_id} 不存在于当前小说")
                    continue
                if character.get("status") != "active" or character.get("is_deleted") is True:
                    errors.append(f"{label}: 角色端点 {endpoint_id} 必须是 active 未删除角色")
                elif require_core_endpoints and character.get("is_core_character") is not True:
                    errors.append(f"{label}: 角色端点 {endpoint_id} 必须是 active 核心角色")

            if (
                relation_type in RELATION_TYPES
                and source_id
                and target_id
                and source_id != target_id
                and candidate_is_active
                and check_active_semantic
            ):
                normalized_source, normalized_target = normalize_relation_endpoints(
                    source_id,
                    target_id,
                    relation_type,
                )
                semantic = (normalized_source, normalized_target, relation_type)
                previous_label = semantic_owner.get(semantic)
                if previous_label is not None:
                    message = f"{label}: 与 {previous_label} 构成重复语义关系"
                    errors.append(message)
                    conflict_errors.append(message)
                else:
                    semantic_owner[semantic] = label
                candidate_semantics.append(semantic)
                semantic_labels.append(label)

        existing_relations = await character_relation_repo.find_active_semantic_relations(
            novel_id,
            candidate_semantics,
            exclude_relation_id=exclude_relation_id,
            session=session,
        )
        existing_semantics = {
            (
                str(relation["normalized_source_character_id"]),
                str(relation["normalized_target_character_id"]),
                str(relation["relation_type"]),
            ): str(relation["relation_id"])
            for relation in existing_relations
        }
        for label, semantic in zip(semantic_labels, candidate_semantics):
            conflicting_relation_id = existing_semantics.get(semantic)
            if conflicting_relation_id:
                message = f"{label}: 与既有活动关系 {conflicting_relation_id} 语义重复"
                errors.append(message)
                conflict_errors.append(message)

        if raise_on_conflict and conflict_errors:
            raise DuplicateKeyError("角色关系语义冲突: " + "; ".join(conflict_errors))
        return errors

    @staticmethod
    async def bulk_append_relations(novel_id: str, result: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """只回放能够完整证明的旧关系批次，不再续建缺失关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            result: 原人工或 AI 确认请求，不补字段或更换 local ref。
            idempotency_key: 原批量追加幂等键。
            session: 可选调用方事务。
        Returns:
            按原候选顺序返回全部既有关系；证据缺失时明确拒绝。
        """
        source = _payload_to_dict(result)
        is_ai_confirmation = source.get("request_type") == "ai_confirmation"
        if is_ai_confirmation:
            source = CharacterRelationsAIConfirmationRequestV1.model_validate(
                source
            ).model_dump(mode="json")
            all_candidates = {
                str(candidate["relation_ref"]): _payload_to_dict(candidate)
                for candidate in source.get("candidate", {}).get("relations", [])
            }
            selected_refs = list(source.get("selected_relation_refs") or [])
            normalized_candidates = [all_candidates[ref] for ref in selected_refs]
        else:
            normalized_candidates = [
                _payload_to_dict(candidate)
                for candidate in source.get("relations", [])
            ]
            for index, candidate in enumerate(normalized_candidates, start=1):
                candidate["relation_ref"] = f"relation_{index:03d}"
        if not normalized_candidates:
            raise ValueError("至少需要一条角色关系")
        relation_refs = [str(candidate["relation_ref"]) for candidate in normalized_candidates]
        if len(relation_refs) != len(set(relation_refs)):
            raise ValueError("角色关系 local ref 不能重复")

        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "request": source})

        existing = await character_relation_repo.find_by_batch_idempotency(
            novel_id, key_hash, session=session,
        )
        if any(item.get("batch_request_hash") != request_hash for item in existing):
            raise GenerationDomainError(
                "IDEMPOTENCY_KEY_REUSED",
                "同一 Idempotency-Key 已用于不同的角色关系批量请求",
                status_code=409,
            )
        by_ref = {str(item.get("batch_local_ref")): item for item in existing if item.get("batch_local_ref")}
        if len(by_ref) != len(existing):
            raise DuplicateKeyError("角色关系批次 local ref 元数据冲突")
        if set(by_ref) - set(relation_refs):
            raise GenerationDomainError(
                "IDEMPOTENCY_KEY_REUSED",
                "同一 Idempotency-Key 的既有角色关系映射与当前请求不一致",
                status_code=409,
            )
        if set(by_ref) != set(relation_refs):
            # 部分行可能来自旧中断，也可能是成功后被硬删，不能补建或猜测整批成功。
            raise DomainApiError(
                "CHARACTER_RELATION_FACT_REQUIRED",
                "旧批次没有完整成功记录，请保留原请求；新关系请逐条设置明确起点后确认",
                status_code=409,
            )
        return {
            "character_relations": [by_ref[ref] for ref in relation_refs],
            "relation_ref_map": {ref: str(by_ref[ref]["relation_id"]) for ref in relation_refs} if is_ai_confirmation else {},
        }

    @staticmethod
    async def create_relation(
        novel_id: str, payload: Any, *, idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """只回放旧人工创建的既有关系，新关系须由作者确认明确起点。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            payload: 原角色关系创建 DTO 或等价映射。
            idempotency_key: 原创建幂等键。
            session: 可选调用方事务。
        Returns:
            原键仍可查询的关系行；没有成功证据时明确拒绝。
        """
        source = _payload_to_dict(payload)
        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "payload": source})
        existing = await character_relation_repo.find_by_creation_idempotency(
            novel_id, key_hash, session=session,
        )
        if existing is not None:
            if existing.get("creation_request_hash") != request_hash:
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的角色关系创建请求",
                    status_code=409,
                )
            return existing
        raise DomainApiError(
            "CHARACTER_RELATION_FACT_REQUIRED",
            "没有找到旧创建的成功记录，请保留原请求；新关系请设置明确起点后确认",
            status_code=409,
        )

    @staticmethod
    async def get_relation(
        novel_id: str,
        relation_id: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """读取指定小说内的一条角色关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            角色关系文档。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_relation_repo.get_relation(novel_id, relation_id, session=session)

    @staticmethod
    async def list_relations(
        novel_id: str,
        *,
        character_id: str | None = None,
        relation_type: str | None = None,
        is_active: bool | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出小说内角色关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 可选角色端点业务 ID。
            relation_type: 可选关系类型。
            is_active: 可选活动状态过滤。
            session: 可选 MongoDB 会话。

        Returns:
            稳定排序的角色关系文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        if relation_type is not None and relation_type not in RELATION_TYPES:
            raise ValueError(f"不支持的 relation_type={relation_type}")
        if character_id:
            # 查询过滤只校验端点属于当前小说；非核心或暂时停用角色的历史关系仍可读取。
            await character_repo.get_character(novel_id, character_id, session=session)
        return await character_relation_repo.list_relations(
            novel_id,
            character_id=character_id,
            relation_type=relation_type,
            is_active=is_active,
            session=session,
        )

    @staticmethod
    async def _validate_persisted_relation(
        novel_id: str,
        relation: dict[str, Any],
        *,
        relation_type: str,
        should_be_active: bool,
        require_active_endpoints: bool,
        session: AsyncClientSession | None,
    ) -> tuple[str, str]:
        """复核既有关系端点并计算新的规范化端点。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation: 当前关系文档。
            relation_type: 待保存的关系类型。
            should_be_active: 保存后是否会成为活动关系。
            require_active_endpoints: 是否要求两端当前均为 active。
            session: 可选 MongoDB 会话。

        Returns:
            规范化来源与目标角色业务 ID。
        """
        source_id = str(relation["source_character_id"])
        target_id = str(relation["target_character_id"])
        if source_id == target_id:
            raise ValueError("角色关系不能指向自身")
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"不支持的 relation_type={relation_type}")
        for endpoint_id in (source_id, target_id):
            try:
                character = await character_repo.get_character(
                    novel_id,
                    endpoint_id,
                    include_deleted=True,
                    session=session,
                )
            except NotFoundError as exc:
                raise ValueError(f"角色端点 {endpoint_id} 不存在于当前小说") from exc
            if require_active_endpoints and (
                character.get("is_deleted") is True
                or character.get("status") != "active"
            ):
                raise ValueError(f"角色端点 {endpoint_id} 当前不可用，关系无法启用")

        normalized = normalize_relation_endpoints(source_id, target_id, relation_type)
        if should_be_active:
            conflicts = await character_relation_repo.find_active_semantic_relations(
                novel_id,
                [(normalized[0], normalized[1], relation_type)],
                exclude_relation_id=str(relation["relation_id"]),
                session=session,
            )
            if conflicts:
                raise DuplicateKeyError(
                    f"角色关系与既有活动关系 {conflicts[0]['relation_id']} 语义重复"
                )
        return normalized

    @staticmethod
    async def update_relation(novel_id: str, relation_id: str, payload: Any, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """编辑尚未认领的旧关系原文，端点与稳定业务 ID 保持不可变。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            payload: 已通过严格 Schema 校验的内容更新请求。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            递增版本后的完整关系文档。
        """
        from backend.services.novel.character_relation_fact_service import ensure_character_relation_state_unmanaged

        source = _payload_to_dict(payload)
        expected_version = int(source.pop("expected_version"))

        async def _update(session: AsyncClientSession) -> dict[str, Any]:
            """在一个写入单元内复核引用并执行 CAS 更新。"""
            await ensure_character_relation_state_unmanaged(novel_id, [relation_id], session=session)
            current = await character_relation_repo.get_relation(
                novel_id,
                relation_id,
                session=session,
            )
            CharacterRelationService._ensure_expected_version(current, expected_version)
            update_fields = {field: source[field] for field in RELATION_CONTENT_FIELDS}
            for field in (
                "current_state",
                "core_conflict",
                "hidden_tension",
                "possible_change",
                "story_value",
            ):
                update_fields[field] = str(update_fields[field]).strip()
            relation_type = str(_normalize_scalar(update_fields["relation_type"]))
            update_fields["relation_type"] = relation_type

            validation_view = {**current, **update_fields}
            remains_active = bool(current.get("is_active"))
            normalized_source, normalized_target = (
                await CharacterRelationService._validate_persisted_relation(
                    novel_id,
                    validation_view,
                    relation_type=relation_type,
                    should_be_active=remains_active,
                    require_active_endpoints=remains_active,
                    session=session,
                )
            )
            update_fields.update(
                {
                    "normalized_source_character_id": normalized_source,
                    "normalized_target_character_id": normalized_target,
                    "semantic_key": (
                        f"{normalized_source}:{normalized_target}:{relation_type}"
                    ),
                }
            )
            endpoint_ids = [
                str(current["source_character_id"]),
                str(current["target_character_id"]),
            ]
            endpoint_signatures = None
            if remains_active:
                endpoint_signatures = await _load_character_endpoint_signatures(
                    novel_id,
                    endpoint_ids,
                    require_usable=True,
                    session=session,
                )
                await _touch_character_endpoint_signatures(
                    endpoint_signatures,
                    session=session,
                )
            written = await character_relation_repo.update_relation(
                novel_id,
                relation_id,
                update_fields,
                expected_version,
                session=session,
            )
            if endpoint_signatures is not None:
                current_signatures = await _load_character_endpoint_signatures(
                    novel_id,
                    endpoint_ids,
                    require_usable=True,
                    session=session,
                )
                if current_signatures != endpoint_signatures:
                    raise DuplicateKeyError(
                        "角色关系更新期间端点已被并发修改，请重试"
                    )
            return written

        if session is not None:
            if not session.in_transaction:
                raise RuntimeError("旧关系原文保存必须在调用方事务内执行")
            return await _update(session)

        return await run_mongo_write_unit(_update, "update_character_relation", require_transaction=True)

    @staticmethod
    async def update_relation_design(
        novel_id: str, relation_id: str, payload: Any,
        *, session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按原版本保存六个设计字段，保留端点和裸状态。

        Args:
            novel_id: 当前小说的物理 ID。
            relation_id: 原关系的稳定业务 ID。
            payload: 六个设计字段及作者开始编辑时的版本。
            session: 调用方的保存事务；省略时开启必需事务。

        Returns:
            版本递增一次后的完整关系文档。
        """
        request = CharacterRelationDesignUpdateRequestV1.model_validate(payload)
        update_fields = request.model_dump(exclude={"expected_version"})

        async def _update(write_session: AsyncClientSession) -> dict[str, Any]:
            """把小说、两端保护和设计更新放在同一事务。"""
            novel = await novel_repo.get_novel_by_id(novel_id, session=write_session)
            # 空事实范围也与新确认争用小说，不能只保护当前关系和两端。
            await protect_chapter_record_sources(
                {("novels", novel_id): novel}, session=write_session,
            )
            current = await character_relation_repo.get_relation(novel_id, relation_id, session=write_session)
            CharacterRelationService._ensure_expected_version(current, request.expected_version)
            remains_active = bool(current["is_active"])
            normalized_source, normalized_target = await CharacterRelationService._validate_persisted_relation(
                novel_id, current, relation_type=request.relation_type,
                should_be_active=remains_active, require_active_endpoints=remains_active,
                session=write_session,
            )
            endpoint_signatures = await _load_character_endpoint_signatures(
                novel_id, [current["source_character_id"], current["target_character_id"]],
                require_usable=remains_active, session=write_session,
            )
            await _touch_character_endpoint_signatures(endpoint_signatures, session=write_session)
            # 仅去重键按新类型规范化，原端点顺序及 current_state 不参与写入。
            return await character_relation_repo.update_relation(
                novel_id, relation_id,
                {**update_fields,
                 "normalized_source_character_id": normalized_source,
                 "normalized_target_character_id": normalized_target,
                 "semantic_key": f"{normalized_source}:{normalized_target}:{request.relation_type}"},
                request.expected_version, session=write_session,
            )

        if session is not None:
            if not session.in_transaction:
                raise RuntimeError("关系设计保存必须在调用方事务内执行")
            return await _update(session)
        return await run_mongo_write_unit(_update, "update_character_relation_design", require_transaction=True)

    @staticmethod
    async def _current_blockers(
        novel_id: str,
        relation: dict[str, Any],
        *,
        session: AsyncClientSession | None,
    ) -> list[str]:
        """按当前两个角色端点事实重算关系自动阻断来源。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation: 当前人物关系文档。
            session: 可选 MongoDB 会话。

        Returns:
            当前已删除或非 active 角色的端点业务 ID 列表。
        """
        blockers: list[str] = []
        for character_id in (
            str(relation["source_character_id"]),
            str(relation["target_character_id"]),
        ):
            try:
                character = await character_repo.get_character(
                    novel_id,
                    character_id,
                    include_deleted=True,
                    session=session,
                )
            except NotFoundError as exc:
                raise ValueError(f"角色端点 {character_id} 已被彻底删除") from exc
            if (
                character.get("is_deleted") is True
                or character.get("status") != "active"
            ):
                blockers.append(character_id)
        return blockers

    @staticmethod
    async def set_relation_active(novel_id: str, relation_id: str, *, expected_version: int, is_active: bool, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """修改用户启停意图并计算角色关系实际有效态。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。
            is_active: 用户期望的启用状态。

            session: 调用方事务；提供时不另开事务。

        Returns:
            递增版本后的完整关系文档。
        """

        async def _set_active(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内复核端点并执行启停 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await character_relation_repo.get_relation(
                novel_id,
                relation_id,
                session=session,
            )
            CharacterRelationService._ensure_expected_version(current, expected_version)
            if not is_active:
                await CharacterVolumeStateService.ensure_relations_can_be_disabled(
                    novel_id,
                    [relation_id],
                    session=session,
                )
            # 每次以端点当前事实重算，避免恢复角色后残留 blocker 或漏记新失效端点。
            blockers = await CharacterRelationService._current_blockers(
                novel_id,
                current,
                session=session,
            )
            if is_active:
                if blockers:
                    raise ValueError(
                        "角色关系仍受失效端点阻断，无法启用: " + ", ".join(blockers)
                    )
                await CharacterRelationService._validate_persisted_relation(
                    novel_id,
                    current,
                    relation_type=str(current["relation_type"]),
                    should_be_active=True,
                    require_active_endpoints=True,
                    session=session,
                )
            endpoint_ids = [
                str(current["source_character_id"]),
                str(current["target_character_id"]),
            ]
            endpoint_signatures = None
            guard_touches: list[DependencyGuardContribution] = []
            if is_active:
                endpoint_signatures = await _load_character_endpoint_signatures(
                    novel_id,
                    endpoint_ids,
                    require_usable=True,
                    session=session,
                )
                guard_touches = await _touch_character_endpoint_signatures(
                    endpoint_signatures,
                    session=session,
                )
            written: dict[str, Any] | None = None
            try:
                written = await character_relation_repo.update_relation(
                    novel_id,
                    relation_id,
                    {
                        "user_is_active": is_active,
                        "disabled_by_character_ids": blockers,
                        "is_active": is_active and not blockers,
                    },
                    expected_version,
                    session=session,
                )
                if endpoint_signatures is not None:
                    current_signatures = await _load_character_endpoint_signatures(
                        novel_id,
                        endpoint_ids,
                        require_usable=True,
                        session=session,
                    )
                    if current_signatures != endpoint_signatures:
                        raise DuplicateKeyError(
                            "角色关系启用期间端点已被并发修改，请重试"
                        )
                return written
            except Exception:
                if session is None and written is not None:
                    try:
                        await _compensate_character_relation_update(current, written)
                    except Exception as compensation_exc:
                        raise RuntimeError(
                            "角色关系启停失败，且 standalone 补偿未完成"
                        ) from compensation_exc
                if session is None and guard_touches:
                    await rollback_dependency_endpoint_guards(
                        character_repo.collection,
                        guard_touches,
                    )
                raise

        async def _guarded_set_active(
            session: AsyncClientSession | None,
        ) -> dict[str, Any]:
            """在状态写互斥内执行关系启停流程。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                return await _set_active(session)
            finally:
                await release_state_write_lock(
                    novel_id,
                    state_lock,
                    session=session,
                )

        if session is not None:
            return await _guarded_set_active(session)

        return await run_mongo_write_unit(
            _guarded_set_active,
            "set_character_relation_active",
        )

    @staticmethod
    async def soft_delete_relation(novel_id: str, relation_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """把角色关系移入回收站。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            软删除后的完整关系文档。
        """

        async def _delete(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内执行软删除 CAS。"""
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                await novel_repo.get_novel_by_id(novel_id, session=session)
                current = await character_relation_repo.get_relation(
                    novel_id,
                    relation_id,
                    session=session,
                )
                CharacterRelationService._ensure_expected_version(
                    current,
                    expected_version,
                )
                await CharacterVolumeStateService.ensure_relations_can_be_disabled(
                    novel_id,
                    [relation_id],
                    session=session,
                )
                return await character_relation_repo.soft_delete_relation(
                    novel_id,
                    relation_id,
                    expected_version,
                    session=session,
                )
            finally:
                await release_state_write_lock(
                    novel_id,
                    state_lock,
                    session=session,
                )

        if session is not None:
            return await _delete(session)

        return await run_mongo_write_unit(_delete, "soft_delete_character_relation")

    @staticmethod
    async def list_deleted_relations(novel_id: str) -> list[dict[str, Any]]:
        """读取小说角色关系回收站。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。

        Returns:
            已软删除角色关系列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await character_relation_repo.list_deleted_relations(novel_id)

    @staticmethod
    async def restore_relation(novel_id: str, relation_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """从回收站恢复角色关系并重新校验端点与语义唯一性。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            恢复后的完整关系文档。
        """

        async def _restore(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内复核并恢复关系。"""
            novel = await novel_repo.get_novel_by_id(novel_id, session=session)
            if session is not None:
                await protect_chapter_record_sources({("novels", novel_id): novel}, session=session)
            current = await character_relation_repo.get_relation(
                novel_id,
                relation_id,
                include_deleted=True,
                session=session,
            )
            if not current.get("is_deleted"):
                raise NotFoundError(f"角色关系 '{relation_id}' 不在回收站")
            CharacterRelationService._ensure_expected_version(current, expected_version)
            endpoint_ids = [
                str(current["source_character_id"]),
                str(current["target_character_id"]),
            ]
            endpoint_signatures = await _load_character_endpoint_signatures(
                novel_id,
                endpoint_ids,
                require_usable=False,
                session=session,
            )
            blockers = await CharacterRelationService._current_blockers(
                novel_id,
                current,
                session=session,
            )
            should_be_active = current["user_is_active"]
            effective_active = should_be_active and not blockers
            if effective_active:
                await CharacterRelationService._validate_persisted_relation(
                    novel_id,
                    current,
                    relation_type=str(current["relation_type"]),
                    should_be_active=True,
                    require_active_endpoints=True,
                    session=session,
                )
            guard_touches = await _touch_character_endpoint_signatures(
                endpoint_signatures,
                session=session,
            )
            restored: dict[str, Any] | None = None
            try:
                restored = await character_relation_repo.restore_relation(
                    novel_id,
                    relation_id,
                    expected_version,
                    effective_active=effective_active,
                    disabled_by_character_ids=blockers,
                    session=session,
                )
                current_signatures = await _load_character_endpoint_signatures(
                    novel_id,
                    endpoint_ids,
                    require_usable=False,
                    session=session,
                )
                if current_signatures != endpoint_signatures:
                    raise DuplicateKeyError(
                        "角色关系恢复期间端点已被并发修改，请重试"
                    )
                return restored
            except Exception:
                if session is None and restored is not None:
                    try:
                        await _compensate_character_relation_update(current, restored)
                    except Exception as compensation_exc:
                        raise RuntimeError(
                            "角色关系恢复失败，且 standalone 补偿未完成"
                        ) from compensation_exc
                if session is None and guard_touches:
                    await rollback_dependency_endpoint_guards(
                        character_repo.collection,
                        guard_touches,
                    )
                raise

        if session is not None:
            return await _restore(session)

        return await run_mongo_write_unit(_restore, "restore_character_relation")

    @staticmethod
    async def hard_delete_relation(
        novel_id: str,
        relation_id: str,
        *,
        expected_version: int,
    ) -> bool:
        """物理删除回收站中的角色关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            relation_id: 稳定角色关系业务 ID。
            expected_version: 调用方持有的乐观锁版本。

        Returns:
            删除成功时返回 True。
        """

        async def _hard_delete(session: AsyncClientSession | None) -> bool:
            """在一个写入单元内执行硬删除 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            try:
                references = await BaseRepository(
                    "character_volume_states"
                ).find_many(
                    {
                        "novel_id": to_object_id(novel_id),
                        "relationship_focus_ids": relation_id,
                    },
                    include_deleted=True,
                    sort=[("state_id", 1)],
                    session=session,
                )
                if references:
                    raise DomainApiError(
                        "CHARACTER_RELATION_STATE_REFERENCE_PROTECTED",
                        "角色关系仍被卷级状态引用，不能永久删除",
                        status_code=409,
                        details={
                            "state_ids": [
                                str(state["state_id"]) for state in references
                            ],
                            "count": len(references),
                        },
                    )
                return await character_relation_repo.hard_delete_relation(
                    novel_id,
                    relation_id,
                    expected_version,
                    session=session,
                )
            finally:
                await release_state_write_lock(
                    novel_id,
                    state_lock,
                    session=session,
                )

        return await run_mongo_write_unit(_hard_delete, "hard_delete_character_relation")
