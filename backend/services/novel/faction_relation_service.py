"""阵营关系当前事实的领域服务。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.errors import DuplicateKeyError, NotFoundError, VersionConflictError
from backend.db.endpoint_guard import (
    DependencyGuardContribution,
    rollback_dependency_endpoint_guards,
    touch_dependency_endpoint_guards,
)
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.llm.schemas.faction_relation_pydantic import (
    FACTION_RELATIONS_RESULT_SCHEMA_ID,
    FACTION_RELATIONS_RESULT_SCHEMA_VERSION,
    SYMMETRIC_FACTION_RELATION_TYPES,
    build_faction_relation_semantic_key,
)
from backend.services.llm.faction_relation_generation_contract import (
    FACTION_RELATION_GENERATION_STEP,
    FACTION_RELATION_WORKFLOW,
    compute_faction_relation_input_fingerprint,
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


FACTION_RELATION_TYPES = frozenset(
    {
        "hostile",
        "allied",
        "cold_war",
        "dependent",
        "subordinate",
        "trade_partner",
        "secret_cooperation",
        "historical_enemy",
    }
)
FACTION_RELATION_CONTENT_FIELDS = (
    "relation_type",
    "current_state",
    "core_conflict",
    "hidden_tension",
    "possible_change",
    "intensity",
)


def _payload_to_dict(payload: Any) -> Dict[str, Any]:
    """把 Pydantic 模型或普通映射转换为独立字典。

    Args:
        payload: Pydantic V2 模型或可转换为字典的载荷。

    Returns:
        不与调用方共享可变状态的字典。
    """
    if hasattr(payload, "model_dump"):
        return dict(payload.model_dump(mode="json"))
    return dict(payload)


def _normalize_scalar(value: Any) -> Any:
    """把枚举转换为公开字符串值。

    Args:
        value: 任意标量。

    Returns:
        Enum 的 value 或原始值。
    """
    return value.value if isinstance(value, Enum) else value


def _faction_endpoint_signatures(
    factions_by_id: Dict[str, Dict[str, Any]],
    faction_ids: List[str],
) -> Dict[str, tuple[Any, Any, str, bool, str]]:
    """生成阵营关系端点的身份、版本、状态与名称签名。

    Args:
        factions_by_id: 已通过同小说作用域校验的阵营映射。
        faction_ids: 本次关系使用的稳定阵营业务 ID。

    Returns:
        阵营 ID 到并发比较签名的映射。
    """
    return {
        faction_id: (
            factions_by_id[faction_id].get("_id"),
            factions_by_id[faction_id]["version"],
            str(factions_by_id[faction_id].get("active_status")),
            factions_by_id[faction_id].get("is_deleted") is True,
            str(factions_by_id[faction_id].get("name") or "").strip(),
        )
        for faction_id in faction_ids
    }


async def _load_faction_endpoint_documents(
    novel_id: str,
    faction_ids: List[str],
    *,
    require_usable: bool,
    session: AsyncClientSession | None,
) -> Dict[str, Dict[str, Any]]:
    """读取阵营关系端点主档且不重复校验已持久化叙述字段。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_ids: 稳定阵营业务 ID。
        require_usable: 是否要求端点未删除且 active。
        session: 可选 MongoDB 会话。

    Returns:
        阵营 ID 到当前主档的映射。
    """
    factions_by_id: Dict[str, Dict[str, Any]] = {}
    for faction_id in faction_ids:
        try:
            faction = await faction_repo.get_faction(
                novel_id,
                faction_id,
                include_deleted=True,
                session=session,
            )
        except NotFoundError as exc:
            raise NotFoundError(f"阵营端点 {faction_id} 不存在于当前小说") from exc
        if require_usable and (
            faction.get("is_deleted") is True
            or faction.get("active_status") != "active"
        ):
            raise ValueError(f"阵营端点 {faction_id} 当前不可用")
        if not str(faction.get("name") or "").strip():
            raise ValueError(f"阵营端点 {faction_id} 名称为空，无法生成关系投影")
        factions_by_id[faction_id] = faction
    return factions_by_id


async def _touch_faction_endpoint_signatures(
    signatures: Dict[
        str,
        tuple[Any, Any, str, bool, str],
    ],
    *,
    session: AsyncClientSession | None,
) -> list[DependencyGuardContribution]:
    """按阵营端点业务签名推进内部依赖护栏。

    Args:
        signatures: 写入前读取的阵营端点业务签名。
        session: 可选 MongoDB 会话。

    Returns:
        每个端点业务查询及其 touch 前 guard 基线，供失败补偿使用。
    """
    queries = [
        {
            "_id": signature[0],
            "faction_id": faction_id,
            "version": signature[1],
            "active_status": signature[2],
            "is_deleted": True if signature[3] else {"$ne": True},
            "name": {"$type": "string", "$regex": r"\S"},
        }
        for faction_id, signature in signatures.items()
    ]
    return await touch_dependency_endpoint_guards(
        faction_repo.collection,
        queries,
        session=session,
    )


async def _compensate_faction_relation_update(
    snapshot: Dict[str, Any],
    written: Dict[str, Any],
) -> None:
    """精确回滚 standalone 阵营关系写入且不覆盖并发新版本。

    Args:
        snapshot: 阵营关系写入前预镜像。
        written: 本次 CAS 写入返回的写后文档。

    Returns:
        无；仍处于本次写后版本时恢复预镜像。
    """
    await _restore_snapshots(
        faction_relation_repo,
        [_updated_compensation_record(snapshot, written)],
    )


class FactionRelationService:
    """统一维护阵营关系方向、引用、语义唯一与完整生命周期。"""

    @staticmethod
    def _ensure_expected_version(relation: Dict[str, Any], expected_version: int) -> None:
        """在领域复核前快速拒绝明显过期的阵营关系版本。

        Args:
            relation: 当前数据库关系文档。
            expected_version: 调用方提交的版本。

        Returns:
            无；版本一致时正常返回。
        """
        actual_version = int(relation["version"])
        if actual_version != expected_version:
            raise VersionConflictError(
                f"阵营关系 '{relation.get('relation_id')}' 版本冲突："
                f"expected={expected_version}, actual={actual_version}"
            )

    @staticmethod
    async def validate_relation_payloads(
        novel_id: str,
        payloads: List[Any],
        *,
        require_active_endpoints: bool,
        check_active_semantic: bool = True,
        exclude_relation_id: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        """执行人工与 AI 共用的阵营关系端点和语义校验。

        Args:
            novel_id: 小说 ObjectId 字符串。
            payloads: 使用稳定 faction_id 端点的关系载荷列表。
            require_active_endpoints: 是否要求端点未删除且 active_status=active。
            check_active_semantic: 是否检查活动语义唯一性。
            exclude_relation_id: 内容更新时排除的当前关系 ID。
            session: 可选 MongoDB 会话。

        Returns:
            本次涉及的 faction_id 到阵营文档映射。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        normalized_payloads = [_payload_to_dict(payload) for payload in payloads]
        endpoint_ids = sorted(
            {
                str(payload.get(field) or "")
                for payload in normalized_payloads
                for field in ("source_faction_id", "target_faction_id")
                if payload.get(field)
            }
        )
        factions_by_id: Dict[str, Dict[str, Any]] = {}
        for faction_id in endpoint_ids:
            try:
                faction = await faction_repo.get_faction(
                    novel_id,
                    faction_id,
                    include_deleted=True,
                    session=session,
                )
            except NotFoundError as exc:
                raise NotFoundError(f"阵营端点 {faction_id} 不存在于当前小说") from exc
            if require_active_endpoints and (
                faction.get("is_deleted") is True
                or faction.get("active_status") != "active"
                or faction.get("level_type") != "core"
            ):
                raise ValueError(f"阵营端点 {faction_id} 必须是活动核心势力")
            projected_name = str(faction.get("name") or "").strip()
            if not projected_name:
                raise ValueError(f"阵营端点 {faction_id} 名称为空，无法生成关系投影")
            factions_by_id[faction_id] = faction

        semantic_owner: Dict[tuple[str, str, str], int] = {}
        semantics: List[tuple[str, str, str]] = []
        for index, payload in enumerate(normalized_payloads):
            source_id = str(payload.get("source_faction_id") or "")
            target_id = str(payload.get("target_faction_id") or "")
            relation_type = str(_normalize_scalar(payload.get("relation_type")) or "")
            intensity = payload.get("intensity")
            if not source_id or not target_id:
                raise ValueError(f"relations[{index}] 缺少阵营端点")
            if source_id == target_id:
                raise ValueError(f"relations[{index}] 阵营关系不能指向自身")
            if source_id not in factions_by_id or target_id not in factions_by_id:
                raise ValueError(f"relations[{index}] 包含无效阵营端点")
            if relation_type not in FACTION_RELATION_TYPES:
                raise ValueError(f"relations[{index}] 不支持 relation_type={relation_type}")
            if isinstance(intensity, bool) or not isinstance(intensity, int) or not 1 <= intensity <= 5:
                raise ValueError(f"relations[{index}] intensity 必须为 1 至 5 的整数")
            for field in ("current_state", "core_conflict", "possible_change"):
                value = payload.get(field)
                if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2000:
                    raise ValueError(f"relations[{index}] {field} 必须为非空文本")
            hidden_tension = payload.get("hidden_tension", "")
            if not isinstance(hidden_tension, str) or len(hidden_tension.strip()) > 2000:
                raise ValueError(f"relations[{index}] hidden_tension 最多 2000 字符")

            if payload.get("is_active", True) is True and check_active_semantic:
                semantic = build_faction_relation_semantic_key(
                    source_id,
                    target_id,
                    relation_type,
                )
                previous_index = semantic_owner.get(semantic)
                if previous_index is not None:
                    raise DuplicateKeyError(
                        f"relations[{index}] 与 relations[{previous_index}] 构成重复语义关系"
                    )
                semantic_owner[semantic] = index
                semantics.append(semantic)

        conflicts = await faction_relation_repo.find_active_semantic_relations(
            novel_id,
            semantics,
            exclude_relation_id=exclude_relation_id,
            session=session,
        )
        if conflicts:
            relation_ids = ", ".join(str(item["relation_id"]) for item in conflicts)
            raise DuplicateKeyError(f"与既有活动阵营关系语义重复: {relation_ids}")
        return factions_by_id

    @staticmethod
    async def bulk_create_relations(
        novel_id: str,
        payloads: List[Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """批量校验、分配 ID 并创建正式阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            payloads: 使用 faction_id 引用端点的人工或 AI 关系载荷。
            session: 可选 MongoDB 会话；AI 聚合确认应传入其现有会话。

        Returns:
            按输入顺序返回新建的完整阵营关系。
        """
        sources = [_payload_to_dict(payload) for payload in payloads]
        if not sources:
            return []
        factions_by_id = await FactionRelationService.validate_relation_payloads(
            novel_id,
            sources,
            require_active_endpoints=True,
            session=session,
        )
        endpoint_ids = sorted(factions_by_id)
        endpoint_signatures = _faction_endpoint_signatures(
            factions_by_id,
            endpoint_ids,
        )
        relation_ids = await id_sequence_repo.allocate_many(
            novel_id,
            "faction_relation",
            "fr",
            len(sources),
            session=session,
        )
        documents: List[Dict[str, Any]] = []
        for source, relation_id in zip(sources, relation_ids):
            source_id = str(source["source_faction_id"])
            target_id = str(source["target_faction_id"])
            relation_type = str(_normalize_scalar(source["relation_type"]))
            normalized_source, normalized_target, _ = build_faction_relation_semantic_key(
                source_id,
                target_id,
                relation_type,
            )
            if relation_type in SYMMETRIC_FACTION_RELATION_TYPES:
                # 对称关系正式端点也使用稳定顺序，避免反向展示产生两套事实。
                source_id, target_id = normalized_source, normalized_target
            suffix = int(relation_id.rsplit("_", 1)[-1])
            document: Dict[str, Any] = {
                "novel_id": novel_id,
                "relation_id": relation_id,
                "source_faction_id": source_id,
                "target_faction_id": target_id,
                "source_faction_name": str(factions_by_id[source_id]["name"]).strip(),
                "target_faction_name": str(factions_by_id[target_id]["name"]).strip(),
                "normalized_source_faction_id": normalized_source,
                "normalized_target_faction_id": normalized_target,
                "relation_type": relation_type,
                "semantic_key": f"{normalized_source}:{normalized_target}:{relation_type}",
                "current_state": str(source.get("current_state") or "").strip(),
                "core_conflict": str(source.get("core_conflict") or "").strip(),
                "hidden_tension": str(source.get("hidden_tension") or "").strip(),
                "possible_change": str(source.get("possible_change") or "").strip(),
                "intensity": int(source["intensity"]),
                "user_is_active": bool(source.get("is_active", True)),
                "is_active": bool(source.get("is_active", True)),
                "disabled_by_faction_ids": [],
                "sort_order": suffix * 10,
                "version": 1,
            }
            for field in (
                "creation_idempotency_key_hash",
                "creation_request_hash",
                "batch_idempotency_key_hash",
                "batch_request_hash",
                "batch_local_ref",
                "batch_request_kind",
                "batch_command_marker",
            ):
                if source.get(field) is not None:
                    document[field] = source[field]
            documents.append(document)
        # 先推进端点内部护栏，再写依赖；失败时 revision 推进不影响公开业务版本。
        guard_touches = await _touch_faction_endpoint_signatures(
            endpoint_signatures,
            session=session,
        )
        try:
            created = await faction_relation_repo.insert_relations(
                documents,
                session=session,
            )
            current_factions = await FactionRelationService.validate_relation_payloads(
                novel_id,
                sources,
                require_active_endpoints=True,
                check_active_semantic=False,
                session=session,
            )
            if _faction_endpoint_signatures(
                current_factions,
                endpoint_ids,
            ) != endpoint_signatures:
                raise DuplicateKeyError("阵营关系创建期间端点已被并发修改，请重试")
        except Exception:
            if session is None:
                await faction_relation_repo.delete_relations_exact(
                    novel_id,
                    relation_ids,
                )
                if guard_touches:
                    await rollback_dependency_endpoint_guards(
                        faction_repo.collection,
                        guard_touches,
                    )
            raise
        return created

    @staticmethod
    async def bulk_append_relations(novel_id: str, result: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """幂等追加严格人工批次或 AI 显式选择的阵营关系。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            result: 已通过人工或 AI 确认联合 Schema 校验的请求。
            idempotency_key: 调用方提供的批量追加幂等键。

            session: 调用方事务；提供时不另开事务。

        Returns:
            包含新建正式阵营关系列表的字典。
        """
        source = _payload_to_dict(result)
        is_ai_confirmation = source.get("request_type") == "ai_confirmation"
        if is_ai_confirmation:
            all_candidates = [
                _payload_to_dict(candidate)
                for candidate in source.get("candidate", {}).get("relations", [])
            ]
            selected_refs = set(source.get("selected_relation_refs") or [])
            normalized_candidates = [
                candidate
                for candidate in all_candidates
                if candidate.get("relation_ref") in selected_refs
            ]
            request_kind = "ai_confirmation"
        else:
            normalized_candidates = [
                _payload_to_dict(candidate)
                for candidate in source.get("relations", [])
            ]
            for index, candidate in enumerate(normalized_candidates, start=1):
                candidate["relation_ref"] = f"relation_{index:03d}"
            request_kind = "manual"
        if not normalized_candidates:
            raise ValueError("至少需要一条阵营关系")
        relation_refs = [str(candidate["relation_ref"]) for candidate in normalized_candidates]
        if len(relation_refs) != len(set(relation_refs)):
            raise ValueError("阵营关系 local ref 不能重复")
        semantic_keys: set[tuple[str, str, str]] = set()
        for candidate in normalized_candidates:
            if candidate.get("is_active", True) is not True:
                continue
            semantic_key = build_faction_relation_semantic_key(
                str(candidate["source_faction_id"]),
                str(candidate["target_faction_id"]),
                str(_normalize_scalar(candidate["relation_type"])),
            )
            if semantic_key in semantic_keys:
                raise DuplicateKeyError(
                    "relations 中不能包含重复或反向重复的活动语义边"
                )
            semantic_keys.add(semantic_key)

        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "request": source})

        async def _load_existing(
            active_session: AsyncClientSession | None,
        ) -> Dict[str, Dict[str, Any]]:
            """读取同一批次已存在的 local ref，并校验请求摘要。"""
            existing = await faction_relation_repo.find_by_batch_idempotency(
                novel_id,
                key_hash,
                session=active_session,
            )
            if any(item.get("batch_request_hash") != request_hash for item in existing):
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的阵营关系批量请求",
                    status_code=409,
                )
            by_ref = {
                str(item.get("batch_local_ref")): item
                for item in existing
                if item.get("batch_local_ref")
            }
            if len(by_ref) != len(existing):
                raise DuplicateKeyError("阵营关系批次 local ref 元数据冲突")
            if set(by_ref) - set(relation_refs):
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 的既有阵营关系映射与当前请求不一致",
                    status_code=409,
                )
            return by_ref

        async def _validate_ai_versions(
            active_session: AsyncClientSession | None,
        ) -> None:
            """重读 AI basis 正式来源，拒绝消失或版本漂移。"""
            if not is_ai_confirmation:
                return
            basis = source["basis"]
            if (
                basis.get("novel_id") != novel_id
                or source["generation_input"].get("novel_id") != novel_id
            ):
                raise NotFoundError("AI 阵营关系确认不属于当前小说")
            if (
                basis.get("workflow") != FACTION_RELATION_WORKFLOW
                or basis.get("step") != FACTION_RELATION_GENERATION_STEP
                or basis.get("schema_id") != FACTION_RELATIONS_RESULT_SCHEMA_ID
                or basis.get("schema_version")
                != FACTION_RELATIONS_RESULT_SCHEMA_VERSION
            ):
                raise ValueError("AI 阵营关系确认的 workflow/step/schema 契约不匹配")
            basis_faction_ids: set[str] = set()
            basis_relation_ids: set[str] = set()
            novel_source_count = 0
            for item in basis.get("source_refs", []):
                resource_type = str(item["resource_type"])
                resource_id = str(item["id"])
                expected_version = int(item["version"])
                if resource_type == "novel":
                    novel_source_count += 1
                    if resource_id != novel_id:
                        raise ValueError("basis 中的 novel 来源不属于当前小说")
                    current = await novel_repo.get_novel_by_id(
                        novel_id,
                        session=active_session,
                    )
                elif resource_type == "faction":
                    basis_faction_ids.add(resource_id)
                    current = await faction_repo.get_faction(
                        novel_id,
                        resource_id,
                        session=active_session,
                    )
                elif resource_type == "faction_relation":
                    basis_relation_ids.add(resource_id)
                    current = await faction_relation_repo.get_relation(
                        novel_id,
                        resource_id,
                        session=active_session,
                    )
                else:
                    raise ValueError(f"不支持的 basis resource_type={resource_type}")
                if int(current["version"]) != expected_version:
                    raise VersionConflictError(
                        f"AI 阵营关系候选依据版本冲突: {resource_type}:{resource_id}"
                    )
            selected_faction_ids = set(source["generation_input"]["faction_ids"])
            if novel_source_count != 1 or basis_faction_ids != selected_faction_ids:
                raise ValueError("AI 阵营关系 basis 必须精确覆盖小说和所选正式势力")
            current_relation_ids = {
                str(item["relation_id"])
                for item in await faction_relation_repo.get_relations_by_novel(
                    novel_id,
                    active_only=True,
                    session=active_session,
                )
                if item.get("batch_idempotency_key_hash") != key_hash
                and item.get("source_faction_id") in selected_faction_ids
                and item.get("target_faction_id") in selected_faction_ids
            }
            if current_relation_ids != basis_relation_ids:
                raise DuplicateKeyError("AI 阵营关系候选依据中的正式关系集合已变化")
            current_fingerprint = compute_faction_relation_input_fingerprint(
                source["generation_input"],
                basis.get("source_refs", []),
                flow_snapshot=basis.get("flow_snapshot"),
            )
            if basis.get("input_fingerprint") != current_fingerprint:
                raise DuplicateKeyError("AI 阵营关系候选输入指纹冲突")

        def _build_result(
            existing_by_ref: Dict[str, Dict[str, Any]],
        ) -> Dict[str, Any]:
            """按候选顺序组装批次结果和 AI 公开映射。

            Args:
                existing_by_ref: 本批 local ref 到正式阵营关系文档的完整映射。

            Returns:
                顺序稳定的正式关系和仅 AI 确认携带的 ref 映射。
            """
            return {
                "faction_relations": [
                    existing_by_ref[relation_ref]
                    for relation_ref in relation_refs
                ],
                "relation_ref_map": (
                    {
                        relation_ref: str(
                            existing_by_ref[relation_ref]["relation_id"]
                        )
                        for relation_ref in relation_refs
                    }
                    if is_ai_confirmation
                    else {}
                ),
            }

        async def _append(active_session: AsyncClientSession | None) -> Dict[str, Any]:
            """在一个写入单元内续写缺失 local ref 并返回完整映射。"""
            existing_by_ref = await _load_existing(active_session)
            if set(existing_by_ref) == set(relation_refs):
                return _build_result(existing_by_ref)
            await novel_repo.get_novel_by_id(novel_id, session=active_session)
            await _validate_ai_versions(active_session)
            missing = [
                dict(candidate)
                for candidate in normalized_candidates
                if candidate["relation_ref"] not in existing_by_ref
            ]
            has_marker = any(
                item.get("batch_command_marker") is True
                for item in existing_by_ref.values()
            )
            for index, candidate in enumerate(missing):
                candidate.update(
                    {
                        "batch_idempotency_key_hash": key_hash,
                        "batch_request_hash": request_hash,
                        "batch_local_ref": candidate["relation_ref"],
                        "batch_request_kind": request_kind,
                    }
                )
                if not has_marker and index == 0:
                    candidate["batch_command_marker"] = True
            if missing:
                created = await FactionRelationService.bulk_create_relations(
                    novel_id,
                    missing,
                    session=active_session,
                )
                for relation in created:
                    existing_by_ref[str(relation["batch_local_ref"])] = relation
            if set(existing_by_ref) != set(relation_refs):
                raise DuplicateKeyError("阵营关系批次未能形成完整 local ref 映射")
            return _build_result(existing_by_ref)

        if session is not None:
            return await _append(session)

        try:
            return await run_mongo_write_unit(_append, "bulk_append_faction_relations")
        except DuplicateKeyError:
            replay = await _load_existing(None)
            if set(replay) == set(relation_refs):
                return _build_result(replay)
            raise

    @staticmethod
    async def create_relation(novel_id: str, payload: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """幂等创建一条人工阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            payload: 严格创建请求。
            idempotency_key: 调用方提供的创建幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            新建或幂等回放的完整阵营关系。
        """
        source = _payload_to_dict(payload)
        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "payload": source})

        async def _find_replay(
            session: AsyncClientSession | None,
        ) -> Dict[str, Any] | None:
            """读取并校验同一幂等键的首次结果。"""
            existing = await faction_relation_repo.find_by_creation_idempotency(
                novel_id,
                key_hash,
                session=session,
            )
            if existing is None:
                return None
            if existing.get("creation_request_hash") != request_hash:
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的阵营关系创建请求",
                    status_code=409,
                )
            return existing

        async def _create(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在一个写入单元内完成幂等回放与创建。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            replay = await _find_replay(session)
            if replay is not None:
                return replay
            source["creation_idempotency_key_hash"] = key_hash
            source["creation_request_hash"] = request_hash
            created = await FactionRelationService.bulk_create_relations(
                novel_id,
                [source],
                session=session,
            )
            return created[0]

        if session is not None:
            return await _create(session)

        try:
            return await run_mongo_write_unit(_create, "create_faction_relation")
        except DuplicateKeyError:
            replay = await _find_replay(None)
            if replay is not None:
                return replay
            raise

    @staticmethod
    async def get_relation(novel_id: str, relation_id: str) -> Dict[str, Any]:
        """获取一条未删除阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。

        Returns:
            匹配的完整关系文档。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_relation_repo.get_relation(novel_id, relation_id)

    @staticmethod
    async def get_relations_by_novel(
        novel_id: str,
        *,
        active_only: bool | None = None,
    ) -> List[Dict[str, Any]]:
        """获取小说下阵营关系，可按实际有效态过滤。

        Args:
            novel_id: 小说 ObjectId 字符串。
            active_only: True/False 分别筛选有效/无效，None 返回全部未删除关系。

        Returns:
            阵营关系文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_relation_repo.get_relations_by_novel(
            novel_id,
            active_only=active_only,
        )

    @staticmethod
    async def get_relations_by_faction(
        novel_id: str,
        faction_id: str,
        *,
        active_only: bool | None = None,
    ) -> List[Dict[str, Any]]:
        """获取某个阵营参与的关系，可按实际有效态过滤。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            active_only: True/False 分别筛选有效/无效，None 返回全部未删除关系。

        Returns:
            阵营关系文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        await faction_repo.get_faction(novel_id, faction_id, include_deleted=True)
        return await faction_relation_repo.get_relations_by_faction(
            novel_id,
            faction_id,
            active_only=active_only,
        )

    @staticmethod
    async def update_relation(novel_id: str, relation_id: str, payload: Any, *, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """更新阵营关系内容，稳定端点保持不可变。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            payload: 内容字段与 expected_version。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            递增版本后的完整关系文档。
        """
        source = _payload_to_dict(payload)
        expected_version = int(source.pop("expected_version"))

        async def _update(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在一个写入单元内复核并执行内容 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await faction_relation_repo.get_relation(
                novel_id,
                relation_id,
                session=session,
            )
            FactionRelationService._ensure_expected_version(current, expected_version)
            update_fields = {
                field: source[field] for field in FACTION_RELATION_CONTENT_FIELDS
            }
            for field in (
                "current_state",
                "core_conflict",
                "hidden_tension",
                "possible_change",
            ):
                update_fields[field] = str(update_fields[field]).strip()
            relation_type = str(_normalize_scalar(update_fields["relation_type"]))
            update_fields["relation_type"] = relation_type
            validation_payload = {
                **current,
                **update_fields,
                "is_active": bool(current.get("is_active")),
            }
            remains_active = bool(current.get("is_active"))
            factions_by_id = await FactionRelationService.validate_relation_payloads(
                novel_id,
                [validation_payload],
                require_active_endpoints=remains_active,
                check_active_semantic=remains_active,
                exclude_relation_id=relation_id,
                session=session,
            )
            normalized_source, normalized_target, _ = (
                build_faction_relation_semantic_key(
                    str(current["source_faction_id"]),
                    str(current["target_faction_id"]),
                    relation_type,
                )
            )
            update_fields.update(
                {
                    "normalized_source_faction_id": normalized_source,
                    "normalized_target_faction_id": normalized_target,
                    "semantic_key": (
                        f"{normalized_source}:{normalized_target}:{relation_type}"
                    ),
                }
            )
            endpoint_ids = sorted(factions_by_id)
            endpoint_signatures = None
            guard_touches: list[DependencyGuardContribution] = []
            if remains_active:
                endpoint_signatures = _faction_endpoint_signatures(
                    factions_by_id,
                    endpoint_ids,
                )
                guard_touches = await _touch_faction_endpoint_signatures(
                    endpoint_signatures,
                    session=session,
                )
            written: Dict[str, Any] | None = None
            try:
                written = await faction_relation_repo.update_relation(
                    novel_id,
                    relation_id,
                    update_fields,
                    expected_version,
                    session=session,
                )
                if endpoint_signatures is not None:
                    current_factions = (
                        await FactionRelationService.validate_relation_payloads(
                            novel_id,
                            [validation_payload],
                            require_active_endpoints=True,
                            check_active_semantic=False,
                            session=session,
                        )
                    )
                    if _faction_endpoint_signatures(
                        current_factions,
                        endpoint_ids,
                    ) != endpoint_signatures:
                        raise DuplicateKeyError(
                            "阵营关系更新期间端点已被并发修改，请重试"
                        )
                return written
            except Exception:
                if session is None and written is not None:
                    try:
                        await _compensate_faction_relation_update(current, written)
                    except Exception as compensation_exc:
                        raise RuntimeError(
                            "阵营关系更新失败，且 standalone 补偿未完成"
                        ) from compensation_exc
                if session is None and guard_touches:
                    await rollback_dependency_endpoint_guards(
                        faction_repo.collection,
                        guard_touches,
                    )
                raise

        if session is not None:
            return await _update(session)

        return await run_mongo_write_unit(_update, "update_faction_relation")

    @staticmethod
    async def _current_blockers(
        novel_id: str,
        relation: Dict[str, Any],
        *,
        session: AsyncClientSession | None,
    ) -> List[str]:
        """按当前两端阵营状态重算自动阻断来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation: 当前阵营关系文档。
            session: 可选 MongoDB 会话。

        Returns:
            当前已删除或非 active 的端点 faction_id 列表。
        """
        blockers: List[str] = []
        for faction_id in (
            str(relation["source_faction_id"]),
            str(relation["target_faction_id"]),
        ):
            try:
                faction = await faction_repo.get_faction(
                    novel_id,
                    faction_id,
                    include_deleted=True,
                    session=session,
                )
            except NotFoundError as exc:
                raise ValueError(f"阵营端点 {faction_id} 已被彻底删除") from exc
            if faction.get("is_deleted") is True or faction.get("active_status") != "active":
                blockers.append(faction_id)
        return blockers

    @staticmethod
    async def validate_faction_unblock(
        novel_id: str,
        faction_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """预检阵营恢复 active 后将重新启用的全部关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 即将恢复 active 的阵营业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            校验通过后将重新启用的关系数量。
        """
        relations = await faction_relation_repo.get_relations_by_faction(
            novel_id,
            faction_id,
            active_only=None,
            session=session,
        )
        candidates: List[Dict[str, Any]] = []
        semantics: Dict[tuple[str, str, str], str] = {}
        for relation in relations:
            blockers = list(relation.get("disabled_by_faction_ids") or [])
            if faction_id not in blockers or relation["user_is_active"] is not True:
                continue
            remaining = [item for item in blockers if item != faction_id]
            if remaining:
                continue

            # 当前阵营按“即将 active”处理；另一端必须已经可用。
            for endpoint_id in (
                str(relation["source_faction_id"]),
                str(relation["target_faction_id"]),
            ):
                if endpoint_id == faction_id:
                    continue
                endpoint = await faction_repo.get_faction(
                    novel_id,
                    endpoint_id,
                    include_deleted=True,
                    session=session,
                )
                if endpoint.get("is_deleted") is True or endpoint.get("active_status") != "active":
                    raise ValueError(f"阵营端点 {endpoint_id} 当前不可用")

            semantic = build_faction_relation_semantic_key(
                str(relation["source_faction_id"]),
                str(relation["target_faction_id"]),
                str(relation["relation_type"]),
            )
            previous_relation_id = semantics.get(semantic)
            if previous_relation_id is not None:
                raise DuplicateKeyError(
                    f"阵营恢复后关系 {relation['relation_id']} 与 {previous_relation_id} 语义重复"
                )
            semantics[semantic] = str(relation["relation_id"])
            candidates.append(relation)

        existing = await faction_relation_repo.find_active_semantic_relations(
            novel_id,
            list(semantics),
            session=session,
        )
        if existing:
            relation_ids = ", ".join(str(item["relation_id"]) for item in existing)
            raise DuplicateKeyError(f"阵营恢复会与活动关系语义冲突: {relation_ids}")
        return len(candidates)

    @staticmethod
    async def set_relation_active(novel_id: str, relation_id: str, *, expected_version: int, is_active: bool, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """修改用户启停意图并重算阵营关系有效态。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。
            is_active: 用户期望的启用状态。

            session: 调用方事务；提供时不另开事务。

        Returns:
            更新后的完整关系文档。
        """

        async def _set_active(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在一个写入单元内重算阻断来源并执行 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await faction_relation_repo.get_relation(
                novel_id,
                relation_id,
                session=session,
            )
            FactionRelationService._ensure_expected_version(current, expected_version)
            blockers = await FactionRelationService._current_blockers(
                novel_id,
                current,
                session=session,
            )
            if is_active and blockers:
                raise ValueError("阵营关系仍受失效端点阻断: " + ", ".join(blockers))
            if is_active:
                validation_payload = {**current, "is_active": True}
                factions_by_id = await FactionRelationService.validate_relation_payloads(
                    novel_id,
                    [validation_payload],
                    require_active_endpoints=True,
                    exclude_relation_id=relation_id,
                    session=session,
                )
            else:
                factions_by_id = {}
            endpoint_ids = sorted(factions_by_id)
            endpoint_signatures = None
            guard_touches: list[DependencyGuardContribution] = []
            if is_active:
                endpoint_signatures = _faction_endpoint_signatures(
                    factions_by_id,
                    endpoint_ids,
                )
                guard_touches = await _touch_faction_endpoint_signatures(
                    endpoint_signatures,
                    session=session,
                )
            written: Dict[str, Any] | None = None
            try:
                written = await faction_relation_repo.update_relation(
                    novel_id,
                    relation_id,
                    {
                        "user_is_active": is_active,
                        "disabled_by_faction_ids": blockers,
                        "is_active": is_active and not blockers,
                    },
                    expected_version,
                    session=session,
                )
                if endpoint_signatures is not None:
                    current_factions = (
                        await FactionRelationService.validate_relation_payloads(
                            novel_id,
                            [{**current, "is_active": True}],
                            require_active_endpoints=True,
                            check_active_semantic=False,
                            session=session,
                        )
                    )
                    if _faction_endpoint_signatures(
                        current_factions,
                        endpoint_ids,
                    ) != endpoint_signatures:
                        raise DuplicateKeyError(
                            "阵营关系启用期间端点已被并发修改，请重试"
                        )
                return written
            except Exception:
                if session is None and written is not None:
                    try:
                        await _compensate_faction_relation_update(current, written)
                    except Exception as compensation_exc:
                        raise RuntimeError(
                            "阵营关系启停失败，且 standalone 补偿未完成"
                        ) from compensation_exc
                if session is None and guard_touches:
                    await rollback_dependency_endpoint_guards(
                        faction_repo.collection,
                        guard_touches,
                    )
                raise

        if session is not None:
            return await _set_active(session)

        return await run_mongo_write_unit(_set_active, "set_faction_relation_active")

    @staticmethod
    async def soft_delete_relation(novel_id: str, relation_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """把阵营关系移入回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            软删除后的完整关系文档。
        """

        async def _delete(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在一个写入单元内执行软删除 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            return await faction_relation_repo.soft_delete_relation(
                novel_id,
                relation_id,
                expected_version,
                session=session,
            )

        if session is not None:
            return await _delete(session)

        return await run_mongo_write_unit(_delete, "soft_delete_faction_relation")

    @staticmethod
    async def list_deleted_relations(novel_id: str) -> List[Dict[str, Any]]:
        """读取小说阵营关系回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            已软删除阵营关系列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_relation_repo.list_deleted_relations(novel_id)

    @staticmethod
    async def restore_relation(novel_id: str, relation_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> Dict[str, Any]:
        """恢复阵营关系并按当前端点状态重算阻断来源。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            恢复后的完整关系文档。
        """

        async def _restore(session: AsyncClientSession | None) -> Dict[str, Any]:
            """在一个写入单元内重算阻断、复核唯一性并恢复。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await faction_relation_repo.get_relation(
                novel_id,
                relation_id,
                include_deleted=True,
                session=session,
            )
            if not current.get("is_deleted"):
                raise NotFoundError(f"阵营关系 '{relation_id}' 不在回收站")
            FactionRelationService._ensure_expected_version(current, expected_version)
            blockers = await FactionRelationService._current_blockers(
                novel_id,
                current,
                session=session,
            )
            effective_active = current["user_is_active"] and not blockers
            validation_payload = {**current, "is_active": effective_active}
            endpoint_ids = sorted(
                {
                    str(current["source_faction_id"]),
                    str(current["target_faction_id"]),
                }
            )
            if effective_active:
                factions_by_id = (
                    await FactionRelationService.validate_relation_payloads(
                        novel_id,
                        [validation_payload],
                        require_active_endpoints=True,
                        check_active_semantic=True,
                        exclude_relation_id=relation_id,
                        session=session,
                    )
                )
            else:
                factions_by_id = await _load_faction_endpoint_documents(
                    novel_id,
                    endpoint_ids,
                    require_usable=False,
                    session=session,
                )
            endpoint_signatures = _faction_endpoint_signatures(
                factions_by_id,
                endpoint_ids,
            )
            guard_touches = await _touch_faction_endpoint_signatures(
                endpoint_signatures,
                session=session,
            )
            restored: Dict[str, Any] | None = None
            try:
                restored = await faction_relation_repo.restore_relation(
                    novel_id,
                    relation_id,
                    expected_version,
                    effective_active=effective_active,
                    disabled_by_faction_ids=blockers,
                    source_faction_name=str(
                        factions_by_id[str(current["source_faction_id"])]["name"]
                    ).strip(),
                    target_faction_name=str(
                        factions_by_id[str(current["target_faction_id"])]["name"]
                    ).strip(),
                    session=session,
                )
                current_factions = await _load_faction_endpoint_documents(
                    novel_id,
                    endpoint_ids,
                    require_usable=False,
                    session=session,
                )
                if _faction_endpoint_signatures(
                    current_factions,
                    endpoint_ids,
                ) != endpoint_signatures:
                    raise DuplicateKeyError(
                        "阵营关系恢复期间端点已被并发修改，请重试"
                    )
                return restored
            except Exception:
                if session is None and restored is not None:
                    try:
                        await _compensate_faction_relation_update(current, restored)
                    except Exception as compensation_exc:
                        raise RuntimeError(
                            "阵营关系恢复失败，且 standalone 补偿未完成"
                        ) from compensation_exc
                if session is None and guard_touches:
                    await rollback_dependency_endpoint_guards(
                        faction_repo.collection,
                        guard_touches,
                    )
                raise

        if session is not None:
            return await _restore(session)

        return await run_mongo_write_unit(_restore, "restore_faction_relation")

    @staticmethod
    async def hard_delete_relation(
        novel_id: str,
        relation_id: str,
        *,
        expected_version: int,
    ) -> bool:
        """物理删除回收站中的阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            relation_id: 稳定阵营关系业务 ID。
            expected_version: 调用方持有的版本。

        Returns:
            删除成功时返回 True。
        """

        async def _hard_delete(session: AsyncClientSession | None) -> bool:
            """在一个写入单元内执行硬删除 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            return await faction_relation_repo.hard_delete_relation(
                novel_id,
                relation_id,
                expected_version,
                session=session,
            )

        return await run_mongo_write_unit(_hard_delete, "hard_delete_faction_relation")
