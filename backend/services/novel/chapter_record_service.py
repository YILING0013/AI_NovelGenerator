"""作者确认章后事实；记录、来源保护和成功回执共用一个事务。"""

from copy import deepcopy
import hashlib
from typing import Literal, Mapping

from bson import ObjectId
from pydantic import ValidationError

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import touch_dependency_endpoint_guards
from backend.db.errors import IdempotencyConflictError, NotFoundError, VersionConflictError
from backend.db.repositories.confirmation_receipt_repository import ConfirmationReceiptRepository
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import build_idempotency_fingerprint, validate_expected_version
from backend.services.novel.chapter_record_contract import (
    ChapterEventConfirmV1, ChapterReportConfirmV1, ChapterRecordVoidV1,
    ChapterEventReadV1, ChapterReportReadV1,
    ChapterPsychologicalStateConfirmV1, ChapterPsychologicalStateResultV1,
    ChapterItemOwnerConfirmV1, ChapterItemOwnerResultV1,
    ChapterCharacterRelationStateConfirmV1, ChapterCharacterRelationStateResultV1,
    serialize_chapter_record,
)
from backend.services.novel.chapter_record_source import (
    RELATED_ENTITIES, load_chapter_record_source_in_session,
    protect_chapter_record_sources,
)
from backend.services.novel.character_fact_contract import validate_character_fact_receipt
from backend.services.novel.character_relation_fact_contract import validate_character_relation_fact_receipt
from backend.services.novel.character_volume_state_service import CharacterVolumeStateService
from backend.services.novel.chapter_revision_contract import serialize_chapter_revision
from backend.services.novel.chapter_check_contract import (
    CHAPTER_ITEM_OWNER_CHECK_TASK, ChapterItemOwnerCheckInputV1,
)
from backend.services.novel.chapter_check_service import (
    load_chapter_item_owner_sources_in_session,
)
from backend.services.novel.item_service import ItemService
from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint


RECORD_KINDS = {"event": "events", "report": "chapter_reports", "history": "entity_state_history"}
confirmation_receipt_repo = ConfirmationReceiptRepository(
    "chapter_record_confirmation_receipts", "章后确认键已被占用，请使用原请求重试",
)


async def _replay(novel_id, fingerprint, *, expected_operation: str, session, expected_receipt_schema: str | None = None):
    """先返回原成功结果，来源后来改稿或回收不触发重复执行。

    Args:
        novel_id: 小说范围。
        fingerprint: 本次请求的键和内容摘要。
        expected_operation: 调用方固定的原命令类型，不从已存回执推断。
        session: 当前确认事务。
        expected_receipt_schema: 人物、关系或物品事实的完整回执标记；None 只接受旧无标记回执。
    Returns:
        原成功响应；没有回执时返回 None。
    """
    receipt = await confirmation_receipt_repo.find_receipt(novel_id, fingerprint.key_hash, session=session)
    if receipt is None:
        return None
    if receipt["request_hash"] != fingerprint.request_hash:
        raise IdempotencyConflictError("同一确认键已用于不同内容，请保留原请求")
    request = receipt.get("request")
    if (not isinstance(request, Mapping)
            or receipt.get("operation") != expected_operation
            or request.get("operation") != expected_operation):
        raise DomainApiError("CHAPTER_RECORD_RECEIPT_INVALID", "原确认回执的命令类型不一致，请保留原请求并检查回执", status_code=409)
    marked = "schema_id" in receipt or "schema_version" in receipt
    if expected_receipt_schema is not None or marked:
        from backend.services.novel.item_fact_contract import validate_item_fact_receipt
        from backend.services.novel.faction_fact_contract import validate_faction_fact_receipt

        validators = {
            "character.fact.receipt": validate_character_fact_receipt,
            "character_relation.fact.receipt": validate_character_relation_fact_receipt,
            "item.fact.receipt": validate_item_fact_receipt,
            "faction.fact.receipt": validate_faction_fact_receipt,
        }
        if (expected_receipt_schema not in validators
                or receipt.get("schema_id") != expected_receipt_schema
                or type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1):
            raise DomainApiError("CHAPTER_RECORD_RECEIPT_INVALID", "原确认回执的格式不受支持，请保留原请求并检查回执", status_code=409)
        try:
            return validators[expected_receipt_schema](receipt)
        except ValueError as exc:
            raise DomainApiError("CHAPTER_RECORD_RECEIPT_INVALID", "原事实回执的内容不一致，请保留原请求并检查回执", status_code=409) from exc
    legacy_results = {
        "confirm_event": ChapterEventReadV1,
        "confirm_report": ChapterReportReadV1,
        "confirm_psychological_state": ChapterPsychologicalStateResultV1,
        "confirm_item_owner": ChapterItemOwnerResultV1,
        "confirm_character_relation_state": ChapterCharacterRelationStateResultV1,
        "void_event": ChapterEventReadV1,
        "void_report": ChapterReportReadV1,
    }
    result_model = legacy_results.get(expected_operation)
    if result_model is None:
        raise DomainApiError("CHAPTER_RECORD_RECEIPT_INVALID", "原确认回执的命令类型不受支持，请保留原请求并检查回执", status_code=409)
    try:
        result_model.model_validate(receipt.get("result"))
    except ValidationError as exc:
        raise DomainApiError("CHAPTER_RECORD_RECEIPT_INVALID", "原确认回执的结果格式不正确，请保留原请求并检查回执", status_code=409) from exc
    # 只检查已存合同；不按当前实体、来源或作废状态重算原成功响应。
    return deepcopy(receipt["result"])


async def _save_receipt(request, fingerprint, source, result, *, session):
    """三种确认和作废共用同一回执形状，保留原请求、原结果及完整来源。

    Args:
        request: 含操作、小说范围和完整输入的原请求。
        fingerprint: 请求键和内容摘要。
        source: 本事务已经核验的 BSON 来源字段。
        result: 原成功公开响应。
        session: 当前确认事务。
    Returns:
        无；回执与实际记录一起提交。
    """
    await confirmation_receipt_repo.create_receipt({
        "novel_id": source["novel_id"], "operation": request["operation"],
        "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash,
        "request": request, "result": result,
        **{field: source[field] for field in ("chapter_id", "source_parents", "evidence")},
    }, session=session)


async def _read_record(document, kind, *, session=None):
    """历史读取只比较当前正文，软删除不会让不可变记录失去读取入口。

    Args:
        document: 原始 BSON 记录。
        kind: 事件、报告或状态历史。
        session: 作废命令中的读取使用同一事务。
    Returns:
        带动态复核标记的公开记录。
    """
    chapter = await BaseRepository("chapters").collection.find_one({
        "_id": document["chapter_id"], "novel_id": document["novel_id"],
    }, session=session)
    if chapter is None:
        raise DomainApiError("CHAPTER_RECORD_SOURCE_MISSING", "记录的来源章节缺失，请检查数据完整性", status_code=409)
    needs_review = hashlib.sha256(chapter["content"].encode("utf-8")).hexdigest() != document["evidence"]["content_hash"]
    return serialize_chapter_record({**document, "needs_review": needs_review}, kind)


class ChapterRecordService:
    """只有明确的作者确认命令能够写入章后记录。"""

    @staticmethod
    async def get_source_revision(novel_id: str, chapter_id: str, version: int) -> dict:
        """读取同书原修订和真实回收位置，允许来源的任一级已回收。

        Args:
            novel_id: 记录所属小说。
            chapter_id: 来源章节。
            version: 作者选定的修订版本。
        Returns:
            原样修订，以及从小说到章节依次列出的回收位置。
        """
        revision_version = validate_expected_version(version)

        async def read(session):
            novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True, session=session)
            chapter = await BaseRepository("chapters").collection.find_one({
                "_id": to_object_id(chapter_id), "novel_id": novel["_id"],
            }, session=session)
            if chapter is None:
                raise NotFoundError("来源章节不存在于当前小说")
            deleted_sources = ["novel"] if novel["is_deleted"] else []
            # 每一级都用章中保存的完整归属核对；回收不会解除同书和父级检查。
            parents = {"novel_id": novel["_id"]}
            for kind, label in (("volume", "卷"), ("arc", "篇章"), ("scene", "场景")):
                identity = chapter[f"{kind}_id"]
                parent = await BaseRepository(f"{kind}s").collection.find_one({
                    "_id": identity, **parents,
                }, session=session)
                if parent is None:
                    raise NotFoundError(f"来源{label}不存在或不属于当前章节的父级")
                if parent["is_deleted"]:
                    deleted_sources.append(kind)
                parents[f"{kind}_id"] = identity
            if chapter["is_deleted"]:
                deleted_sources.append("chapter")
            revision = await BaseRepository("chapter_revisions").collection.find_one({
                "chapter_id": chapter["_id"], "version": revision_version, **parents,
            }, session=session)
            if revision is None:
                raise NotFoundError("来源修订不存在或不属于当前章节")
            if hashlib.sha256(revision["content"].encode("utf-8")).hexdigest() != revision["content_hash"]:
                raise DomainApiError("CHAPTER_RECORD_REVISION_INVALID", "所选修订的正文校验失败", status_code=409)
            return {"revision": serialize_chapter_revision(revision), "deleted_sources": deleted_sources}

        return await run_mongo_write_unit(read, "get_chapter_record_source_revision", require_transaction=True)

    @staticmethod
    async def confirm(novel_id: str, kind: Literal["event", "report"], data: Mapping | ChapterEventConfirmV1 | ChapterReportConfirmV1, *, idempotency_key: str) -> dict:
        """确认事件或追加报告，报告版本与章节 head 在同一事务推进。

        Args:
            novel_id: 小说范围。
            kind: 路由明确选择事件或报告。
            data: 作者确认的内容、来源和已读报告版本。
            idempotency_key: 整次确认固定使用的请求键。
        Returns:
            新确认结果，或同键请求原成功快照。
        """
        model = {"event": ChapterEventConfirmV1, "report": ChapterReportConfirmV1}[kind]
        fields = model.model_validate(data).model_dump()
        novel_id = str(to_object_id(novel_id))
        for name in ("chapter_id", "revision_id"):
            fields["evidence"][name] = fields["evidence"][name].lower()
        for reference in fields["related_entities"]:
            if reference["entity_type"].endswith("_volume_state"):
                reference["entity_id"] = reference["entity_id"].lower()
        request = {"operation": f"confirm_{kind}", "novel_id": novel_id, "target_id": None, "data": fields}
        fingerprint = build_idempotency_fingerprint(idempotency_key, request)

        async def save(session):
            replay = await _replay(novel_id, fingerprint, expected_operation=request["operation"], session=session)
            if replay is not None:
                return replay
            source = await load_chapter_record_source_in_session(novel_id, fields["evidence"], session=session)
            chapter = source["guards"]["chapters", fields["evidence"]["chapter_id"]]
            for reference in fields["related_entities"]:
                collection, identity_field = RELATED_ENTITIES[reference["entity_type"]]
                identity = to_object_id(reference["entity_id"]) if identity_field == "_id" else reference["entity_id"]
                entity = await BaseRepository(collection).collection.find_one({
                    "novel_id": chapter["novel_id"], identity_field: identity, "is_deleted": False,
                }, session=session)
                if entity is None:
                    raise DomainApiError("CHAPTER_RECORD_ENTITY_NOT_FOUND", "相关实体不存在于本书或已回收", status_code=404)
                source["guards"][collection, str(entity["_id"])] = entity
            head = chapter.get("chapter_report_head", {"report_version": 0, "report_id": None})
            if kind == "report" and head["report_version"] != fields["expected_report_version"]:
                raise VersionConflictError("章末报告已有新版本，请保留稿件并读取最新报告")
            await protect_chapter_record_sources(source["guards"], session=session)
            now = get_utc_now()
            now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
            document = {
                "_id": ObjectId(), "novel_id": chapter["novel_id"], "chapter_id": chapter["_id"],
                "source_parents": {name: chapter[name] for name in ("volume_id", "arc_id", "scene_id")},
                **{name: value for name, value in fields.items() if name != "expected_report_version"},
                "evidence": source["evidence"], "confirmed_at": now, "voided_at": None, "void_reason": None,
            }
            if kind == "report":
                document.update(report_version=head["report_version"] + 1, previous_report_id=head["report_id"])
                head_filter = head if "chapter_report_head" in chapter else {"$exists": False}
                changed = await BaseRepository("chapters").collection.update_one({
                    "_id": chapter["_id"], "novel_id": chapter["novel_id"],
                    "version": chapter["version"], "is_deleted": False, "chapter_report_head": head_filter,
                }, {"$set": {"chapter_report_head": {"report_version": document["report_version"], "report_id": document["_id"]}}}, session=session)
                if changed.matched_count != 1:
                    raise VersionConflictError("章末报告在保存期间已变化，请读取最新报告")
            await BaseRepository(RECORD_KINDS[kind]).collection.insert_one(document, session=session)
            result = serialize_chapter_record({**document, "needs_review": source["needs_review"]}, kind)
            await _save_receipt(request, fingerprint, document, result, session=session)
            return result

        return await run_mongo_write_unit(save, f"confirm_chapter_{kind}", require_transaction=True)

    @staticmethod
    async def confirm_psychological_state(novel_id: str, data: Mapping | ChapterPsychologicalStateConfirmV1, *, idempotency_key: str) -> dict:
        """通过原实体服务修改人物心理状态，并同事务记录实际差异。

        Args:
            novel_id: 小说范围。
            data: 已有卷状态 ID、作者原版本、心理状态及章节证据。
            idempotency_key: 本次确认固定的请求键。
        Returns:
            原成功响应；没有实际变化时 history 为 null。
        """
        fields = ChapterPsychologicalStateConfirmV1.model_validate(data).model_dump()
        novel_id = str(to_object_id(novel_id))
        fields["state_id"] = fields["state_id"].lower()
        for name in ("chapter_id", "revision_id"):
            fields["evidence"][name] = fields["evidence"][name].lower()
        request = {"operation": "confirm_psychological_state", "novel_id": novel_id, "target_id": None, "data": fields}
        fingerprint = build_idempotency_fingerprint(idempotency_key, request)

        async def save(session):
            replay = await _replay(novel_id, fingerprint, expected_operation=request["operation"], session=session)
            if replay is not None:
                return replay
            source = await load_chapter_record_source_in_session(novel_id, fields["evidence"], session=session)
            if source["needs_review"]:
                raise DomainApiError("CHAPTER_RECORD_SOURCE_OUTDATED", "来源正文已经变化，请选择当前正文的修订再确认状态", status_code=409)
            chapter = source["guards"]["chapters", fields["evidence"]["chapter_id"]]
            before = await BaseRepository("character_volume_states").collection.find_one({
                "_id": to_object_id(fields["state_id"]), "novel_id": chapter["novel_id"],
                "volume_id": chapter["volume_id"], "is_deleted": False,
            }, session=session)
            if before is None:
                raise NotFoundError("人物卷状态不存在、已回收或不属于来源章节所在卷")
            # 来源先参加写冲突保护；原实体服务随后才取得小说锁和复核作者版本。
            await protect_chapter_record_sources(source["guards"], session=session)
            after = await CharacterVolumeStateService.update_state(novel_id, fields["state_id"], {
                "expected_version": fields["expected_version"], "psychological_state": fields["psychological_state"],
            }, session=session)
            now = get_utc_now()
            now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
            source_fields = {
                "novel_id": chapter["novel_id"], "chapter_id": chapter["_id"],
                "source_parents": {name: chapter[name] for name in ("volume_id", "arc_id", "scene_id")},
                "evidence": source["evidence"],
            }
            history = None
            if before["psychological_state"] != after["psychological_state"]:
                document = {
                    "_id": ObjectId(), **source_fields, "entity_type": "character_volume_state",
                    "entity_id": before["_id"], "character_id": before["character_id"], "volume_id": before["volume_id"],
                    "before_version": before["version"], "after_version": after["version"],
                    "before": {"psychological_state": before["psychological_state"]},
                    "after": {"psychological_state": after["psychological_state"]}, "confirmed_at": now,
                }
                await BaseRepository("entity_state_history").collection.insert_one(document, session=session)
                history = serialize_chapter_record({**document, "needs_review": False}, "history")
            result = ChapterPsychologicalStateResultV1.model_validate({
                "novel_id": novel_id, "state_id": fields["state_id"], "state_version": after["version"],
                "psychological_state": after["psychological_state"], "evidence": source["evidence"],
                "confirmed_at": now, "needs_review": False, "history": history,
            }).model_dump()
            await _save_receipt(request, fingerprint, source_fields, result, session=session)
            return result

        return await run_mongo_write_unit(save, "confirm_chapter_psychological_state", require_transaction=True)

    @staticmethod
    async def confirm_item_owner(novel_id: str, data: Mapping | ChapterItemOwnerConfirmV1, *, idempotency_key: str) -> dict:
        """确认固定持有人变化，并在同一事务保存真实差异和成功回执。

        Args:
            novel_id: 当前小说。
            data: 检查时固定的物品、方向、版本、依据及原文证据。
            idempotency_key: 本次确认固定使用的请求键。
        Returns:
            实际更新结果和变化历史，或同键原成功响应。
        """
        command = ChapterItemOwnerConfirmV1.model_validate(data)
        fields = command.model_dump()
        novel_id = str(to_object_id(novel_id))
        for name in ("chapter_id", "revision_id"):
            fields["evidence"][name] = fields["evidence"][name].lower()
        request = {"operation": "confirm_item_owner", "novel_id": novel_id, "target_id": None, "data": fields}
        fingerprint = build_idempotency_fingerprint(idempotency_key, request)

        async def save(session):
            replay = await _replay(novel_id, fingerprint, expected_operation=request["operation"], session=session)
            if replay is not None:
                return replay
            from backend.services.novel.item_fact_service import ensure_item_fields_unmanaged
            await ensure_item_fields_unmanaged(novel_id, [fields["item_id"]], session=session)
            source = await load_chapter_record_source_in_session(novel_id, fields["evidence"], session=session)
            if source["needs_review"]:
                raise DomainApiError("CHAPTER_RECORD_SOURCE_OUTDATED", "来源正文已经变化，请选择当前正文的修订再确认持有人", status_code=409)
            chapter = source["guards"]["chapters", fields["evidence"]["chapter_id"]]
            fixed = ChapterItemOwnerCheckInputV1.model_validate({
                "novel_id": novel_id,
                "source": {key: source["evidence"][key] for key in ("chapter_id", "revision_id", "version", "content_hash")},
                **{key: fields[key] for key in ("item_id", "expected_version", "from_character_id", "to_character_id")},
            })
            # 不按客户端 refs 决定读取范围，三份真实资料每次都独立重读。
            sources = await load_chapter_item_owner_sources_in_session(fixed, session=session)
            refs = sources["source_refs"]
            basis = command.basis
            snapshot = basis.flow_snapshot
            fixed_input = fixed.model_dump(mode="json")
            ref_values = [ref.model_dump(mode="json") for ref in refs]
            from backend.services.task_flows.registry import TASKS
            spec = TASKS[CHAPTER_ITEM_OWNER_CHECK_TASK]
            if (basis.novel_id != novel_id or basis.workflow != CHAPTER_ITEM_OWNER_CHECK_TASK
                    or (basis.step, basis.schema_id, basis.schema_version) != (spec.step, spec.schema_id, spec.schema_version)
                    or snapshot["scope"] != fixed_input or snapshot["business_input"] != fixed_input
                    or basis.source_refs != refs):
                raise DomainApiError("CANDIDATE_BASIS_CONFLICT", "物品、持有人方向或来源版本已变化，请重新检查", status_code=409)
            reads = snapshot["execution"].get("source_refs_by_node")
            if not isinstance(reads, dict) or reads.get("preflight") != ref_values or any(value != ref_values for value in reads.values()):
                raise DomainApiError("CANDIDATE_BASIS_CONFLICT", "检查依据缺少完整的物品和持有人版本，请重新检查", status_code=409)
            try:
                current_fingerprint = compute_flow_candidate_fingerprint(CHAPTER_ITEM_OWNER_CHECK_TASK, fixed, refs, snapshot)
            except (KeyError, ValueError) as exc:
                raise DomainApiError("CANDIDATE_BASIS_CONFLICT", "原检查流程或输入已不匹配，请重新检查", status_code=409) from exc
            if current_fingerprint != basis.input_fingerprint:
                raise DomainApiError("CANDIDATE_FINGERPRINT_CONFLICT", "检查依据已变化，请重新检查", status_code=409)

            await protect_chapter_record_sources(source["guards"], session=session)
            before = sources["item"]
            # 必须先保护端点，再让原物品服务重读；否则服务的旧快照会和 guard 冲突。
            await touch_dependency_endpoint_guards(BaseRepository("items").collection, [{
                "_id": before["_id"], "novel_id": before["novel_id"], "version": before["version"],
                "is_deleted": False, "item_write_pending_token": None,
                "lifecycle_status": "held", "owner_character_id": fixed.from_character_id,
            }], session=session)
            await touch_dependency_endpoint_guards(BaseRepository("characters").collection, [{
                "_id": row["_id"], "novel_id": row["novel_id"], "version": row["version"],
                "is_deleted": False, "status": "active",
            } for row in (sources["from_character"], sources["to_character"])], session=session)
            after = await ItemService.update_item(novel_id, fields["item_id"], {
                "expected_version": fields["expected_version"], "owner_character_id": fields["to_character_id"],
            }, session=session)
            now = get_utc_now()
            now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
            source_fields = {
                "novel_id": chapter["novel_id"], "chapter_id": chapter["_id"],
                "source_parents": {name: chapter[name] for name in ("volume_id", "arc_id", "scene_id")},
                "evidence": source["evidence"],
            }
            document = {
                "_id": ObjectId(), **source_fields, "entity_type": "item", "entity_id": before["_id"],
                "item_id": before["item_id"], "before_version": before["version"], "after_version": after["version"],
                "before": {"owner_character_id": before["owner_character_id"]},
                "after": {"owner_character_id": after["owner_character_id"]}, "confirmed_at": now,
            }
            await BaseRepository("entity_state_history").collection.insert_one(document, session=session)
            history = serialize_chapter_record({**document, "needs_review": False}, "history")
            result = ChapterItemOwnerResultV1.model_validate({
                "novel_id": novel_id, "item_id": before["item_id"], "item_version": after["version"],
                "owner_character_id": after["owner_character_id"], "evidence": source["evidence"],
                "confirmed_at": now, "needs_review": False, "history": history,
            }).model_dump()
            await _save_receipt(request, fingerprint, source_fields, result, session=session)
            return result

        return await run_mongo_write_unit(save, "confirm_chapter_item_owner", require_transaction=True)

    @staticmethod
    async def confirm_character_relation_state(
        novel_id: str, data: Mapping | ChapterCharacterRelationStateConfirmV1, *, idempotency_key: str,
    ) -> dict:
        """只回放旧关系状态确认的原成功结果，不再通过旧入口写入状态。

        Args:
            novel_id: 当前小说。
            data: 固定关系版本、作者编辑的状态、原文证据和完整检查依据。
            idempotency_key: 冻结请求后始终沿用的确认键。
        Returns:
            原成功结果，包括合法的 history=null；没有回执时明确拒绝。
        """
        command = ChapterCharacterRelationStateConfirmV1.model_validate(data)
        fields = command.model_dump()
        novel_id = str(to_object_id(novel_id))
        for name in ("chapter_id", "revision_id"):
            fields["evidence"][name] = fields["evidence"][name].lower()
        request = {"operation": "confirm_character_relation_state", "novel_id": novel_id, "target_id": None, "data": fields}
        fingerprint = build_idempotency_fingerprint(idempotency_key, request)

        async def save(session):
            replay = await _replay(novel_id, fingerprint, expected_operation=request["operation"], session=session)
            if replay is not None:
                return replay
            raise DomainApiError(
                "CHARACTER_RELATION_FACT_REQUIRED",
                "没有找到旧关系确认的成功回执，请保留原请求；新状态请从关系事实中确认",
                status_code=409,
            )

        return await run_mongo_write_unit(save, "confirm_chapter_character_relation_state", require_transaction=True)

    @staticmethod
    async def void(novel_id: str, kind: Literal["event", "report"], identity: str, data: Mapping | ChapterRecordVoidV1, *, idempotency_key: str) -> dict:
        """单向作废原记录；原内容、报告头和已执行的实体更新保持原样。

        Args:
            novel_id: 小说范围，允许已软删除的小说。
            kind: 事件或报告。
            identity: 原记录物理 ID。
            data: 作者填写的作废原因。
            idempotency_key: 作废请求的固定键。
        Returns:
            作废成功时的原响应，重放不会改动当前状态。
        """
        fields = ChapterRecordVoidV1.model_validate(data).model_dump()
        novel_id, identity = str(to_object_id(novel_id)), str(to_object_id(identity))
        request = {"operation": f"void_{kind}", "novel_id": novel_id, "target_id": identity, "data": fields}
        fingerprint = build_idempotency_fingerprint(idempotency_key, request)

        async def save(session):
            replay = await _replay(novel_id, fingerprint, expected_operation=request["operation"], session=session)
            if replay is not None:
                return replay
            novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True, session=session)
            collection = BaseRepository(RECORD_KINDS[kind]).collection
            current = await collection.find_one({"_id": to_object_id(identity), "novel_id": novel["_id"]}, session=session)
            if current is None:
                raise NotFoundError("章后记录不存在于当前小说")
            if current["voided_at"] is not None:
                raise VersionConflictError("记录已经作废，请读取当前记录")
            await protect_chapter_record_sources({("novels", novel_id): novel}, session=session)
            now = get_utc_now()
            now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
            changed = await collection.update_one({"_id": current["_id"], "novel_id": novel["_id"], "voided_at": None}, {
                "$set": {"voided_at": now, "void_reason": fields["reason"]},
            }, session=session)
            if changed.matched_count != 1:
                raise VersionConflictError("记录在作废期间已变化，请读取当前记录")
            document = {**current, "voided_at": now, "void_reason": fields["reason"]}
            result = await _read_record(document, kind, session=session)
            await _save_receipt(request, fingerprint, document, result, session=session)
            return result

        return await run_mongo_write_unit(save, f"void_chapter_{kind}", require_transaction=True)

    @staticmethod
    async def get(novel_id: str, kind: Literal["event", "report", "history"], identity: str) -> dict:
        """读取同书历史，小说和来源软删除后仍可查询。

        Args:
            novel_id: 小说范围。
            kind: 明确的记录类别。
            identity: 记录物理 ID。
        Returns:
            原记录和按当前正文派生的复核标记。
        """
        novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True)
        query = {"_id": to_object_id(identity), "novel_id": novel["_id"]}
        if kind == "history":
            # 旧历史没有 schema 标记；新版和不完整标记不能落入旧章证据读取。
            query.update(schema_id={"$exists": False}, schema_version={"$exists": False})
        document = await BaseRepository(RECORD_KINDS[kind]).collection.find_one(query)
        if document is None:
            raise NotFoundError("章后记录不存在于当前小说")
        return await _read_record(document, kind)

    @staticmethod
    async def list(novel_id: str, kind: Literal["event", "report", "history"], *, chapter_id: str | None = None, revision_id: str | None = None, entity_id: str | None = None, entity_type: Literal["character_volume_state", "item", "character_relation"] | None = None) -> list[dict]:
        """列出同书记录，包括报告旧版和作废记录。

        Args:
            novel_id: 小说范围，允许软删除小说。
            kind: 明确的记录类别。
            chapter_id: 可选来源章。
            revision_id: 可选不可变来源修订。
            entity_id: 状态历史的可选实体物理 ID。
            entity_type: 过滤人物卷状态、物品或人物关系历史。
        Returns:
            最新在前的原记录和动态复核标记。
        """
        novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True)
        query = {"novel_id": novel["_id"]}
        if kind == "history":
            query.update(schema_id={"$exists": False}, schema_version={"$exists": False})
        if chapter_id is not None:
            query["chapter_id"] = to_object_id(chapter_id)
        if revision_id is not None:
            query["evidence.revision_id"] = str(to_object_id(revision_id))
        if entity_id is not None:
            query["entity_id"] = to_object_id(entity_id)
            # 保留旧服务调用只传卷状态 ID 时的含义。
            query["entity_type"] = entity_type or "character_volume_state"
        elif entity_type is not None:
            query["entity_type"] = entity_type
        rows = await BaseRepository(RECORD_KINDS[kind]).collection.find(query).sort([("confirmed_at", -1), ("_id", -1)]).to_list(None)
        return [await _read_record(row, kind) for row in rows]

    @staticmethod
    async def report_head(novel_id: str, chapter_id: str) -> dict:
        """读取报告 head 和当前有效报告，作废不会复活上一版。

        Args:
            novel_id: 小说范围。
            chapter_id: 当前章节，允许软删除。
        Returns:
            仍占用的报告版本、ID，以及当前有效报告或 null。
        """
        novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True)
        chapter = await BaseRepository("chapters").collection.find_one({"_id": to_object_id(chapter_id), "novel_id": novel["_id"]})
        if chapter is None:
            raise NotFoundError("章节不存在于当前小说")
        head = chapter.get("chapter_report_head", {"report_version": 0, "report_id": None})
        report = None
        if head["report_id"] is not None:
            document = await BaseRepository("chapter_reports").collection.find_one({
                "_id": head["report_id"], "novel_id": novel["_id"], "chapter_id": chapter["_id"], "report_version": head["report_version"],
            })
            if document is None:
                raise DomainApiError("CHAPTER_REPORT_HEAD_INVALID", "章末报告版本链缺失，请检查数据完整性", status_code=409)
            if document["voided_at"] is None:
                report = await _read_record(document, "report")
        return {"chapter_id": str(chapter["_id"]), "report_version": head["report_version"],
                "report_id": str(head["report_id"]) if head["report_id"] is not None else None, "report": report}
