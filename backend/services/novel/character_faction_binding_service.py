"""全书级角色—势力绑定领域服务。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.endpoint_guard import (
    DependencyGuardContribution,
    rollback_dependency_endpoint_guards,
    touch_dependency_endpoint_guards,
)
from backend.db.repositories.character_faction_binding_repository import character_faction_binding_repo
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import (
    checksum,
    hash_idempotency_key,
)


INITIAL_MEMBERSHIP_TYPES = frozenset({"primary", "secondary", "covert"})
BINDING_CONTENT_FIELDS = (
    "membership_type",
    "role_title",
    "public_status",
    "loyalty_level",
    "notes",
)


def _payload_to_dict(payload: Any) -> dict[str, Any]:
    """将 Pydantic 模型或普通映射转换为独立字典。

    Args:
        payload: Pydantic V2 模型或可转换为 dict 的绑定载荷。

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


async def _load_usable_binding_endpoint_signatures(
    novel_id: str,
    payloads: list[dict[str, Any]],
    *,
    session: AsyncClientSession | None,
) -> tuple[
    dict[str, tuple[Any, Any, str, bool, bool]],
    dict[str, tuple[Any, Any, str, str, bool]],
]:
    """读取绑定端点可用性并生成角色、势力并发比较签名。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        payloads: 本次待创建绑定的规范载荷。
        session: 可选 MongoDB 会话。

    Returns:
        角色签名映射与势力签名映射组成的二元组。
    """
    character_ids = sorted({str(item["character_id"]) for item in payloads})
    faction_ids = sorted({str(item["faction_id"]) for item in payloads})
    characters = await character_repo.get_characters_by_ids(
        novel_id,
        character_ids,
        session=session,
    )
    factions = await faction_repo.get_factions_by_novel(novel_id, session=session)
    characters_by_id = {
        str(character["character_id"]): character for character in characters
    }
    factions_by_id = {
        str(faction["faction_id"]): faction
        for faction in factions
        if str(faction.get("faction_id") or "") in set(faction_ids)
    }
    missing_characters = [
        character_id for character_id in character_ids if character_id not in characters_by_id
    ]
    missing_factions = [
        faction_id for faction_id in faction_ids if faction_id not in factions_by_id
    ]
    if missing_characters or missing_factions:
        raise NotFoundError(
            "角色—势力绑定端点不存在于当前小说: "
            f"characters={missing_characters}, factions={missing_factions}"
        )
    invalid_characters = [
        character_id
        for character_id in character_ids
        if characters_by_id[character_id].get("status") != "active"
        or characters_by_id[character_id].get("is_core_character") is not True
        or characters_by_id[character_id].get("is_deleted") is True
    ]
    invalid_factions = [
        faction_id
        for faction_id in faction_ids
        if factions_by_id[faction_id].get("active_status") != "active"
        or factions_by_id[faction_id].get("level_type") != "core"
        or factions_by_id[faction_id].get("is_deleted") is True
    ]
    if invalid_characters or invalid_factions:
        raise ValueError(
            "角色—势力绑定端点当前不可用: "
            f"characters={invalid_characters}, factions={invalid_factions}"
        )
    character_signatures = {
        character_id: (
            characters_by_id[character_id].get("_id"),
            characters_by_id[character_id]["version"],
            str(characters_by_id[character_id].get("status")),
            characters_by_id[character_id].get("is_core_character") is True,
            characters_by_id[character_id].get("is_deleted") is True,
        )
        for character_id in character_ids
    }
    faction_signatures = {
        faction_id: (
            factions_by_id[faction_id].get("_id"),
            factions_by_id[faction_id]["version"],
            str(factions_by_id[faction_id].get("active_status")),
            str(factions_by_id[faction_id].get("level_type")),
            factions_by_id[faction_id].get("is_deleted") is True,
        )
        for faction_id in faction_ids
    }
    return character_signatures, faction_signatures


async def _rollback_binding_endpoint_touches(
    character_touches: list[DependencyGuardContribution],
    faction_touches: list[DependencyGuardContribution],
) -> None:
    """回退未落库绑定自己的两类端点 guard，并完整尝试两侧。

    Args:
        character_touches: 已推进的角色端点一次性贡献记录。
        faction_touches: 已推进的势力端点一次性贡献记录。

    Returns:
        无；逐条减回尚未消费的本请求贡献。
    """
    if not character_touches and not faction_touches:
        return
    failures: list[Exception] = []
    for collection, touches in (
        (faction_repo.collection, faction_touches),
        (character_repo.collection, character_touches),
    ):
        if not touches:
            continue
        try:
            await rollback_dependency_endpoint_guards(collection, touches)
        except Exception as exc:  # 补偿必须继续尝试另一类端点，最后统一显式失败。
            failures.append(exc)
    if failures:
        raise RuntimeError("绑定失败后的端点 guard 补偿未完整完成") from failures[0]


async def _touch_binding_endpoint_signatures(
    signatures: tuple[
        dict[str, tuple[Any, Any, str, bool, bool]],
        dict[str, tuple[Any, Any, str, str, bool]],
    ],
    *,
    session: AsyncClientSession | None,
) -> tuple[
    list[DependencyGuardContribution],
    list[DependencyGuardContribution],
]:
    """按两类端点签名推进绑定写入所需的内部护栏。

    Args:
        signatures: 角色、势力端点完整签名。
        session: 可选 MongoDB 会话。

    Returns:
        已推进的角色和势力一次性 guard 贡献记录。
    """
    character_signatures, faction_signatures = signatures
    character_queries = [
        {
            "_id": signature[0],
            "character_id": character_id,
            "version": signature[1],
            "status": "active",
            "is_core_character": True,
            "is_deleted": {"$ne": True},
        }
        for character_id, signature in character_signatures.items()
    ]
    faction_queries = [
        {
            "_id": signature[0],
            "faction_id": faction_id,
            "version": signature[1],
            "active_status": "active",
            "level_type": "core",
            "is_deleted": {"$ne": True},
        }
        for faction_id, signature in faction_signatures.items()
    ]
    completed_characters: list[DependencyGuardContribution] = []
    completed_factions: list[DependencyGuardContribution] = []
    try:
        completed_characters = await touch_dependency_endpoint_guards(
            character_repo.collection,
            character_queries,
            session=session,
        )
        completed_factions = await touch_dependency_endpoint_guards(
            faction_repo.collection,
            faction_queries,
            session=session,
        )
    except Exception:
        if session is None:
            await _rollback_binding_endpoint_touches(
                completed_characters,
                completed_factions,
            )
        raise
    return completed_characters, completed_factions


async def _compensate_binding_updates(
    snapshots_and_writes: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
    """精确回滚 standalone 绑定更新且不覆盖并发新版本。

    Args:
        snapshots_and_writes: 按写入顺序保存的写前快照与写后文档。

    Returns:
        无；仅当文档仍停留在本次写后版本时恢复原快照。
    """
    # character_service 已提供跨角色、关系和绑定通用的精确 CAS 快照恢复；
    # 此处延迟导入，避免角色服务初始化时反向导入绑定服务形成循环依赖。
    from backend.services.novel.character_service import (
        _restore_snapshots,
        _updated_compensation_record,
    )

    await _restore_snapshots(
        character_faction_binding_repo,
        [
            _updated_compensation_record(snapshot, written)
            for snapshot, written in snapshots_and_writes
        ],
    )


async def _rollback_failed_binding_write_unit(
    snapshots_and_writes: list[tuple[dict[str, Any], dict[str, Any]]],
    character_touches: list[DependencyGuardContribution],
    faction_touches: list[DependencyGuardContribution],
    *,
    label: str,
) -> None:
    """完整尝试回滚 standalone 绑定写入和两类端点护栏贡献。

    Args:
        snapshots_and_writes: 按写入顺序保存的绑定写前、写后文档。
        character_touches: 本次新增的角色端点护栏贡献。
        faction_touches: 本次新增的势力端点护栏贡献。
        label: 补偿失败时用于定位的业务动作名称。

    Returns:
        无；任一补偿未完成时抛出 RuntimeError。
    """
    failures: list[Exception] = []
    if snapshots_and_writes:
        try:
            await _compensate_binding_updates(snapshots_and_writes)
        except Exception as exc:
            failures.append(exc)
    try:
        await _rollback_binding_endpoint_touches(character_touches, faction_touches)
    except Exception as exc:
        failures.append(exc)
    if failures:
        raise RuntimeError(f"{label}失败，且 standalone 补偿未完整完成") from failures[0]


class CharacterFactionBindingService:
    """维护 active 核心角色与 active 核心势力之间的全书级初始绑定。"""

    @staticmethod
    async def _validate_binding_payloads(
        novel_id: str,
        payloads: list[dict[str, Any]],
        session: AsyncClientSession | None = None,
    ) -> list[str]:
        """批量校验绑定端点、初始状态、主归属唯一性和语义重复。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            payloads: 已转换为字典的绑定创建载荷。
            session: 可选 MongoDB 会话。

        Returns:
            稳定顺序的业务校验错误列表。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        character_ids = sorted(
            {str(payload.get("character_id") or "") for payload in payloads if payload.get("character_id")}
        )
        faction_ids = sorted(
            {str(payload.get("faction_id") or "") for payload in payloads if payload.get("faction_id")}
        )
        characters = await character_repo.get_characters_by_ids(
            novel_id,
            character_ids,
            session=session,
        )
        all_factions = await faction_repo.get_factions_by_novel(novel_id, session=session)
        characters_by_id = {str(character["character_id"]): character for character in characters}
        factions_by_id = {
            str(faction["faction_id"]): faction
            for faction in all_factions
            if str(faction.get("faction_id") or "") in set(faction_ids)
        }
        missing_characters = [
            character_id for character_id in character_ids if character_id not in characters_by_id
        ]
        missing_factions = [
            faction_id for faction_id in faction_ids if faction_id not in factions_by_id
        ]
        if missing_characters or missing_factions:
            raise NotFoundError(
                "角色—势力绑定端点不存在于当前小说: "
                f"characters={missing_characters}, factions={missing_factions}"
            )

        errors: list[str] = []
        conflict_errors: list[str] = []
        semantic_owner: dict[tuple[str, str, str], str] = {}
        primary_owner: dict[str, str] = {}
        semantic_bindings: list[tuple[str, str, str]] = []

        for index, payload in enumerate(payloads):
            label = str(payload.get("binding_ref") or f"bindings[{index}]")
            character_id = str(payload.get("character_id") or "")
            faction_id = str(payload.get("faction_id") or "")
            membership_type = str(_normalize_scalar(payload.get("membership_type")) or "")
            loyalty_level = payload.get("loyalty_level")

            if not character_id or not faction_id:
                errors.append(f"{label}: character_id 与 faction_id 均为必填")
                continue
            if membership_type not in INITIAL_MEMBERSHIP_TYPES:
                errors.append(f"{label}: 初始 membership_type 仅允许 primary|secondary|covert")
            if payload.get("is_active", True) is not True:
                errors.append(f"{label}: 初始绑定的 is_active 必须为 true")
            if payload.get("joined_volume_id") is not None or payload.get("left_volume_id") is not None:
                errors.append(f"{label}: 本轮全书级绑定不接受 joined/left volume ID")
            if loyalty_level is not None and (
                isinstance(loyalty_level, bool)
                or not isinstance(loyalty_level, int)
                or not 1 <= loyalty_level <= 5
            ):
                errors.append(f"{label}: loyalty_level 必须为空或为 1 至 5 的整数")

            character = characters_by_id.get(character_id)
            if character is None:
                errors.append(f"{label}: 角色 {character_id} 不存在于当前小说")
            elif character.get("status") != "active" or character.get("is_core_character") is not True:
                errors.append(f"{label}: 角色 {character_id} 必须是 active 核心角色")

            faction = factions_by_id.get(faction_id)
            if faction is None:
                errors.append(f"{label}: 势力 {faction_id} 不存在于当前小说")
            elif faction.get("level_type") != "core" or faction.get("active_status") != "active":
                errors.append(f"{label}: 势力 {faction_id} 必须是 active 核心势力")

            if membership_type in INITIAL_MEMBERSHIP_TYPES:
                semantic = (character_id, faction_id, membership_type)
                previous_label = semantic_owner.get(semantic)
                if previous_label is not None:
                    conflict_errors.append(f"{label}: 与 {previous_label} 构成重复活动绑定")
                else:
                    semantic_owner[semantic] = label
                semantic_bindings.append(semantic)

            if membership_type == "primary":
                previous_primary = primary_owner.get(character_id)
                if previous_primary is not None:
                    conflict_errors.append(
                        f"{label}: 角色 {character_id} 已在 {previous_primary} 声明主归属"
                    )
                else:
                    primary_owner[character_id] = label

        existing_semantic = await character_faction_binding_repo.find_active_semantic_bindings(
            novel_id,
            semantic_bindings,
            session=session,
        )
        for binding in existing_semantic:
            conflict_errors.append(
                "活动绑定已存在: "
                f"{binding['character_id']}->{binding['faction_id']}({binding['membership_type']})"
            )

        primary_character_ids = [
            character_id
            for character_id, _ in primary_owner.items()
            if character_id
        ]
        existing_primary = await character_faction_binding_repo.find_active_primary_bindings(
            novel_id,
            primary_character_ids,
            session=session,
        )
        for binding in existing_primary:
            conflict_errors.append(
                f"角色 {binding['character_id']} 已有活动主归属绑定 {binding['binding_id']}"
            )
        if errors:
            return errors
        if conflict_errors:
            raise DuplicateKeyError(
                "角色—势力绑定唯一性冲突: " + "; ".join(conflict_errors)
            )
        return []

    @staticmethod
    async def bulk_create_bindings(
        novel_id: str,
        payloads: list[Any],
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """批量创建全书级角色—势力绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            payloads: 正式绑定创建载荷或已映射 character_id 的生成候选。
            session: 可选 MongoDB 会话，用于纳入上层聚合写入。

        Returns:
            按输入顺序返回正式绑定文档。
        """
        normalized_payloads = [_payload_to_dict(payload) for payload in payloads]
        if not normalized_payloads:
            return []
        errors = await CharacterFactionBindingService._validate_binding_payloads(
            novel_id,
            normalized_payloads,
            session=session,
        )
        if errors:
            raise ValueError("角色—势力绑定校验失败: " + "; ".join(errors))
        endpoint_signatures = await _load_usable_binding_endpoint_signatures(
            novel_id,
            normalized_payloads,
            session=session,
        )

        binding_ids = await id_sequence_repo.allocate_many(
            novel_id,
            "character_faction_binding",
            "cfb",
            len(normalized_payloads),
            session=session,
        )
        documents: list[dict[str, Any]] = []
        for payload, binding_id in zip(normalized_payloads, binding_ids):
            suffix = int(binding_id.rsplit("_", 1)[-1])
            notes_value = payload.get("notes")
            if notes_value is None:
                notes_value = payload.get("reason")
            document = {
                "novel_id": novel_id,
                "binding_id": binding_id,
                "character_id": str(payload["character_id"]),
                "faction_id": str(payload["faction_id"]),
                "membership_type": str(_normalize_scalar(payload["membership_type"])),
                "role_title": (
                    str(payload["role_title"]).strip()
                    if payload.get("role_title") is not None
                    else None
                ),
                "public_status": (
                    str(payload["public_status"]).strip()
                    if payload.get("public_status") is not None
                    else None
                ),
                "loyalty_level": payload.get("loyalty_level"),
                "joined_volume_id": None,
                "left_volume_id": None,
                "is_active": True,
                "notes": str(notes_value).strip() if notes_value is not None else None,
                "sort_order": suffix * 10,
                "version": 1,
            }
            # 人工单条和核心角色确认分别使用自己的精确幂等元数据。
            for field in (
                "creation_idempotency_key_hash",
                "creation_request_hash",
                "core_batch_idempotency_key_hash",
                "core_batch_request_hash",
                "core_batch_local_ref",
            ):
                if payload.get(field) is not None:
                    document[field] = payload[field]
            documents.append(document)

        # 两类端点均先推进内部护栏，避免聚合补偿删除已被绑定引用的新主档。
        character_touches, faction_touches = await _touch_binding_endpoint_signatures(
            endpoint_signatures,
            session=session,
        )
        created: list[dict[str, Any]] = []
        try:
            created = await character_faction_binding_repo.insert_bindings(
                documents,
                session=session,
            )
            current_signatures = await _load_usable_binding_endpoint_signatures(
                novel_id,
                normalized_payloads,
                session=session,
            )
            if current_signatures != endpoint_signatures:
                raise DuplicateKeyError("角色—势力绑定创建期间端点已被并发修改，请重试")
        except Exception as exc:
            if session is None:
                failures: list[Exception] = []
                if created:
                    try:
                        compensated = (
                            await character_faction_binding_repo.delete_bindings_exact(
                                novel_id,
                                binding_ids,
                            )
                        )
                        if compensated != len(created):
                            raise RuntimeError("绑定精确补偿数量不完整")
                    except Exception as compensation_exc:
                        failures.append(compensation_exc)
                try:
                    await _rollback_binding_endpoint_touches(
                        character_touches,
                        faction_touches,
                    )
                except Exception as compensation_exc:
                    failures.append(compensation_exc)
                if failures:
                    raise RuntimeError(
                        "角色—势力绑定创建失败，且 standalone 补偿未完整完成"
                    ) from failures[0]
            raise
        return created

    @staticmethod
    async def create_binding(
        novel_id: str,
        payload: Any,
        *,
        idempotency_key: str,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """创建一条人工全书级角色—势力绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            payload: 绑定创建 DTO 或等价映射。
            idempotency_key: 调用方提供的创建幂等键。
            session: 可选 MongoDB 会话。

        Returns:
            新创建的正式绑定文档。
        """
        source = _payload_to_dict(payload)
        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum({"novel_id": novel_id, "payload": source})

        async def _find_replay(
            active_session: AsyncClientSession | None,
        ) -> dict[str, Any] | None:
            """读取并校验同一幂等键的原绑定创建结果。"""
            existing = await character_faction_binding_repo.find_by_creation_idempotency(
                novel_id,
                key_hash,
                session=active_session,
            )
            if existing is None:
                return None
            if existing.get("creation_request_hash") != request_hash:
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的角色阵营绑定创建请求",
                    status_code=409,
                )
            return existing

        async def _create(
            active_session: AsyncClientSession | None,
        ) -> dict[str, Any]:
            """在一个写入单元内完成幂等回放与绑定创建。"""
            await novel_repo.get_novel_by_id(novel_id, session=active_session)
            replay = await _find_replay(active_session)
            if replay is not None:
                return replay
            if source.get("membership_type") == "primary":
                raise ValueError(
                    "人工单条创建只允许 secondary 或 covert；"
                    "主归属必须先创建既有绑定再使用 /primary 切换"
                )
            source["creation_idempotency_key_hash"] = key_hash
            source["creation_request_hash"] = request_hash
            created = await CharacterFactionBindingService.bulk_create_bindings(
                novel_id,
                [source],
                session=active_session,
            )
            return created[0]

        if session is not None:
            return await _create(session)
        try:
            return await run_mongo_write_unit(_create, "create_character_faction_binding")
        except DuplicateKeyError:
            # 唯一索引解决并发抢占，输家回放首次成功写入的业务 ID。
            replay = await _find_replay(None)
            if replay is not None:
                return replay
            raise

    @staticmethod
    async def get_binding(
        novel_id: str,
        binding_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """读取指定小说内的一条角色—势力绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            include_deleted: 是否允许读取回收站中的绑定。
            session: 可选 MongoDB 会话。

        Returns:
            角色—势力绑定文档。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        return await character_faction_binding_repo.get_binding(
            novel_id,
            binding_id,
            include_deleted=include_deleted,
            session=session,
        )

    @staticmethod
    async def list_bindings(
        novel_id: str,
        *,
        character_id: str | None = None,
        faction_id: str | None = None,
        membership_type: str | None = None,
        is_active: bool | None = True,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """列出小说内角色—势力绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            character_id: 可选角色业务 ID。
            faction_id: 可选势力业务 ID。
            membership_type: 可选成员类型。
            is_active: 可选活动状态过滤。
            session: 可选 MongoDB 会话。

        Returns:
            稳定排序的绑定文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        if membership_type is not None and membership_type not in INITIAL_MEMBERSHIP_TYPES:
            raise ValueError(f"本轮不支持 membership_type={membership_type}")
        if character_id:
            character = await character_repo.get_character(novel_id, character_id, session=session)
            if character.get("status") != "active" or character.get("is_core_character") is not True:
                raise ValueError(f"角色 {character_id} 必须是 active 核心角色")
        if faction_id:
            faction = await faction_repo.get_faction(novel_id, faction_id, session=session)
            if faction.get("level_type") != "core" or faction.get("active_status") != "active":
                raise ValueError(f"势力 {faction_id} 必须是 active 核心势力")
        return await character_faction_binding_repo.list_bindings(
            novel_id,
            character_id=character_id,
            faction_id=faction_id,
            membership_type=membership_type,
            is_active=is_active,
            session=session,
        )

    @staticmethod
    def _ensure_expected_version(binding: dict[str, Any], expected_version: int) -> None:
        """校验绑定当前公开版本与调用方版本完全一致。

        Args:
            binding: 当前绑定文档。
            expected_version: 调用方提交的版本。

        Returns:
            无；版本不一致时抛出 409 领域冲突。
        """
        if isinstance(expected_version, bool) or not isinstance(expected_version, int):
            raise ValueError("expected_version 必须为正整数")
        if expected_version < 1:
            raise ValueError("expected_version 必须大于等于 1")
        actual_version = int(binding["version"])
        if actual_version != expected_version:
            raise DuplicateKeyError(
                f"角色—势力绑定 '{binding.get('binding_id')}' 版本冲突："
                f"expected={expected_version}, actual={actual_version}"
            )

    @staticmethod
    async def _current_blockers(
        novel_id: str,
        binding: dict[str, Any],
        *,
        session: AsyncClientSession | None,
    ) -> tuple[list[str], list[str]]:
        """按角色和势力正式事实重算绑定的自动阻断来源。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding: 当前绑定文档。
            session: 可选 MongoDB 会话。

        Returns:
            角色阻断 ID 与势力阻断 ID 组成的二元组。
        """
        character_id = str(binding["character_id"])
        faction_id = str(binding["faction_id"])
        character = await character_repo.get_character(
            novel_id,
            character_id,
            include_deleted=True,
            session=session,
        )
        faction = await faction_repo.get_faction(
            novel_id,
            faction_id,
            include_deleted=True,
            session=session,
        )
        character_blockers = []
        if (
            character.get("is_deleted") is True
            or character.get("status") != "active"
            or character.get("is_core_character") is not True
        ):
            character_blockers.append(character_id)
        faction_blockers = []
        if (
            faction.get("is_deleted") is True
            or faction.get("active_status") != "active"
            or faction.get("level_type") != "core"
        ):
            faction_blockers.append(faction_id)
        return character_blockers, faction_blockers

    @staticmethod
    async def _validate_effective_uniqueness(
        novel_id: str,
        binding: dict[str, Any],
        *,
        effective_active: bool,
        session: AsyncClientSession | None,
    ) -> None:
        """校验即将生效的绑定不会制造语义重复或第二个主归属。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding: 合并更新字段后的绑定视图。
            effective_active: 该视图是否会成为活动有效绑定。
            session: 可选 MongoDB 会话。

        Returns:
            无；冲突时抛出 409 领域异常。
        """
        if not effective_active:
            return
        binding_id = str(binding["binding_id"])
        character_id = str(binding["character_id"])
        faction_id = str(binding["faction_id"])
        membership_type = str(binding["membership_type"])
        semantic_conflicts = (
            await character_faction_binding_repo.find_active_semantic_bindings(
                novel_id,
                [(character_id, faction_id, membership_type)],
                exclude_binding_id=binding_id,
                session=session,
            )
        )
        if semantic_conflicts:
            raise DuplicateKeyError(
                "角色—势力活动语义绑定已存在: "
                f"{semantic_conflicts[0]['binding_id']}"
            )
        if membership_type == "primary":
            primary_conflicts = (
                await character_faction_binding_repo.find_active_primary_bindings(
                    novel_id,
                    [character_id],
                    exclude_binding_id=binding_id,
                    session=session,
                )
            )
            if primary_conflicts:
                raise DuplicateKeyError(
                    f"角色 {character_id} 已有活动主归属绑定 "
                    f"{primary_conflicts[0]['binding_id']}"
                )

    @staticmethod
    async def update_binding(novel_id: str, binding_id: str, payload: Any, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """更新绑定内容，端点保持不可变且 primary 进出必须走专用切换。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            payload: 含 expected_version 的严格更新请求。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            递增版本后的完整绑定文档。
        """
        if hasattr(payload, "model_dump"):
            source = dict(payload.model_dump(mode="json", exclude_unset=True))
        else:
            source = dict(payload)
        expected_version = source.pop("expected_version", None)
        if expected_version is None:
            raise ValueError("绑定更新必须提供 expected_version")

        async def _update(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内复核端点并执行绑定 CAS 更新。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await character_faction_binding_repo.get_binding(
                novel_id,
                binding_id,
                session=session,
            )
            CharacterFactionBindingService._ensure_expected_version(
                current,
                expected_version,
            )
            update_fields = {
                field: source[field]
                for field in BINDING_CONTENT_FIELDS
                if field in source
            }
            if not update_fields:
                raise ValueError("绑定更新至少需要一个可修改字段")

            current_type = str(current["membership_type"])
            next_type = str(
                _normalize_scalar(update_fields.get("membership_type", current_type))
            )
            if next_type not in INITIAL_MEMBERSHIP_TYPES:
                raise ValueError(f"不支持的 membership_type={next_type}")
            if next_type != current_type and "primary" in {current_type, next_type}:
                raise ValueError("primary 归属的进入或离开必须使用 /primary 接口")
            if "membership_type" in update_fields:
                update_fields["membership_type"] = next_type
            for field in ("role_title", "public_status", "notes"):
                if field in update_fields and update_fields[field] is not None:
                    normalized = str(update_fields[field]).strip()
                    update_fields[field] = normalized or None
            loyalty_level = update_fields.get("loyalty_level")
            if loyalty_level is not None and (
                isinstance(loyalty_level, bool)
                or not isinstance(loyalty_level, int)
                or not 1 <= loyalty_level <= 5
            ):
                raise ValueError("loyalty_level 必须为空或为 1 至 5 的整数")

            character_blockers, faction_blockers = (
                await CharacterFactionBindingService._current_blockers(
                    novel_id,
                    current,
                    session=session,
                )
            )
            effective_active = bool(
                current["user_is_active"]
                and not character_blockers
                and not faction_blockers
            )
            validation_view = {
                **current,
                **update_fields,
                "membership_type": next_type,
                "joined_volume_id": None,
                "left_volume_id": None,
                "disabled_by_character_ids": character_blockers,
                "disabled_by_faction_ids": faction_blockers,
                "is_active": effective_active,
            }
            await CharacterFactionBindingService._validate_effective_uniqueness(
                novel_id,
                validation_view,
                effective_active=effective_active,
                session=session,
            )

            endpoint_signatures = None
            character_touches: list[DependencyGuardContribution] = []
            faction_touches: list[DependencyGuardContribution] = []
            if effective_active:
                endpoint_signatures = await _load_usable_binding_endpoint_signatures(
                    novel_id,
                    [current],
                    session=session,
                )
                character_touches, faction_touches = (
                    await _touch_binding_endpoint_signatures(
                        endpoint_signatures,
                        session=session,
                    )
                )
            writes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            try:
                written = await character_faction_binding_repo.update_binding(
                    novel_id,
                    binding_id,
                    {
                        **update_fields,
                        "joined_volume_id": None,
                        "left_volume_id": None,
                        "disabled_by_character_ids": character_blockers,
                        "disabled_by_faction_ids": faction_blockers,
                        "is_active": effective_active,
                    },
                    expected_version,
                    session=session,
                )
                writes.append((current, written))
                if endpoint_signatures is not None:
                    current_signatures = (
                        await _load_usable_binding_endpoint_signatures(
                            novel_id,
                            [current],
                            session=session,
                        )
                    )
                    if current_signatures != endpoint_signatures:
                        raise DuplicateKeyError(
                            "角色—势力绑定更新期间端点已被并发修改，请重试"
                        )
                else:
                    after_blockers = (
                        await CharacterFactionBindingService._current_blockers(
                            novel_id,
                            current,
                            session=session,
                        )
                    )
                    if after_blockers != (character_blockers, faction_blockers):
                        raise DuplicateKeyError(
                            "角色—势力绑定更新期间端点已被并发修改，请重试"
                        )
                return written
            except Exception:
                if session is None:
                    await _rollback_failed_binding_write_unit(
                        writes,
                        character_touches,
                        faction_touches,
                        label="角色—势力绑定更新",
                    )
                raise

        if session is not None:
            return await _update(session)

        return await run_mongo_write_unit(_update, "update_character_faction_binding")

    @staticmethod
    async def set_binding_active(novel_id: str, binding_id: str, *, expected_version: int, is_active: bool, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """修改用户启停意图并结合当前端点阻断计算实际有效态。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。
            is_active: 用户期望的启用状态。

            session: 调用方事务；提供时不另开事务。

        Returns:
            递增版本后的完整绑定文档。
        """

        async def _set_active(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内复核端点并执行启停 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await character_faction_binding_repo.get_binding(
                novel_id,
                binding_id,
                session=session,
            )
            CharacterFactionBindingService._ensure_expected_version(
                current,
                expected_version,
            )
            character_blockers, faction_blockers = (
                await CharacterFactionBindingService._current_blockers(
                    novel_id,
                    current,
                    session=session,
                )
            )
            effective_active = bool(
                is_active and not character_blockers and not faction_blockers
            )
            if (
                is_active
                and not effective_active
                and str(current["membership_type"]) == "primary"
            ):
                primary_conflicts = (
                    await character_faction_binding_repo.find_active_primary_bindings(
                        novel_id,
                        [str(current["character_id"])],
                        exclude_binding_id=binding_id,
                        session=session,
                    )
                )
                if primary_conflicts:
                    raise DuplicateKeyError(
                        f"角色 {current['character_id']} 已有活动主归属绑定 "
                        f"{primary_conflicts[0]['binding_id']}"
                    )
            validation_view = {
                **current,
                "user_is_active": is_active,
                "disabled_by_character_ids": character_blockers,
                "disabled_by_faction_ids": faction_blockers,
                "is_active": effective_active,
            }
            await CharacterFactionBindingService._validate_effective_uniqueness(
                novel_id,
                validation_view,
                effective_active=effective_active,
                session=session,
            )

            endpoint_signatures = None
            character_touches: list[DependencyGuardContribution] = []
            faction_touches: list[DependencyGuardContribution] = []
            if effective_active:
                endpoint_signatures = await _load_usable_binding_endpoint_signatures(
                    novel_id,
                    [current],
                    session=session,
                )
                character_touches, faction_touches = (
                    await _touch_binding_endpoint_signatures(
                        endpoint_signatures,
                        session=session,
                    )
                )
            writes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            try:
                written = await character_faction_binding_repo.update_binding(
                    novel_id,
                    binding_id,
                    {
                        "user_is_active": is_active,
                        "disabled_by_character_ids": character_blockers,
                        "disabled_by_faction_ids": faction_blockers,
                        "is_active": effective_active,
                    },
                    expected_version,
                    session=session,
                )
                writes.append((current, written))
                if endpoint_signatures is not None:
                    current_signatures = (
                        await _load_usable_binding_endpoint_signatures(
                            novel_id,
                            [current],
                            session=session,
                        )
                    )
                    if current_signatures != endpoint_signatures:
                        raise DuplicateKeyError(
                            "角色—势力绑定启停期间端点已被并发修改，请重试"
                        )
                else:
                    after_blockers = (
                        await CharacterFactionBindingService._current_blockers(
                            novel_id,
                            current,
                            session=session,
                        )
                    )
                    if after_blockers != (character_blockers, faction_blockers):
                        raise DuplicateKeyError(
                            "角色—势力绑定启停期间端点已被并发修改，请重试"
                        )
                return written
            except Exception:
                if session is None:
                    await _rollback_failed_binding_write_unit(
                        writes,
                        character_touches,
                        faction_touches,
                        label="角色—势力绑定启停",
                    )
                raise

        if session is not None:
            return await _set_active(session)

        return await run_mongo_write_unit(
            _set_active,
            "set_character_faction_binding_active",
        )

    @staticmethod
    async def switch_primary_binding(novel_id: str, binding_id: str, payload: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """把既有绑定原子切换为主归属并停用原活动 primary。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 将成为 primary 的既有绑定业务 ID。
            payload: 目标版本与被替换 primary 精确版本映射。
            idempotency_key: 调用方提供的切换幂等键。

            session: 调用方事务；提供时不另开事务。

        Returns:
            包含 primary_binding 与 affected_bindings 的切换结果。
        """
        source = _payload_to_dict(payload)
        expected_version = source.get("expected_version")
        if expected_version is None:
            raise ValueError("主归属切换必须提供 expected_version")
        replaced_expected_versions = source.get("replaced_expected_versions")
        if not isinstance(replaced_expected_versions, dict):
            raise ValueError("replaced_expected_versions 必须为绑定版本映射")
        normalized_replaced_versions: dict[str, int] = {}
        for replaced_id, version in replaced_expected_versions.items():
            if (
                not isinstance(replaced_id, str)
                or not replaced_id.startswith("cfb_")
                or isinstance(version, bool)
                or not isinstance(version, int)
                or version < 1
            ):
                raise ValueError("replaced_expected_versions 包含非法绑定 ID 或版本")
            normalized_replaced_versions[replaced_id] = version
        source["replaced_expected_versions"] = normalized_replaced_versions
        key_hash = hash_idempotency_key(idempotency_key)
        request_hash = checksum(
            {
                "novel_id": novel_id,
                "binding_id": binding_id,
                "payload": source,
            }
        )

        async def _find_replay(
            session: AsyncClientSession | None,
        ) -> dict[str, Any] | None:
            """读取并校验同一幂等键的既有主归属切换结果。"""
            existing = (
                await character_faction_binding_repo.find_by_primary_switch_idempotency(
                    novel_id,
                    key_hash,
                    session=session,
                )
            )
            if existing is None:
                return None
            if existing.get("primary_switch_request_hash") != request_hash:
                raise GenerationDomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 Idempotency-Key 已用于不同的主归属切换请求",
                    status_code=409,
                )
            affected_ids = [
                str(value)
                for value in existing.get("primary_switch_affected_binding_ids", [])
                if isinstance(value, str)
            ]
            affected = await character_faction_binding_repo.get_bindings_by_ids(
                novel_id,
                affected_ids,
                include_deleted=True,
                session=session,
            )
            return {
                "primary_binding": existing,
                "affected_bindings": affected,
            }

        async def _switch(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内停用旧 primary 并激活既有目标。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            replay = await _find_replay(session)
            if replay is not None:
                return replay
            target = await character_faction_binding_repo.get_binding(
                novel_id,
                binding_id,
                session=session,
            )
            CharacterFactionBindingService._ensure_expected_version(
                target,
                expected_version,
            )
            character_blockers, faction_blockers = (
                await CharacterFactionBindingService._current_blockers(
                    novel_id,
                    target,
                    session=session,
                )
            )
            if character_blockers or faction_blockers:
                raise ValueError(
                    "主归属目标端点当前不可用: "
                    f"characters={character_blockers}, factions={faction_blockers}"
                )

            character_id = str(target["character_id"])
            primary_bindings = (
                await character_faction_binding_repo.list_primary_bindings_for_character(
                    novel_id,
                    character_id,
                    session=session,
                )
            )
            # standalone 顺序写会短暂先停用旧 primary；未完成声明只允许同一幂等
            # 请求续写，其他切换不能趁“暂无活动 primary”的窗口抢占。
            resumed_claims: list[dict[str, Any]] = []
            for primary in primary_bindings:
                claimed_key = primary.get("replaced_by_primary_switch_key_hash")
                claimed_target_id = primary.get("replaced_by_primary_binding_id")
                if not isinstance(claimed_key, str) or not isinstance(
                    claimed_target_id,
                    str,
                ):
                    continue
                if primary.get("replaced_by_primary_switch_completed") is True:
                    continue
                try:
                    claimed_target = await character_faction_binding_repo.get_binding(
                        novel_id,
                        claimed_target_id,
                        include_deleted=True,
                        session=session,
                    )
                except NotFoundError:
                    claimed_target = None
                if (
                    claimed_target is not None
                    and claimed_target.get("primary_switch_idempotency_key_hash")
                    == claimed_key
                ):
                    continue
                claimed_expected_version = primary.get(
                    "replaced_by_primary_expected_version"
                )
                primary_id = str(primary["binding_id"])
                if (
                    claimed_key == key_hash
                    and claimed_target_id == binding_id
                    and normalized_replaced_versions.get(primary_id)
                    == claimed_expected_version
                    and int(primary["version"])
                    == int(claimed_expected_version or 0) + 1
                    and primary.get("is_active") is False
                ):
                    resumed_claims.append(primary)
                    continue
                raise DuplicateKeyError("检测到尚未完成的主归属切换，请重试")

            replaced = [
                primary
                for primary in primary_bindings
                if primary.get("is_active") is True
                and str(primary["binding_id"]) != binding_id
            ]
            actual_replaced_versions = {
                str(primary["binding_id"]): int(primary["version"])
                for primary in replaced
            }
            actual_replaced_versions.update(
                {
                    str(primary["binding_id"]): int(
                        primary["replaced_by_primary_expected_version"]
                    )
                    for primary in resumed_claims
                }
            )
            if normalized_replaced_versions != actual_replaced_versions:
                raise DuplicateKeyError(
                    "被替换主归属版本集合冲突："
                    f"expected={normalized_replaced_versions}, "
                    f"actual={actual_replaced_versions}"
                )

            resumed_write_records: list[
                tuple[dict[str, Any], dict[str, Any]]
            ] = []
            for claimed in resumed_claims:
                previous_state = claimed.get("replaced_by_primary_previous_state")
                if not isinstance(previous_state, dict):
                    raise DuplicateKeyError("未完成主归属切换缺少可补偿的旧状态")
                snapshot = {**claimed, **previous_state}
                for internal_field in (
                    "replaced_by_primary_switch_key_hash",
                    "replaced_by_primary_binding_id",
                    "replaced_by_primary_expected_version",
                    "replaced_by_primary_previous_state",
                    "replaced_by_primary_switch_completed",
                ):
                    snapshot.pop(internal_field, None)
                resumed_write_records.append((snapshot, claimed))

            endpoint_signatures = await _load_usable_binding_endpoint_signatures(
                novel_id,
                [target],
                session=session,
            )
            character_touches, faction_touches = (
                await _touch_binding_endpoint_signatures(
                    endpoint_signatures,
                    session=session,
                )
            )
            writes = list(resumed_write_records)
            affected: list[dict[str, Any]] = list(resumed_claims)
            try:
                for previous in sorted(
                    replaced,
                    key=lambda item: str(item["binding_id"]),
                ):
                    written_previous = (
                        await character_faction_binding_repo.update_binding(
                            novel_id,
                            str(previous["binding_id"]),
                            {
                                "user_is_active": False,
                                "is_active": False,
                                "replaced_by_primary_switch_key_hash": key_hash,
                                "replaced_by_primary_binding_id": binding_id,
                                "replaced_by_primary_expected_version": (
                                    normalized_replaced_versions[
                                        str(previous["binding_id"])
                                    ]
                                ),
                                "replaced_by_primary_previous_state": {
                                    "version": int(previous["version"]),
                                    "user_is_active": bool(
                                        previous["user_is_active"]
                                    ),
                                    "is_active": bool(previous.get("is_active")),
                                    **(
                                        {"updated_at": previous["updated_at"]}
                                        if "updated_at" in previous
                                        else {}
                                    ),
                                },
                                "replaced_by_primary_switch_completed": False,
                            },
                            normalized_replaced_versions[str(previous["binding_id"])],
                            session=session,
                        )
                    )
                    writes.append((previous, written_previous))
                    affected.append(written_previous)

                written_target = await character_faction_binding_repo.update_binding(
                    novel_id,
                    binding_id,
                    {
                        "membership_type": "primary",
                        "joined_volume_id": None,
                        "left_volume_id": None,
                        "user_is_active": True,
                        "disabled_by_character_ids": [],
                        "disabled_by_faction_ids": [],
                        "is_active": True,
                        "primary_switch_idempotency_key_hash": key_hash,
                        "primary_switch_request_hash": request_hash,
                        "primary_switch_affected_binding_ids": [
                            str(item["binding_id"]) for item in affected
                        ],
                    },
                    expected_version,
                    session=session,
                )
                writes.append((target, written_target))
                current_signatures = await _load_usable_binding_endpoint_signatures(
                    novel_id,
                    [target],
                    session=session,
                )
                if current_signatures != endpoint_signatures:
                    raise DuplicateKeyError(
                        "主归属切换期间端点已被并发修改，请重试"
                    )
                await character_faction_binding_repo.mark_primary_switch_claims_complete(
                    novel_id,
                    [
                        (str(item["binding_id"]), int(item["version"]))
                        for item in affected
                    ],
                    key_hash,
                    session=session,
                )
                return {
                    "primary_binding": written_target,
                    "affected_bindings": affected,
                }
            except Exception:
                if session is None:
                    await _rollback_failed_binding_write_unit(
                        writes,
                        character_touches,
                        faction_touches,
                        label="主归属切换",
                    )
                raise

        if session is not None:
            return await _switch(session)

        try:
            return await run_mongo_write_unit(
                _switch,
                "switch_character_faction_binding_primary",
            )
        except DuplicateKeyError:
            replay = await _find_replay(None)
            if replay is not None:
                return replay
            raise

    @staticmethod
    async def soft_delete_binding(novel_id: str, binding_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """把角色—势力绑定移入回收站。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            软删除后的完整绑定文档。
        """

        async def _delete(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内执行绑定软删除 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            return await character_faction_binding_repo.soft_delete_binding(
                novel_id,
                binding_id,
                expected_version,
                session=session,
            )

        if session is not None:
            return await _delete(session)

        return await run_mongo_write_unit(
            _delete,
            "soft_delete_character_faction_binding",
        )

    @staticmethod
    async def list_deleted_bindings(novel_id: str) -> list[dict[str, Any]]:
        """读取小说角色—势力绑定回收站。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。

        Returns:
            已软删除绑定的稳定排序列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await character_faction_binding_repo.list_deleted_bindings(novel_id)

    @staticmethod
    async def restore_binding(novel_id: str, binding_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """从回收站恢复绑定并重新计算端点阻断及活动唯一性。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            恢复后的完整绑定文档。
        """

        async def _restore(session: AsyncClientSession | None) -> dict[str, Any]:
            """在一个写入单元内复核端点并执行恢复 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await character_faction_binding_repo.get_binding(
                novel_id,
                binding_id,
                include_deleted=True,
                session=session,
            )
            if current.get("is_deleted") is not True:
                raise NotFoundError(f"角色—势力绑定 '{binding_id}' 不在回收站")
            CharacterFactionBindingService._ensure_expected_version(
                current,
                expected_version,
            )
            character_blockers, faction_blockers = (
                await CharacterFactionBindingService._current_blockers(
                    novel_id,
                    current,
                    session=session,
                )
            )
            effective_active = bool(
                current["user_is_active"]
                and not character_blockers
                and not faction_blockers
            )
            if (
                current["user_is_active"]
                and not effective_active
                and str(current["membership_type"]) == "primary"
            ):
                primary_conflicts = (
                    await character_faction_binding_repo.find_active_primary_bindings(
                        novel_id,
                        [str(current["character_id"])],
                        exclude_binding_id=binding_id,
                        session=session,
                    )
                )
                if primary_conflicts:
                    raise DuplicateKeyError(
                        f"角色 {current['character_id']} 已有活动主归属绑定 "
                        f"{primary_conflicts[0]['binding_id']}"
                    )
            validation_view = {
                **current,
                "is_deleted": False,
                "disabled_by_character_ids": character_blockers,
                "disabled_by_faction_ids": faction_blockers,
                "is_active": effective_active,
            }
            await CharacterFactionBindingService._validate_effective_uniqueness(
                novel_id,
                validation_view,
                effective_active=effective_active,
                session=session,
            )

            endpoint_signatures = None
            character_touches: list[DependencyGuardContribution] = []
            faction_touches: list[DependencyGuardContribution] = []
            if effective_active:
                endpoint_signatures = await _load_usable_binding_endpoint_signatures(
                    novel_id,
                    [current],
                    session=session,
                )
                character_touches, faction_touches = (
                    await _touch_binding_endpoint_signatures(
                        endpoint_signatures,
                        session=session,
                    )
                )
            writes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            try:
                restored = await character_faction_binding_repo.restore_binding(
                    novel_id,
                    binding_id,
                    expected_version,
                    effective_active=effective_active,
                    disabled_by_character_ids=character_blockers,
                    disabled_by_faction_ids=faction_blockers,
                    session=session,
                )
                writes.append((current, restored))
                if endpoint_signatures is not None:
                    current_signatures = (
                        await _load_usable_binding_endpoint_signatures(
                            novel_id,
                            [current],
                            session=session,
                        )
                    )
                    if current_signatures != endpoint_signatures:
                        raise DuplicateKeyError(
                            "角色—势力绑定恢复期间端点已被并发修改，请重试"
                        )
                else:
                    after_blockers = (
                        await CharacterFactionBindingService._current_blockers(
                            novel_id,
                            current,
                            session=session,
                        )
                    )
                    if after_blockers != (character_blockers, faction_blockers):
                        raise DuplicateKeyError(
                            "角色—势力绑定恢复期间端点已被并发修改，请重试"
                        )
                return restored
            except Exception:
                if session is None:
                    await _rollback_failed_binding_write_unit(
                        writes,
                        character_touches,
                        faction_touches,
                        label="角色—势力绑定恢复",
                    )
                raise

        if session is not None:
            return await _restore(session)

        return await run_mongo_write_unit(
            _restore,
            "restore_character_faction_binding",
        )

    @staticmethod
    async def hard_delete_binding(
        novel_id: str,
        binding_id: str,
        *,
        expected_version: int,
    ) -> bool:
        """物理删除回收站中的角色—势力绑定。

        Args:
            novel_id: 小说 MongoDB ObjectId 字符串。
            binding_id: 稳定绑定业务 ID。
            expected_version: 调用方持有的乐观锁版本。

        Returns:
            删除成功时返回 True。
        """

        async def _hard_delete(session: AsyncClientSession | None) -> bool:
            """在一个写入单元内执行绑定硬删除 CAS。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            return await character_faction_binding_repo.hard_delete_binding(
                novel_id,
                binding_id,
                expected_version,
                session=session,
            )

        return await run_mongo_write_unit(
            _hard_delete,
            "hard_delete_character_faction_binding",
        )
