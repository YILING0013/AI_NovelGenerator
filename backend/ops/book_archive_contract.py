"""只用包内原始文档检查作品 ID、关联和已知唯一键。"""

from __future__ import annotations

import re
import hashlib
from datetime import datetime
from typing import Any

from bson import ObjectId


CORE_COLLECTIONS = (
    "novels", "volumes", "arcs", "scenes", "chapters", "characters", "factions",
    "character_relations", "faction_relations", "character_faction_bindings",
    "world_rules", "locations", "items", "character_volume_states", "faction_volume_states",
)
RECEIPT_COLLECTIONS = (
    "volume_command_receipts", "character_volume_state_initialization_receipts",
    "faction_volume_state_initialization_receipts", "world_rule_core_confirmation_receipts",
    "location_generation_confirmation_receipts", "item_generation_confirmation_receipts",
    "writing_confirmation_receipts",
)
COLLECTIONS = (*CORE_COLLECTIONS, "id_sequences", *RECEIPT_COLLECTIONS)
REVISION_COLLECTIONS = (*COLLECTIONS, "chapter_revisions")
FORESHADOWING_COLLECTIONS = (*REVISION_COLLECTIONS, "foreshadowings", "foreshadowing_creation_receipts")
CHAPTER_RECORD_COLLECTIONS = (*FORESHADOWING_COLLECTIONS, "events", "chapter_reports", "entity_state_history", "chapter_record_confirmation_receipts")
CHARACTER_BATCH_COLLECTIONS = (*CHAPTER_RECORD_COLLECTIONS, "character_creation_batch_receipts")
FACTION_BATCH_COLLECTIONS = (*CHARACTER_BATCH_COLLECTIONS, "faction_creation_batch_receipts")
# Dev 的势力归档占用 11；本分支的整批创建使用独立合同 12。
FACTION_FACT_FORMAT_VERSION = 11
CHARACTER_BATCH_FORMAT_VERSION = 12
COMBINED_FORMAT_VERSION = 13
FACTION_VOLUME_START_FORMAT_VERSION = 14
SUPPORTED_FORMAT_VERSIONS = tuple(range(1, 15))
# v11/v12 是两条独立历史格式，不按版本大小互相放行扩展。
FACTION_FACT_FORMAT_VERSIONS = (FACTION_FACT_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION)
CHARACTER_BATCH_FORMAT_VERSIONS = (CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION)

# 与当前分配器和公开 ID 格式一致；序列保留删除过的 ID 和分配失败留下的空号。
BUSINESS_IDS = {
    "characters": ("character_id", "character", "char"),
    "factions": ("faction_id", "faction", "fac"),
    "character_relations": ("relation_id", "character_relation", "cr"),
    "faction_relations": ("relation_id", "faction_relation", "fr"),
    "character_faction_bindings": ("binding_id", "character_faction_binding", "cfb"),
    "world_rules": ("rule_id", "world_rule", "rule"),
    "locations": ("location_id", "location", "loc"),
    "items": ("item_id", "item", "item"),
    "foreshadowings": ("foreshadowing_id", "foreshadowing", "fo"),
}


class ArchiveValidationError(ValueError):
    """带有包内文件和行号的验证失败。"""

    def __init__(self, location: str, message: str) -> None:
        """保存能够直接找到问题记录的位置。

        Args:
            location: 包内路径，可附 JSONL 行号和字段。
            message: 失败原因。
        """
        self.location = location
        self.message = message
        super().__init__(f"{location}: {message}")


def _business_number(value: Any, prefix: str, location: str) -> int:
    """检查现存记录和历史快照共用的业务 ID 格式并取出序号。

    Args:
        value: 原样保存的业务 ID。
        prefix: 当前实体类型的固定前缀。
        location: ID 所在的包内位置。

    Returns:
        该 ID 已占用的整数序号。
    """
    if not isinstance(value, str) or re.fullmatch(rf"{prefix}_[0-9]{{6,19}}", value) is None:
        raise ArchiveValidationError(location, "稳定业务 ID 格式错误或超过当前整数序列范围")
    return int(value.split("_")[-1])


def _reference(value: Any, targets: dict, location: str, summary: dict, *, physical: bool = False, historical: bool = False, business_prefix: str | None = None) -> dict | None:
    """核对多个集合共用的直接引用，历史缺失单独计数。

    Args:
        value: 原始引用 ID。
        targets: 同书目标 ID 到原文档的映射。
        location: 当前字段在包内的位置。
        summary: 累加验证数量的结果。
        physical: 是否要求 BSON ObjectId。
        historical: 是否允许已永久删除的历史目标。
        business_prefix: 历史引用缺失时仍须满足的业务 ID 前缀。

    Returns:
        找到的目标文档，或允许缺失的历史目标。
    """
    if not isinstance(value, ObjectId if physical else str) or (not physical and not value):
        raise ArchiveValidationError(location, "引用 ID 类型错误")
    if business_prefix is not None:
        _business_number(value, business_prefix, location)
    target = targets.get(value)
    if target is None:
        if historical:
            summary["historical_references_unresolved"] += 1
            return None
        raise ArchiveValidationError(location, "引用的同书记录不存在")
    summary["references"] += 1
    return target


def _snapshot_rows(rows: Any, location: str, novel_id: ObjectId, identity_field: str) -> list:
    """检查成功回执自己的快照归属和 ID，不要求历史对象仍存在。

    Args:
        rows: 原样保存的成功响应数组。
        location: 数组在回执中的位置。
        novel_id: 当前包的作品 ID。
        identity_field: 该响应实际保存的 ID 字段。

    Returns:
        按原顺序排列的快照 ID。
    """
    if not isinstance(rows, list):
        raise ArchiveValidationError(location, "回执快照必须是数组")
    identities = []
    seen = set()
    for index, row in enumerate(rows):
        row_location = f"{location}[{index}]"
        if not isinstance(row, dict) or row.get("novel_id") not in (novel_id, str(novel_id)):
            raise ArchiveValidationError(row_location, "回执快照缺少同书 novel_id")
        identity = row.get(identity_field)
        if not isinstance(identity, (str, ObjectId)) or not str(identity):
            raise ArchiveValidationError(f"{row_location}.{identity_field}", "回执快照缺少有效 ID")
        if identity_field in ("_id", "state_id", "volume_id", "arc_id", "scene_id", "chapter_id"):
            if not ObjectId.is_valid(identity):
                raise ArchiveValidationError(f"{row_location}.{identity_field}", "回执快照物理 ID 格式错误")
        else:
            for field, _, prefix in BUSINESS_IDS.values():
                if field == identity_field:
                    _business_number(identity, prefix, f"{row_location}.{identity_field}")
        if str(identity) in seen:
            raise ArchiveValidationError(f"{row_location}.{identity_field}", "回执快照 ID 重复")
        identities.append(identity)
        seen.add(str(identity))
    return identities


def _validate_faction_plan(document: dict, location: str, *, format_version: int) -> None:
    """v14 新计划不含动态事实，原创建结果和摘要必须可独立复验。"""
    from pydantic import ValidationError
    from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumePlanFieldsV1, FactionVolumePlanReadV1
    from backend.db.write_contracts import canonical_request_hash

    if format_version < 14:
        raise ArchiveValidationError(location, "势力独立卷参与计划仅由 v14 承载，不能升级旧包")
    dynamic = {"power_level", "resources", "public_stance", "influence_scope", "active_status"}
    original = document.get("plan_creation_result")
    if not isinstance(original, dict) or "plan_creation_result" in original:
        raise ArchiveValidationError(location, "参与计划缺少独立的首次创建结果")
    for row in (document, original):
        if dynamic & row.keys() or row.get("content_contract") != "participation_plan_v1":
            raise ArchiveValidationError(location, "参与计划不能保存实际状态或默认等级")
        for field in ("creation_idempotency_key_hash", "creation_request_hash"):
            if not isinstance(row.get(field), str) or re.fullmatch(r"[0-9a-f]{64}", row[field]) is None:
                raise ArchiveValidationError(location, "参与计划及首次结果必须保留合法的原键与请求摘要")
        public = {field: value for field, value in row.items() if field in FactionVolumePlanReadV1.model_fields}
        for field in ("state_id", "novel_id", "volume_id", "source_state_id"):
            if public.get(field) is not None:
                public[field] = str(public[field])
        try:
            FactionVolumePlanReadV1.model_validate(public)
        except ValidationError as exc:
            raise ArchiveValidationError(location, "参与计划的公开内容或生命周期无效") from exc
    immutable = ("_id", "state_id", "novel_id", "volume_id", "faction_id", "source_state_id", "created_at", "creation_idempotency_key_hash", "creation_request_hash")
    if (any(original.get(field) != document.get(field) for field in immutable)
            or original["version"] != 1 or original["is_deleted"] or original["created_at"] != original["updated_at"]):
        raise ArchiveValidationError(location, "参与计划的首次结果身份、初始版本或审计不一致")
    content = {field: original[field] for field in FactionVolumePlanFieldsV1.model_fields}
    expected_hash = canonical_request_hash({"operation": "create_participation_plan", "novel_id": str(original["novel_id"]),
        "volume_id": str(original["volume_id"]), "faction_id": original["faction_id"], "content": content,
        **({"source_state_id": str(original["source_state_id"])} if original["source_state_id"] is not None else {})})
    if original.get("creation_request_hash") != expected_hash or document["version"] == 1 and any(document[field] != original[field] for field in content):
        raise ArchiveValidationError(location, "参与计划的首次内容、摘要或未更新原文不一致")


def _validate_foreshadowing(document: dict, novel_id: ObjectId, location: str, by_id: dict, summary: dict, *, historical: bool = False) -> None:
    """检查伏笔原字段和不可变原文，成功创建快照允许来源后来被删。"""
    from pydantic import ValidationError
    from backend.services.novel.foreshadowing_contract import ForeshadowingReadV1
    if not isinstance(document, dict) or not isinstance(document.get("_id"), ObjectId) or document.get("novel_id") != novel_id:
        raise ArchiveValidationError(location, "伏笔及创建快照需要同书 BSON 身份")
    payload = {name: document.get(name) for name in ForeshadowingReadV1.model_fields}
    payload.update(novel_id=str(novel_id), planted_needs_review=False, resolved_needs_review=False)
    try:
        ForeshadowingReadV1.model_validate(payload)
    except ValidationError as exc:
        raise ArchiveValidationError(location, "伏笔字段、状态或证据格式不正确") from exc
    if document["status"] in ("planted", "resolved") and document["planted_evidence"] is None or document["status"] == "resolved" and document["resolved_evidence"] is None:
        raise ArchiveValidationError(location, "已埋设或已回收状态缺少对应章节证据")
    for name in ("planting_position", "resolution_position"):
        position = document[name]
        if position is not None:
            if position["id"] != str(ObjectId(position["id"])):
                raise ArchiveValidationError(f"{location}.{name}", "计划位置必须保存小写稳定 ID")
            _reference(ObjectId(position["id"]), by_id[f"{position['kind']}s"], f"{location}.{name}", summary, physical=True, historical=historical)
    for name in ("planted_evidence", "resolved_evidence"):
        evidence = document[name]
        if evidence is None:
            continue
        for field in ("chapter_id", "revision_id"):
            if evidence[field] != str(ObjectId(evidence[field])):
                raise ArchiveValidationError(f"{location}.{name}.{field}", "章节证据必须保存小写稳定 ID")
        chapter = _reference(ObjectId(evidence["chapter_id"]), by_id["chapters"], f"{location}.{name}.chapter_id", summary, physical=True)
        revision = _reference(ObjectId(evidence["revision_id"]), by_id["chapter_revisions"], f"{location}.{name}.revision_id", summary, physical=True)
        if (revision["chapter_id"] != chapter["_id"] or revision["novel_id"] != novel_id
                or revision["version"] != evidence["version"] or revision["content_hash"] != evidence["content_hash"]
                or revision["content"][evidence["start"]:evidence["start"] + len(evidence["quote"])] != evidence["quote"]):
            raise ArchiveValidationError(f"{location}.{name}", "证据与所选同章修订、正文摘要或码点位置不一致")


def _validate_chapter_record_source(document: dict, location: str, by_id: dict, summary: dict) -> dict:
    """核对章后记录与回执共用的原文来源，不要求来源仍在活动列表。

    Args:
        document: 包含章节、来源父级和证据的原始记录或回执。
        location: 当前记录的包内位置。
        by_id: 已核对同书归属的物理 ID 映射。
        summary: 累加同书引用数量的验证摘要。
    Returns:
        证据对应的同书章节，包括软删除章节。
    """
    from pydantic import ValidationError
    from backend.services.novel.chapter_record_contract import ChapterRecordEvidenceV1

    evidence = document.get("evidence")
    try:
        ChapterRecordEvidenceV1.model_validate(evidence)
    except ValidationError as exc:
        raise ArchiveValidationError(f"{location}.evidence", "章节证据字段不正确") from exc
    for field in ("chapter_id", "revision_id"):
        if evidence[field] != str(ObjectId(evidence[field])):
            raise ArchiveValidationError(f"{location}.evidence.{field}", "章节证据必须保存小写稳定 ID")
    chapter = _reference(document.get("chapter_id"), by_id["chapters"], f"{location}.chapter_id", summary, physical=True)
    revision = _reference(ObjectId(evidence["revision_id"]), by_id["chapter_revisions"], f"{location}.evidence.revision_id", summary, physical=True)
    if (evidence["chapter_id"] != str(chapter["_id"]) or revision["chapter_id"] != chapter["_id"]
            or evidence["version"] != revision["version"] or evidence["content_hash"] != revision["content_hash"]
            or revision["content"][evidence["start"]:evidence["start"] + len(evidence["quote"])] != evidence["quote"]):
        raise ArchiveValidationError(f"{location}.evidence", "来源章、修订、正文摘要或原文码点位置不一致")
    parents = {field: chapter[field] for field in ("volume_id", "arc_id", "scene_id")}
    if document.get("source_parents") != parents:
        raise ArchiveValidationError(f"{location}.source_parents", "来源父级必须与同书章节一致")
    return chapter


def _validate_chapter_records(documents: dict, novel_id: ObjectId, by_id: dict, by_business: dict,
                             locations: dict, summary: dict, sequence_minimum: dict, required_sequences: set,
                             format_version: int) -> None:
    """核对不可变记录、报告 head、真实变化和确认回执，并保留历史业务号。

    Args:
        documents: 已完成基本身份和章节修订检查的原始集合。
        novel_id: 本书 BSON 身份。
        by_id: 同书物理 ID 映射。
        by_business: 同书业务 ID 映射。
        locations: 原始文档所在的包内位置。
        summary: 累加回执、引用和唯一键检查数量。
        sequence_minimum: 累加历史业务 ID 已占用的序列下限。
        required_sequences: 记录必须保留的业务序列类型。
        format_version: 清单声明的版本；物品转交从 v6、人物关系状态从 v7 开始支持。
    Returns:
        无；不一致时抛出带包内位置的错误。
    """
    import unicodedata
    from pydantic import ValidationError
    from backend.db.write_contracts import canonical_request_hash
    from backend.services.llm.candidate_contract import compute_candidate_input_fingerprint
    from backend.services.novel.chapter_record_contract import (
        ChapterEventConfirmV1, ChapterReportConfirmV1, ChapterRecordVoidV1,
        ChapterPsychologicalStateConfirmV1, ChapterPsychologicalStateResultV1,
        ChapterItemOwnerConfirmV1, ChapterItemOwnerResultV1,
        ChapterCharacterRelationStateConfirmV1, ChapterCharacterRelationStateResultV1,
        CharacterRelationStateHistoryReadV1,
        serialize_chapter_record,
    )

    report_chains: dict[ObjectId, list[dict]] = {}
    history_versions = set()
    relation_records = []
    relation_endpoint_business_ids, relation_endpoint_physical_ids = {}, {}
    confirmed = {name: set() for name in ("events", "chapter_reports", "entity_state_history")}
    voided = {"events": set(), "chapter_reports": set()}
    entity_collections = {entity: name for name, (_, entity, _) in BUSINESS_IDS.items() if name != "foreshadowings"}
    entity_collections.update(character_volume_state="character_volume_states", faction_volume_state="faction_volume_states")
    for name in confirmed:
        for row in documents[name]:
            location = locations[name, row["_id"]]
            if name == "entity_state_history" and row.get("entity_type") == "item" and format_version < 6:
                raise ArchiveValidationError(location, "物品转交历史必须使用 v6 归档")
            if name == "entity_state_history" and row.get("entity_type") == "character_relation":
                if format_version < 7:
                    raise ArchiveValidationError(location, "人物关系状态历史必须使用 v7 归档")
                # 公开序列化会过滤顶层字段，归档必须先拒绝原始 BSON 偷带卷状态等字段。
                expected_fields = (set(CharacterRelationStateHistoryReadV1.model_fields)
                                   - {"history_id", "needs_review"}) | {"_id", "chapter_id", "source_parents"}
                if set(row) != expected_fields:
                    raise ArchiveValidationError(location, "人物关系状态历史只能保存固定身份、原文与 current_state 变化")
            chapter = _validate_chapter_record_source(row, location, by_id, summary)
            kind = {"events": "event", "chapter_reports": "report", "entity_state_history": "history"}[name]
            try:
                public = serialize_chapter_record({**row, "needs_review": False}, kind)
                if name == "events":
                    ChapterEventConfirmV1.model_validate({field: row.get(field) for field in ("title", "content", "evidence", "related_entities")})
                elif name == "chapter_reports":
                    ChapterReportConfirmV1.model_validate({
                        "expected_report_version": row["report_version"] - 1,
                        **{field: row.get(field) for field in ("summary", "issues", "evidence", "related_entities")},
                    })
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                raise ArchiveValidationError(location, "章后记录字段或实际变化类型不正确") from exc
            if "needs_review" in row:
                raise ArchiveValidationError(location, "needs_review 必须读取时计算，不能保存在事实记录")
            if name != "entity_state_history":
                if (row["voided_at"] is None) != (row["void_reason"] is None):
                    raise ArchiveValidationError(location, "作废时间和原因必须同时保存")
                if row["voided_at"] is not None:
                    try:
                        ChapterRecordVoidV1.model_validate({"reason": row["void_reason"]})
                    except ValidationError as exc:
                        raise ArchiveValidationError(location, "作废原因无效") from exc
                for index, ref in enumerate(public["related_entities"]):
                    ref_location = f"{location}.related_entities[{index}]"
                    target_name = entity_collections[ref["entity_type"]]
                    if ref["entity_type"].endswith("_volume_state"):
                        if ref["entity_id"] != str(ObjectId(ref["entity_id"])):
                            raise ArchiveValidationError(ref_location, "状态引用必须保存小写稳定 ID")
                        _reference(ObjectId(ref["entity_id"]), by_id[target_name], ref_location, summary, physical=True, historical=True)
                    else:
                        _, entity, prefix = BUSINESS_IDS[target_name]
                        _reference(ref["entity_id"], by_business[target_name], ref_location, summary, historical=True, business_prefix=prefix)
                        sequence_minimum[entity] = max(sequence_minimum[entity], _business_number(ref["entity_id"], prefix, ref_location))
                        required_sequences.add(entity)
            if name == "chapter_reports":
                if row["previous_report_id"] is not None and not isinstance(row["previous_report_id"], ObjectId):
                    raise ArchiveValidationError(location, "上一版报告必须保存 BSON ID")
                report_chains.setdefault(row["chapter_id"], []).append(row)
            if name == "entity_state_history":
                if (not isinstance(row["entity_id"], ObjectId)
                        or row["after_version"] != row["before_version"] + 1 or row["before"] == row["after"]):
                    raise ArchiveValidationError(location, "实际变化必须改变允许字段并只增加一次实体版本")
                key = (row["entity_type"], row["entity_id"], row["after_version"])
                if key in history_versions:
                    raise ArchiveValidationError(location, "同一实体版本的变化历史重复")
                history_versions.add(key)
                summary["unique_keys"] += 1
                if row["entity_type"] == "character_relation":
                    relation_records.append((row, [(row[f"{side}_version"], row[side]["current_state"])
                                                   for side in ("before", "after")], location))
                    continue
                if row["entity_type"] == "item":
                    target = _reference(row["entity_id"], by_id["items"], f"{location}.entity_id", summary, physical=True, historical=True)
                    known_item = by_business["items"].get(row["item_id"])
                    if (target is not None and target["item_id"] != row["item_id"]
                            or known_item is not None and known_item["_id"] != row["entity_id"]):
                        raise ArchiveValidationError(location, "历史物品的 BSON ID 与稳定业务 ID 不一致")
                    if target is not None and target["version"] < row["after_version"]:
                        raise ArchiveValidationError(location, "现存物品版本不能低于已确认历史版本")
                    if (target is not None and target["version"] == row["after_version"]
                            and target["owner_character_id"] != row["after"]["owner_character_id"]):
                        raise ArchiveValidationError(location, "物品版本未再变化时，持有人必须与历史结果一致")
                    number = _business_number(row["item_id"], "item", f"{location}.item_id")
                    sequence_minimum["item"] = max(sequence_minimum["item"], number)
                    required_sequences.add("item")
                    for side in ("before", "after"):
                        owner = row[side]["owner_character_id"]
                        owner_location = f"{location}.{side}.owner_character_id"
                        _reference(owner, by_business["characters"], owner_location, summary, historical=True, business_prefix="char")
                        sequence_minimum["character"] = max(sequence_minimum["character"], _business_number(owner, "char", owner_location))
                        required_sequences.add("character")
                    continue
                if row["volume_id"] != chapter["volume_id"]:
                    raise ArchiveValidationError(location, "人物状态变化必须属于来源卷")
                target = _reference(row["entity_id"], by_id["character_volume_states"], f"{location}.entity_id", summary, physical=True, historical=True)
                if target is not None and (target["character_id"] != row["character_id"] or target["volume_id"] != row["volume_id"]):
                    raise ArchiveValidationError(location, "历史状态身份与现存状态不一致")
                if target is not None and target["version"] < row["after_version"]:
                    raise ArchiveValidationError(location, "现存状态版本不能低于已确认历史版本")
                number = _business_number(row["character_id"], "char", f"{location}.character_id")
                sequence_minimum["character"] = max(sequence_minimum["character"], number)
                required_sequences.add("character")

    for chapter in documents["chapters"]:
        location = locations["chapters", chapter["_id"]]
        chain = sorted(report_chains.get(chapter["_id"], []), key=lambda row: row["report_version"])
        previous_id = None
        for version, row in enumerate(chain, 1):
            if row["report_version"] != version or row["previous_report_id"] != previous_id:
                raise ArchiveValidationError(locations["chapter_reports", row["_id"]], "报告版本必须从一连续追加，并链接同章上一版")
            previous_id = row["_id"]
            summary["unique_keys"] += 1
        head = chapter.get("chapter_report_head")
        if chain:
            expected_head = {"report_version": len(chain), "report_id": previous_id}
            if (head != expected_head or not isinstance(head["report_version"], int)
                    or isinstance(head["report_version"], bool)):
                raise ArchiveValidationError(f"{location}.chapter_report_head", "章节报告 head 必须指向最后追加的版本，包括作废版本")
        elif "chapter_report_head" in chapter and (head != {"report_version": 0, "report_id": None}
                or not isinstance(head["report_version"], int) or isinstance(head["report_version"], bool)):
            raise ArchiveValidationError(f"{location}.chapter_report_head", "没有报告的章节只能没有 head 或保存 0/null")

    keys = set()
    input_models = {
        "confirm_event": ChapterEventConfirmV1, "confirm_report": ChapterReportConfirmV1,
        "confirm_psychological_state": ChapterPsychologicalStateConfirmV1,
        "void_event": ChapterRecordVoidV1, "void_report": ChapterRecordVoidV1,
    }
    if format_version >= 6:
        input_models["confirm_item_owner"] = ChapterItemOwnerConfirmV1
    if format_version >= 7:
        input_models["confirm_character_relation_state"] = ChapterCharacterRelationStateConfirmV1
    for receipt in documents["chapter_record_confirmation_receipts"]:
        location = locations["chapter_record_confirmation_receipts", receipt["_id"]]
        _validate_chapter_record_source(receipt, location, by_id, summary)
        operation, request = receipt.get("operation"), receipt.get("request")
        for field in ("idempotency_key_hash", "request_hash"):
            if not isinstance(receipt.get(field), str) or re.fullmatch(r"[0-9a-f]{64}", receipt[field]) is None:
                raise ArchiveValidationError(f"{location}.{field}", "确认回执必须保存 SHA-256 摘要")
        if receipt["idempotency_key_hash"] in keys:
            raise ArchiveValidationError(location, "确认回执请求键重复")
        keys.add(receipt["idempotency_key_hash"])
        if (not isinstance(operation, str) or operation not in input_models or not isinstance(request, dict)
                or set(request) != {"operation", "novel_id", "target_id", "data"}
                or request["operation"] != operation or request["novel_id"] != str(novel_id)
                or canonical_request_hash(request) != receipt["request_hash"]
                or not isinstance(receipt.get("created_at"), datetime)):
            raise ArchiveValidationError(location, "确认回执命令、完整请求或请求摘要不一致")
        try:
            data = input_models[operation].model_validate(request["data"]).model_dump()
        except ValidationError as exc:
            raise ArchiveValidationError(f"{location}.request", "回执请求不符合该命令的严格输入") from exc
        if data != request["data"]:
            raise ArchiveValidationError(f"{location}.request", "回执必须保留完成规范化且包含默认字段的原确认请求")
        result = receipt.get("result")
        if operation == "confirm_item_owner":
            try:
                result = ChapterItemOwnerResultV1.model_validate(result).model_dump()
            except ValidationError as exc:
                raise ArchiveValidationError(f"{location}.result", "物品转交回执快照不正确") from exc
            history = result["history"]
            row = by_id["entity_state_history"].get(ObjectId(history["history_id"]))
            if (request["target_id"] is not None or result["novel_id"] != str(novel_id)
                    or result["item_id"] != data["item_id"] or result["owner_character_id"] != data["to_character_id"]
                    or result["evidence"] != data["evidence"] or result["evidence"] != receipt["evidence"]
                    or result["needs_review"] is not False or row is None
                    or history != serialize_chapter_record({**row, "needs_review": False}, "history")
                    or row["entity_type"] != "item" or row["item_id"] != result["item_id"]
                    or row["before"]["owner_character_id"] != data["from_character_id"]
                    or row["after"]["owner_character_id"] != result["owner_character_id"]
                    or row["before_version"] != data["expected_version"] or row["after_version"] != result["item_version"]
                    or row["confirmed_at"] != result["confirmed_at"] or row["evidence"] != receipt["evidence"]
                    or row["chapter_id"] != receipt["chapter_id"] or row["source_parents"] != receipt["source_parents"]):
                raise ArchiveValidationError(location, "物品转交原请求、成功响应与实际变化历史不一致")
            basis = data["basis"]
            generation_input = {
                "novel_id": str(novel_id),
                "source": {field: data["evidence"][field] for field in ("chapter_id", "revision_id", "version", "content_hash")},
                **{field: data[field] for field in ("item_id", "expected_version", "from_character_id", "to_character_id")},
            }
            snapshot = basis["flow_snapshot"]
            source_refs = basis["source_refs"]
            item_refs = [ref for ref in source_refs if ref["resource_type"] == "item"]
            character_refs = [ref for ref in source_refs if ref["resource_type"] == "character"]
            if (basis["novel_id"] != str(novel_id) or basis["workflow"] != "check_chapter_item_owner_by_ai"
                    or basis["step"] != "check_chapter_item_owner" or basis["schema_id"] != "chapter.item_owner_check.result"
                    or basis["schema_version"] != 1 or snapshot["scope"] != generation_input
                    or snapshot["business_input"] != generation_input or len(source_refs) != 3
                    or [ref["resource_type"] for ref in source_refs] != ["item", "character", "character"]
                    or item_refs != [{"resource_type": "item", "id": str(row["entity_id"]), "version": row["before_version"]}]
                    or len(character_refs) != 2):
                raise ArchiveValidationError(location, "物品转交依据必须绑定原物品、两个人物和固定转交方向")
            for field, ref in zip(("from_character_id", "to_character_id"), character_refs):
                if not ObjectId.is_valid(ref["id"]) or ref["id"] != str(ObjectId(ref["id"])):
                    raise ArchiveValidationError(location, "物品转交依据必须保留人物 BSON ID")
                character = by_id["characters"].get(ObjectId(ref["id"]))
                if character is not None and (character["character_id"] != data[field]
                        or character["version"] < ref["version"]):
                    raise ArchiveValidationError(location, "现存人物身份或版本与转交依据不一致")
                known_character = by_business["characters"].get(data[field])
                if known_character is not None and known_character["_id"] != ObjectId(ref["id"]):
                    raise ArchiveValidationError(location, "转交人物业务 ID 与依据 BSON ID 不一致")
            reads = snapshot["execution"].get("source_refs_by_node")
            if (not isinstance(reads, dict) or reads.get("preflight") != source_refs
                    or any(value != source_refs for value in reads.values())):
                raise ArchiveValidationError(location, "原检查必须在每次读取中保留完整物品和人物版本")
            # 用当时保存的输入核对摘要；后来的普通编辑不能使历史回执失效。
            expected_fingerprint = compute_candidate_input_fingerprint(
                **{field: basis[field] for field in ("novel_id", "workflow", "step", "schema_id", "schema_version", "source_refs")},
                inputs={"generation_input": generation_input, "task_flow": snapshot},
            )
            if expected_fingerprint != basis["input_fingerprint"]:
                raise ArchiveValidationError(location, "物品转交依据摘要与原输入不一致")
            if row["_id"] in confirmed["entity_state_history"]:
                raise ArchiveValidationError(location, "同一变化历史不能有两份原确认回执")
            confirmed["entity_state_history"].add(row["_id"])
        elif operation == "confirm_character_relation_state":
            try:
                result = ChapterCharacterRelationStateResultV1.model_validate(result).model_dump()
            except ValidationError as exc:
                raise ArchiveValidationError(f"{location}.result", "人物关系状态回执快照不正确") from exc
            if (result != receipt["result"] or request["target_id"] is not None
                    or result["novel_id"] != str(novel_id) or result["relation_id"] != data["relation_id"]
                    or result["entity_id"] != str(ObjectId(result["entity_id"]))
                    or result["source_character_id"] == result["target_character_id"]
                    or result["current_state"] != data["current_state"]
                    or result["evidence"] != data["evidence"] or result["evidence"] != receipt["evidence"]
                    or result["needs_review"] is not False):
                raise ArchiveValidationError(location, "人物关系状态原请求、固定身份、来源和成功响应不一致")
            history = result["history"]
            if history is None:
                if result["relation_version"] != data["expected_version"]:
                    raise ArchiveValidationError(location, "无变化确认不能增加人物关系版本")
            else:
                row = by_id["entity_state_history"].get(ObjectId(history["history_id"]))
                if (row is None or row["entity_type"] != "character_relation"
                        or history != serialize_chapter_record({**row, "needs_review": False}, "history")
                        or str(row["entity_id"]) != result["entity_id"]
                        or any(row[field] != result[field] for field in ("relation_id", "source_character_id", "target_character_id"))
                        or row["before_version"] != data["expected_version"] or row["after_version"] != result["relation_version"]
                        or row["after"]["current_state"] != result["current_state"]
                        or row["confirmed_at"] != result["confirmed_at"] or row["evidence"] != receipt["evidence"]
                        or row["chapter_id"] != receipt["chapter_id"] or row["source_parents"] != receipt["source_parents"]):
                    raise ArchiveValidationError(location, "人物关系状态回执与实际变化历史不一致")
                if row["_id"] in confirmed["entity_state_history"]:
                    raise ArchiveValidationError(location, "同一变化历史不能有两份原确认回执")
                confirmed["entity_state_history"].add(row["_id"])
            relation = _reference(ObjectId(result["entity_id"]), by_id["character_relations"],
                                  f"{location}.result.entity_id", summary, physical=True, historical=True)
            known_relation = by_business["character_relations"].get(result["relation_id"])
            if (relation is not None and any(relation[field] != result[field] for field in
                                            ("relation_id", "source_character_id", "target_character_id"))
                    or known_relation is not None and known_relation["_id"] != ObjectId(result["entity_id"])):
                raise ArchiveValidationError(location, "历史人物关系的 BSON ID、稳定业务 ID 或固定端点不一致")
            if relation is not None and relation["version"] < result["relation_version"]:
                raise ArchiveValidationError(location, "现存人物关系版本不能低于确认结果版本")
            if (relation is not None and relation["version"] == result["relation_version"]
                    and relation.get("current_state") != result["current_state"]):
                raise ArchiveValidationError(location, "人物关系版本未再变化时，当前状态必须与确认结果一致")
            sequence_minimum["character_relation"] = max(sequence_minimum["character_relation"],
                _business_number(result["relation_id"], "cr", f"{location}.result.relation_id"))
            required_sequences.add("character_relation")
            basis = data["basis"]
            generation_input = {
                "novel_id": str(novel_id),
                "source": {field: data["evidence"][field] for field in ("chapter_id", "revision_id", "version", "content_hash")},
                **{field: data[field] for field in ("relation_id", "expected_version")},
            }
            snapshot, source_refs = basis["flow_snapshot"], basis["source_refs"]
            if (basis["novel_id"] != str(novel_id) or basis["workflow"] != "check_chapter_character_relation_state_by_ai"
                    or basis["step"] != "check_chapter_character_relation_state"
                    or basis["schema_id"] != "chapter.character_relation_state_check.result" or basis["schema_version"] != 1
                    or snapshot["scope"] != generation_input or snapshot["business_input"] != generation_input
                    or len(source_refs) != 3
                    or [ref["resource_type"] for ref in source_refs] != ["character_relation", "character", "character"]
                    or source_refs[0] != {"resource_type": "character_relation", "id": result["entity_id"], "version": data["expected_version"]}):
                raise ArchiveValidationError(location, "人物关系状态依据必须绑定原关系和两个固定人物")
            for field, ref in zip(("source_character_id", "target_character_id"), source_refs[1:]):
                if not ObjectId.is_valid(ref["id"]) or ref["id"] != str(ObjectId(ref["id"])):
                    raise ArchiveValidationError(location, "人物关系状态依据必须保留人物 BSON ID")
                character = _reference(ObjectId(ref["id"]), by_id["characters"],
                                       f"{location}.request.data.basis.{field}", summary, physical=True, historical=True)
                known_character = by_business["characters"].get(result[field])
                if (character is not None and (character["character_id"] != result[field] or character["version"] < ref["version"])
                        or known_character is not None and known_character["_id"] != ObjectId(ref["id"])):
                    raise ArchiveValidationError(location, "人物关系端点业务 ID、BSON ID 或版本与原依据不一致")
                if (relation_endpoint_business_ids.setdefault(ref["id"], result[field]) != result[field]
                        or relation_endpoint_physical_ids.setdefault(result[field], ref["id"]) != ref["id"]):
                    raise ArchiveValidationError(location, "人物关系端点的历史身份在原回执之间不一致")
                sequence_minimum["character"] = max(sequence_minimum["character"],
                    _business_number(result[field], "char", f"{location}.result.{field}"))
                required_sequences.add("character")
            reads = snapshot["execution"].get("source_refs_by_node")
            if (not isinstance(reads, dict) or reads.get("preflight") != source_refs
                    or any(value != source_refs for value in reads.values())):
                raise ArchiveValidationError(location, "原检查必须在每次读取中保留完整关系和人物版本")
            # 只用归档中当时的快照重算，不读取当前流程配置或当前目标内容。
            expected_fingerprint = compute_candidate_input_fingerprint(
                **{field: basis[field] for field in ("novel_id", "workflow", "step", "schema_id", "schema_version", "source_refs")},
                inputs={"generation_input": generation_input, "task_flow": snapshot},
            )
            if expected_fingerprint != basis["input_fingerprint"]:
                raise ArchiveValidationError(location, "人物关系状态依据摘要与原输入不一致")
            relation_records.append((result, [(result["relation_version"], result["current_state"])], location))
        elif operation == "confirm_psychological_state":
            try:
                result = ChapterPsychologicalStateResultV1.model_validate(result).model_dump()
            except ValidationError as exc:
                raise ArchiveValidationError(f"{location}.result", "心理状态回执快照不正确") from exc
            if (request["target_id"] is not None or data["state_id"] != str(ObjectId(data["state_id"]))
                    or result["novel_id"] != str(novel_id) or result["state_id"] != data["state_id"]
                    or result["evidence"] != data["evidence"] or result["evidence"] != receipt["evidence"]
                    or result["psychological_state"] != unicodedata.normalize("NFKC", data["psychological_state"]).strip()
                    or result["needs_review"] is not False):
                raise ArchiveValidationError(location, "心理状态原请求、来源和成功响应不一致")
            history = result["history"]
            if history is None:
                if result["state_version"] != data["expected_version"]:
                    raise ArchiveValidationError(location, "无变化确认不能增加状态版本")
                state = by_id["character_volume_states"].get(ObjectId(data["state_id"]))
                if state is not None and state["volume_id"] != receipt["source_parents"]["volume_id"]:
                    raise ArchiveValidationError(location, "无变化确认的状态必须属于来源卷")
                if state is not None and state["version"] < result["state_version"]:
                    raise ArchiveValidationError(location, "现存状态版本不能低于无变化回执版本")
            else:
                row = by_id["entity_state_history"].get(ObjectId(history["history_id"]))
                if (row is None or history != serialize_chapter_record({**row, "needs_review": False}, "history")
                        or row["entity_id"] != ObjectId(result["state_id"])
                        or row["before_version"] != data["expected_version"] or row["after_version"] != result["state_version"]
                        or row["after"]["psychological_state"] != result["psychological_state"]
                        or row["confirmed_at"] != result["confirmed_at"] or row["evidence"] != receipt["evidence"]):
                    raise ArchiveValidationError(location, "心理状态回执与实际变化历史不一致")
                if row["_id"] in confirmed["entity_state_history"]:
                    raise ArchiveValidationError(location, "同一变化历史不能有两份原确认回执")
                confirmed["entity_state_history"].add(row["_id"])
        else:
            name, kind, id_field = (("events", "event", "event_id") if operation.endswith("event")
                                    else ("chapter_reports", "report", "report_id"))
            if not isinstance(result, dict) or not isinstance(result.get(id_field), str) or not ObjectId.is_valid(result[id_field]):
                raise ArchiveValidationError(f"{location}.result", "确认快照缺少记录 ID")
            row = by_id[name].get(ObjectId(result[id_field]))
            if row is None:
                raise ArchiveValidationError(location, "不可变确认结果的正式记录缺失")
            try:
                expected = serialize_chapter_record({**row, "needs_review": result.get("needs_review")}, kind)
            except ValidationError as exc:
                raise ArchiveValidationError(f"{location}.result", "原成功快照缺少严格布尔 needs_review") from exc
            if operation.startswith("confirm_"):
                expected.update(voided_at=None, void_reason=None)
                if (request["target_id"] is not None or row["_id"] in confirmed[name]
                        or any(data[field] != row[field] for field in data if field != "expected_report_version")
                        or name == "chapter_reports" and data["expected_report_version"] != row["report_version"] - 1):
                    raise ArchiveValidationError(location, "原确认请求与事件或报告内容不一致")
                confirmed[name].add(row["_id"])
            else:
                if (request["target_id"] != str(row["_id"]) or row["voided_at"] is None or row["_id"] in voided[name]
                        or data["reason"] != row["void_reason"]):
                    raise ArchiveValidationError(location, "作废请求与记录的单向作废结果不一致")
                voided[name].add(row["_id"])
            if result != expected or row["evidence"] != receipt["evidence"]:
                raise ArchiveValidationError(location, "确认回执必须保存原成功快照及对应来源")
        summary["receipts"] += 1
        summary["unique_keys"] += 1
    # 已删除对象也保留唯一历史身份；同一版本的已知原值、结果和同值回执不能互相矛盾。
    relation_identities, relation_business_ids, relation_values = {}, {}, {}
    for record, values, location in relation_records:
        physical_id = str(record["entity_id"])
        identity = tuple(record[field] for field in ("relation_id", "source_character_id", "target_character_id"))
        if (relation_identities.setdefault(physical_id, identity) != identity
                or relation_business_ids.setdefault(record["relation_id"], physical_id) != physical_id):
            raise ArchiveValidationError(location, "人物关系的历史身份或固定端点在历史与原回执之间不一致")
        for version, value in values:
            if relation_values.setdefault((physical_id, version), value) != value:
                raise ArchiveValidationError(location, "同一人物关系版本的已知状态在历史与原回执之间不一致")
    for name, identities in confirmed.items():
        if identities != set(by_id[name]):
            raise ArchiveValidationError(f"collections/{name}.jsonl", "不可变记录缺少同事务保存的原确认回执")
    for name, identities in voided.items():
        if identities != {row["_id"] for row in documents[name] if row["voided_at"] is not None}:
            raise ArchiveValidationError(f"collections/{name}.jsonl", "作废记录缺少对应确认回执")


def _validate_character_fact_source(document: dict, location: str, by_id: dict, summary: dict, *, relation_fact: bool = False) -> None:
    """校验真正保护的位置、证据和父链；关系按物理身份等值核对，不改原请求。

    Args:
        document: 严格事实记录或首次回执。
        location: 包内原文档位置。
        by_id: 按集合保存的同书物理身份。
        summary: 累加来源引用数量。
        relation_fact: v9 关系允许公开 ObjectId 大小写等值，旧人物规则保持原样。
    Returns:
        无；真实来源或不可变修订缺失时拒绝。
    """
    for ref in document["protected_sources"]:
        collection = f"{ref['resource_type']}s"
        row = _reference(ObjectId(ref["id"]), by_id[collection], location, summary, physical=True)
        parent_field = {"volume": "novel_id", "arc": "volume_id", "scene": "arc_id", "chapter": "scene_id"}.get(ref["resource_type"])
        parent_id = str(ObjectId(ref["parent_id"])) if relation_fact and ref["parent_id"] is not None else ref["parent_id"]
        if parent_field and str(row[parent_field]) != parent_id:
            raise ArchiveValidationError(location, "人物事实保护来源的真实父链不一致")
    if document["source"]["kind"] == "chapter":
        evidence = document["source"]["evidence"]
        if relation_fact:
            # 只给共用旧证据检查一个等值视图，首次 hash、request/result 和 BSON 原文不重写。
            evidence = {**evidence, **{field: str(ObjectId(evidence[field])) for field in ("chapter_id", "revision_id")}}
        parents = {f"{ref['resource_type']}_id": ObjectId(ref["id"])
                   for ref in document["protected_sources"] if ref["resource_type"] in {"volume", "arc", "scene"}}
        _validate_chapter_record_source({"chapter_id": ObjectId(document["position"]["target_id"]),
                                        "source_parents": parents, "evidence": evidence}, location, by_id, summary)


def _validate_character_facts(documents: dict, novel_id: ObjectId, by_id: dict, by_business: dict,
                              locations: dict, summary: dict, sequence_minimum: dict, required_sequences: set) -> None:
    """核对 v8 人物事实原记录、逐字段处置和原成功回执；旧 A/B/D 不进此分支。

    Args:
        documents: 只含精确新 schema 的历史与回执集合。
        novel_id: 当前包的 BSON 作品身份。
        by_id: 全部同书现存物理记录。
        by_business: 全部同书稳定业务身份。
        locations: 原始 BSON 文档位置。
        summary: 引用、唯一键和回执统计。
        sequence_minimum: 包括已删除人物和历史引用的序列下限。
        required_sequences: 必须保留的序列类型。
    Returns:
        无；损坏时抛出带包内位置的错误。
    """
    import json
    from backend.db.write_contracts import canonical_request_hash
    from backend.services.novel.character_fact_contract import (
        CharacterFactBasisV1, CharacterFactResultV1,
        parse_character_fact_record, validate_character_fact_receipt,
    )

    records, immutable_hashes = {}, {}
    entity_business, business_entities, version_actions = {}, {}, set()
    active_positions = set()
    for raw in documents["entity_state_history"]:
        location = locations["entity_state_history", raw["_id"]]
        try:
            row = parse_character_fact_record(raw)
        except ValueError as exc:
            raise ArchiveValidationError(location, "人物事实记录不符合精确 schema/version 或固定字段") from exc
        records[row["history_id"]] = row
        immutable_hashes[row["history_id"]] = canonical_request_hash({key: value for key, value in row.items() if key != "validity"})
        _validate_character_fact_source(row, location, by_id, summary)
        for field, validity in row["validity"].items():
            if validity["state"] == "active":
                position_key = (row["entity_id"], field, row["position"]["intent"], row["position"]["target_id"])
                if position_key in active_positions:
                    raise ArchiveValidationError(location, "同一人物字段位置不能有两个未被替代或作废的记录")
                active_positions.add(position_key)

    record_receipts, dispositions = {}, {}
    frozen_bases = []
    for raw in documents["chapter_record_confirmation_receipts"]:
        location = locations["chapter_record_confirmation_receipts", raw["_id"]]
        try:
            # 新请求和原结果本来就保存 JSON；不能在恢复时猜测并改写时间或 BSON 身份。
            json.dumps(raw["request"], allow_nan=False)
            json.dumps(raw["result"], allow_nan=False)
            validate_character_fact_receipt(raw)
            result = CharacterFactResultV1.model_validate(raw["result"]).model_dump(exclude_unset=True)
            basis = CharacterFactBasisV1.model_validate(raw["request"]["data"]["basis"]).model_dump(exclude_unset=True)
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "人物事实回执必须保留严格原请求、JSON 成功快照及精确摘要") from exc
        _validate_character_fact_source(raw, location, by_id, summary)
        entity_id, business_id = result["entity_id"], result["character_id"]
        if (entity_business.setdefault(entity_id, business_id) != business_id
                or business_entities.setdefault(business_id, entity_id) != entity_id):
            raise ArchiveValidationError(location, "人物事实历史物理身份和业务身份不能重绑")
        target = _reference(ObjectId(entity_id), by_id["characters"], location, summary, physical=True, historical=True)
        business_target = by_business["characters"].get(business_id)
        if ((target is not None and target["character_id"] != business_id)
                or (business_target is not None and str(business_target["_id"]) != entity_id)):
            raise ArchiveValidationError(location, "人物事实物理身份与现存稳定业务身份不一致")
        if target is not None and (type(target.get("version")) is not int or target["version"] < result["after_version"]):
            raise ArchiveValidationError(location, "现存人物必须保留不低于全部事实动作的真实业务版本")
        sequence_minimum["character"] = max(sequence_minimum["character"], _business_number(business_id, "char", location))
        required_sequences.add("character")
        action_key = (entity_id, result["after_version"])
        if action_key in version_actions:
            raise ArchiveValidationError(location, "一次人物版本只能属于一个确认或作废动作")
        version_actions.add(action_key)
        row = result["record"]
        if row is not None:
            identity = row["history_id"]
            actual = records.get(identity)
            if (actual is None or identity in record_receipts
                    or canonical_request_hash({key: value for key, value in row.items() if key != "validity"}) != immutable_hashes[identity]):
                raise ArchiveValidationError(location, "每条新人物事实必须精确配对唯一原成功回执，不可改写原值或来源")
            record_receipts[identity] = raw
        for change in result["validity_changes"]:
            key = (change["history_id"], change["field"])
            original = records.get(key[0])
            if (key in dispositions or original is None or original["entity_id"] != entity_id
                    or key[1] not in original["after"] or original["after_version"] >= result["after_version"]
                    or original["validity"][key[1]] != change["after"]):
                raise ArchiveValidationError(location, "替代或作废必须唯一配对更早的同人物字段及当前终态")
            dispositions[key] = (result["after_version"], change["after"])
        frozen_bases.append((basis, location))
        summary["receipts"] += 1
        summary["unique_keys"] += 1

    if set(record_receipts) != set(records):
        raise ArchiveValidationError("collections/entity_state_history.jsonl", "人物事实历史缺少对应原成功回执")
    for identity, row in records.items():
        location = locations["entity_state_history", ObjectId(identity)]
        for field, validity in row["validity"].items():
            if (validity["state"] != "active") != ((identity, field) in dispositions):
                raise ArchiveValidationError(location, "每项替代或作废终态必须有完整处置回执，活动字段不能伪带处置")
        for field, previous_id in row["previous"].items():
            if previous_id is None:
                continue
            previous = records.get(previous_id)
            if (previous is None or previous["entity_id"] != row["entity_id"] or field not in previous["after"]
                    or previous["after_version"] >= row["after_version"]
                    or previous["after"][field] != row["before"]["values"][field]):
                raise ArchiveValidationError(location, "已知前值必须来自更早同人物同字段的完整确认记录")
        for field, identities in row["resolves"].items():
            if any(reference not in records or records[reference]["entity_id"] != row["entity_id"]
                   or field not in records[reference]["after"] or records[reference]["after_version"] >= row["after_version"]
                   for reference in identities):
                raise ArchiveValidationError(location, "解除依据必须属于更早的同人物同字段记录")
        target = by_id["characters"].get(ObjectId(row["entity_id"]))
        if target is not None and row["position"]["intent"] == "book_start":
            for field, value in row["after"].items():
                if (field not in {"psychological_state", "public_state", "hidden_state", "actual_goal"}
                        and row["validity"][field]["state"] == "active" and target.get(field) != value):
                    raise ArchiveValidationError(location, "未作废或替代的书初字段必须与主档初始镜像一致")

    entity_collections = {entity: name for name, (_, entity, _) in BUSINESS_IDS.items() if name != "foreshadowings"}
    entity_collections.update(character_volume_state="character_volume_states", faction_volume_state="faction_volume_states")
    legacy_state_identities = {}
    for old in by_id["entity_state_history"].values():
        if "schema_id" not in old and "schema_version" not in old and old["entity_type"] == "character_volume_state":
            # 只使用旧 A 已明确记录的身份，不把其值或审计时刻升级为剧情事实。
            identity = (old["character_id"], old["volume_id"])
            legacy_state_identities.setdefault(old["entity_id"], set()).add(identity)
    for basis, location in frozen_bases:
        target_version = basis["target"].get("version", 0)
        for snapshot in [*basis["targets"], *basis["field_sources"]]:
            identity = snapshot["history_id"]
            if (identity not in records or snapshot["after_version"] > target_version
                    or canonical_request_hash({key: value for key, value in snapshot.items() if key != "validity"}) != immutable_hashes[identity]):
                raise ArchiveValidationError(location, "预览所操作及解释来源必须保留原不可变记录快照")
            for field, validity in snapshot["validity"].items():
                disposition = dispositions.get((identity, field))
                expected = disposition[1] if disposition is not None and disposition[0] <= target_version else {"state": "active"}
                if validity != expected:
                    raise ArchiveValidationError(location, "预览记录有效性必须与该人物原预览版本一致")
        for read in basis["reads"]:
            # 这是当时目录的内部父链；无关成员之后硬删除不应损坏原成功回执。
            directory = {row["id"]: row for row in read["directory"]}
            if len(directory) != len(read["directory"]):
                raise ArchiveValidationError(location, "冻结目录物理身份不能重复")
            parent_types = {"volume": "novel", "arc": "volume", "scene": "arc", "chapter": "scene"}
            for entry in directory.values():
                expected = parent_types[entry["resource_type"]]
                if (expected == "novel" and entry["parent_id"] != read["novel_id"]
                        or expected != "novel" and (entry["parent_id"] not in directory
                        or directory[entry["parent_id"]]["resource_type"] != expected)):
                    raise ArchiveValidationError(location, "冻结目录的层级和父链不自洽")
            position = read["position"]
            if position["target_type"] == "novel":
                if position["target_id"] != read["novel_id"] or position["order"]:
                    raise ArchiveValidationError(location, "冻结书初位置必须属于当前小说")
            else:
                entry = directory.get(position["target_id"])
                if entry is None or entry["resource_type"] != position["target_type"]:
                    raise ArchiveValidationError(location, "冻结读取位置必须存在于当时目录")
                order = [entry["order_index"]]
                while entry["resource_type"] != "volume":
                    entry = directory[entry["parent_id"]]
                    order.append(entry["order_index"])
                if list(reversed(order)) != position["order"]:
                    raise ArchiveValidationError(location, "冻结读取顺序必须与当时完整父链一致")
            for observation in read["history"]:
                actual = records.get(observation["history_id"])
                if (actual is None or actual["entity_id"] != observation["entity_id"]
                        or immutable_hashes[observation["history_id"]] != observation["immutable_fingerprint"]
                        or observation["validity"].keys() != actual["validity"].keys()):
                    raise ArchiveValidationError(location, "冻结读取必须匹配原不可变记录指纹及字段集合")
                if actual["entity_id"] == basis["target"]["entity_id"] and actual["after_version"] > target_version:
                    raise ArchiveValidationError(location, "冻结读取不能包含预览版本之后才确认的同人物事实")
                for field, validity in observation["validity"].items():
                    disposition = dispositions.get((observation["history_id"], field))
                    expected = disposition[1] if disposition is not None and disposition[0] <= target_version else {"state": "active"}
                    if ((actual["entity_id"] == basis["target"]["entity_id"] and validity != expected)
                            or validity["state"] != "active" and validity != actual["validity"][field]):
                        raise ArchiveValidationError(location, "冻结读取不能伪造原预览版本的替代或作废状态")
            for source in read["sources"]:
                if source["revision_valid"]:
                    revision = by_id["chapter_revisions"].get(ObjectId(source["revision_id"]))
                    if (revision is None or str(revision["chapter_id"]) != source["chapter_id"]
                            or revision["version"] != source["revision_version"] or revision["content_hash"] != source["revision_hash"]):
                        raise ArchiveValidationError(location, "冻结有效来源必须对应原不可变修订身份、版本及摘要")
        for legacy in basis["legacy_sources"]:
            if legacy["kind"] == "profile":
                # 严格 basis 已绑定目标身份/原版本；上面也已核对现存人物。
                continue
            identity = (legacy["character_id"], ObjectId(legacy["volume_id"]))
            if legacy_state_identities.setdefault(ObjectId(legacy["state_id"]), {identity}) != {identity}:
                raise ArchiveValidationError(location, "旧卷状态的冻结人物身份或卷归属不能重绑")
            state = _reference(ObjectId(legacy["state_id"]), by_id["character_volume_states"], location, summary, physical=True, historical=True)
            if state is not None and (state["character_id"] != legacy["character_id"]
                    or state["volume_id"] != ObjectId(legacy["volume_id"])
                    or type(state.get("version")) is not int or state["version"] < legacy["version"]):
                raise ArchiveValidationError(location, "旧卷状态的现存身份、归属及版本与原预览不一致")
            volume = _reference(ObjectId(legacy["volume_id"]), by_id["volumes"], location, summary, physical=True, historical=True)
            if volume is not None and legacy["volume"] is not None and (
                    type(volume.get("version")) is not int or volume["version"] < legacy["volume"]["version"]):
                raise ArchiveValidationError(location, "旧卷状态所属卷的现存版本不能低于原预览")
        for observation in basis["reference_reads"]:
            reference = observation["reference"]
            name = entity_collections[reference["entity_type"]]
            if not reference["entity_type"].endswith("_volume_state"):
                business_target = by_business[name].get(reference["entity_id"])
                if business_target is not None and str(business_target["_id"]) != observation["entity_id"]:
                    raise ArchiveValidationError(location, "历史引用的业务身份不能改绑另一物理身份")
            actual = by_id[name].get(ObjectId(observation["entity_id"]))
            if actual is not None:
                business_field = BUSINESS_IDS[name][0] if name in BUSINESS_IDS else "state_id"
                if (str(actual[business_field]) != reference["entity_id"] or type(actual.get("version")) is not int
                        or actual["version"] < observation["version"]):
                    raise ArchiveValidationError(location, "历史引用的现存物理身份、业务身份及版本不一致")
        for reference in basis["references"]:
            name = entity_collections[reference["entity_type"]]
            if reference["entity_type"].endswith("_volume_state"):
                _reference(ObjectId(reference["entity_id"]), by_id[name], location, summary, physical=True, historical=True)
            else:
                _, entity, prefix = BUSINESS_IDS[name]
                _reference(reference["entity_id"], by_business[name], location, summary, historical=True, business_prefix=prefix)
                sequence_minimum[entity] = max(sequence_minimum[entity], _business_number(reference["entity_id"], prefix, location))
                required_sequences.add(entity)


def _validate_relation_facts(documents: dict, by_id: dict, locations: dict, summary: dict) -> None:
    """核对 v9 关系原记录、首次回执及后续处置；不重算今天的读取结果。

    Args:
        documents: 仅含精确关系 schema 的历史和回执。
        by_id: 全部同书原文档，按集合区分物理身份。
        locations: 原文档在包内的位置。
        summary: 累加原回执、来源和唯一动作数量。
    Returns:
        无；任何缺失或不一致均拒绝归档。
    """
    import json
    from backend.db.write_contracts import canonical_request_hash
    from backend.services.novel.character_relation_fact_contract import (
        CharacterRelationFactBasisV1, CharacterRelationFactResultV1,
        parse_character_relation_fact_record, validate_character_relation_fact_receipt,
    )

    records, immutable_hashes, active_positions = {}, {}, set()
    for raw in documents["entity_state_history"]:
        location = locations["entity_state_history", raw["_id"]]
        try:
            row = parse_character_relation_fact_record(raw)
        except ValueError as exc:
            raise ArchiveValidationError(location, "关系事实必须符合精确 schema、BSON 身份、时间和固定字段") from exc
        identity = ObjectId(row["history_id"])
        records[identity] = row
        immutable_hashes[identity] = canonical_request_hash({key: value for key, value in row.items() if key != "validity"})
        _validate_character_fact_source(row, location, by_id, summary, relation_fact=True)
        if row["validity"]["current_state"]["state"] == "active":
            position_key = (ObjectId(row["entity_id"]), row["position"]["intent"], ObjectId(row["position"]["target_id"]))
            if position_key in active_positions:
                raise ArchiveValidationError(location, "同一关系位置不能有两条活动状态记录")
            active_positions.add(position_key)

    record_receipts, dispositions, frozen_bases = set(), {}, []
    for raw in documents["chapter_record_confirmation_receipts"]:
        location = locations["chapter_record_confirmation_receipts", raw["_id"]]
        try:
            # 原请求先核 hash，公开 JSON 不接受落盘时偷偷换成 BSON 或重写原文。
            json.dumps(raw["request"], allow_nan=False)
            json.dumps(raw["result"], allow_nan=False)
            validate_character_relation_fact_receipt(raw)
            result = CharacterRelationFactResultV1.model_validate(raw["result"]).model_dump(exclude_unset=True)
            basis = CharacterRelationFactBasisV1.model_validate(raw["request"]["data"]["basis"]).model_dump(exclude_unset=True)
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "关系回执必须保留严格原请求、JSON 结果、BSON 时间及精确摘要") from exc
        _validate_character_fact_source(raw, location, by_id, summary, relation_fact=True)
        row = result["record"]
        if row is not None:
            identity = ObjectId(row["history_id"])
            # 这三个公开 ID 落盘时转为 BSON，大小写不构成身份变化；只改比较副本。
            original = {**row, **{field: str(ObjectId(row[field])) for field in ("history_id", "novel_id", "entity_id")}}
            if (identity not in records or identity in record_receipts
                    or canonical_request_hash({key: value for key, value in original.items() if key != "validity"}) != immutable_hashes[identity]):
                raise ArchiveValidationError(location, "每条关系事实必须精确配对唯一首次回执，原值、身份和来源不可改写")
            record_receipts.add(identity)
        for change in result["validity_changes"]:
            identity = ObjectId(change["history_id"])
            original = records.get(identity)
            if (identity in dispositions or original is None
                    or ObjectId(original["entity_id"]) != ObjectId(result["entity_id"])
                    or original["after_version"] >= result["after_version"]
                    or original["validity"]["current_state"] != change["after"]):
                raise ArchiveValidationError(location, "关系替代或作废必须唯一配对更早的同关系记录及当前终态")
            dispositions[identity] = (result["after_version"], change["after"])
        frozen_bases.append((basis, location))
        summary["receipts"] += 1
        summary["unique_keys"] += 1

    if record_receipts != records.keys():
        raise ArchiveValidationError("collections/entity_state_history.jsonl", "关系事实历史缺少唯一首次成功回执")
    for identity, row in records.items():
        location = locations["entity_state_history", identity]
        if (row["validity"]["current_state"]["state"] != "active") != (identity in dispositions):
            raise ArchiveValidationError(location, "关系记录终态必须有完整处置回执，活动状态不能带处置")
        previous_id = row["previous"]["current_state"]
        if previous_id is not None:
            previous = records.get(ObjectId(previous_id))
            if (previous is None or ObjectId(previous["entity_id"]) != ObjectId(row["entity_id"])
                    or previous["after_version"] >= row["after_version"]
                    or previous["after"]["current_state"] != row["before"]["values"]["current_state"]):
                raise ArchiveValidationError(location, "关系前值必须来自更早的同关系新事实，不能借旧 D 补起点")
        for reference in [*row["replaces"].values(), *(item for values in row["resolves"].values() for item in values)]:
            original = records.get(ObjectId(reference))
            if (original is None or ObjectId(original["entity_id"]) != ObjectId(row["entity_id"])
                    or original["after_version"] >= row["after_version"]):
                raise ArchiveValidationError(location, "关系替代及解除依据必须属于更早的同关系新事实")
        # 裸 current_state 还可能保留旧 D/资料编辑或后来被作废的初始更正，不能倒推为当前事实。

    for basis, location in frozen_bases:
        target_version = basis["target"].get("version", 0)
        for snapshot in [*basis["targets"], *basis["field_sources"]]:
            identity = ObjectId(snapshot["history_id"])
            if (identity not in records or snapshot["after_version"] > target_version
                    or canonical_request_hash({key: value for key, value in snapshot.items() if key != "validity"}) != immutable_hashes[identity]):
                raise ArchiveValidationError(location, "关系预览快照必须对应保留的原不可变记录")
            disposition = dispositions.get(identity)
            expected = disposition[1] if disposition is not None and disposition[0] <= target_version else {"state": "active"}
            if snapshot["validity"]["current_state"] != expected:
                raise ArchiveValidationError(location, "关系预览快照有效性与当时版本不一致")
        for read in basis["reads"]:
            # 严格 Read 已按集合核对当时目录及父链；不要求无关旧目录成员今天还存在。
            expected_history = {identity for identity, row in records.items()
                                if ObjectId(row["entity_id"]) == ObjectId(basis["target"]["entity_id"])
                                and row["after_version"] <= target_version}
            if {ObjectId(row["history_id"]) for row in read["history"]} != expected_history:
                raise ArchiveValidationError(location, "关系原读取必须完整保留当时已有记录，不能漏掉后伪称未认领")
            for observation in read["history"]:
                identity = ObjectId(observation["history_id"])
                actual = records.get(identity)
                if (actual is None or ObjectId(actual["entity_id"]) != ObjectId(observation["entity_id"])
                        or actual["relation_id"] != observation["relation_id"]
                        or actual["after_version"] != observation["after_version"]
                        or actual["after_version"] > target_version
                        or immutable_hashes[identity] != observation["immutable_fingerprint"]):
                    raise ArchiveValidationError(location, "关系原读取必须匹配当时已存在的原记录身份、版本及不可变摘要")
                disposition = dispositions.get(identity)
                expected = disposition[1] if disposition is not None and disposition[0] <= target_version else {"state": "active"}
                if observation["validity"]["current_state"] != expected:
                    raise ArchiveValidationError(location, "关系原读取不能伪造当时的替代或作废状态")
            for source in read["sources"]:
                if source["revision_valid"]:
                    revision = by_id["chapter_revisions"].get(ObjectId(source["revision_id"]))
                    if (revision is None or revision["chapter_id"] != ObjectId(source["chapter_id"])
                            or revision["version"] != source["revision_version"] or revision["content_hash"] != source["revision_hash"]):
                        raise ArchiveValidationError(location, "关系原有效来源必须保留同章原修订、版本及正文摘要")


def _validate_item_facts(documents: dict, by_id: dict, by_business: dict, locations: dict,
                         summary: dict, sequence_minimum: dict, required_sequences: set) -> None:
    """检查物品原记录、首次成功结果和整组作废；不按今天的状态重建历史。

    Args:
        documents: 已按物品 schema 分开的历史与回执。
        by_id: 同书原文档，按集合和物理身份索引。
        by_business: 同书现存业务身份。
        locations: 原文档在包内的位置。
        summary: 累加引用和成功请求数量。
        sequence_minimum: 包含已删除历史引用的业务号下限。
        required_sequences: 恢复时必须保留的序列。
    Returns:
        无；任何缺失或不一致都会拒绝该备份包。
    """
    import json
    from backend.db.write_contracts import canonical_request_hash
    from backend.services.novel.item_fact_contract import (
        ItemFactBasisV1, ItemFactRecordV1, ItemFactResultV1,
        parse_item_fact_record, validate_item_fact_receipt,
    )

    from backend.api.error_protocol import DomainApiError
    from backend.services.novel.item_fact_reader import evaluate_item_facts
    from backend.services.novel.writing_position import PARENTS

    records, immutable_hashes, active_positions = {}, {}, set()
    groups = []
    for raw in documents["entity_state_history"]:
        location = locations["entity_state_history", raw["_id"]]
        try:
            row = ItemFactRecordV1.model_validate(parse_item_fact_record(raw)).model_dump(mode="json")
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "物品记录的格式、身份或四项状态不正确") from exc
        identity = ObjectId(row["history_id"])
        records[identity] = row
        immutable_hashes[identity] = canonical_request_hash({key: value for key, value in row.items() if key != "validity"})
        _validate_character_fact_source(row, location, by_id, summary, relation_fact=True)
        groups.extend((value, location) for value in (row["before"]["values"], row["after"]) if value is not None)
        if row["validity"]["state"] == "active":
            key = (ObjectId(row["entity_id"]), row["position"]["intent"], ObjectId(row["position"]["target_id"]))
            if key in active_positions:
                raise ArchiveValidationError(location, "同一物品位置不能有两条活动状态记录")
            active_positions.add(key)

    record_receipts, dispositions, frozen_bases = set(), {}, []
    for raw in documents["chapter_record_confirmation_receipts"]:
        location = locations["chapter_record_confirmation_receipts", raw["_id"]]
        try:
            json.dumps(raw["request"], allow_nan=False)
            json.dumps(raw["result"], allow_nan=False)
            validate_item_fact_receipt(raw)
            result = ItemFactResultV1.model_validate(raw["result"]).model_dump(mode="json")
            basis = ItemFactBasisV1.model_validate(raw["request"]["data"]["basis"]).model_dump(mode="json")
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "物品回执必须保留原请求、首次结果和正确的请求摘要") from exc
        _validate_character_fact_source(raw, location, by_id, summary, relation_fact=True)
        row = result["record"]
        if row is not None:
            references = {(ref["resource_type"], ref["business_id"]): ref
                          for ref in [*basis["read"]["references"], *basis["preview_references"]]}
            if any(row["after"][field] is not None and not references[kind, row["after"][field]]["available"]
                   for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"), ("location", "current_location_id"))):
                raise ArchiveValidationError(location, "首次保存采用的物品引用在原预览中必须可用")
            identity = ObjectId(row["history_id"])
            original = {**row, **{key: str(ObjectId(row[key])) for key in ("history_id", "novel_id", "entity_id")}}
            if (identity not in records or identity in record_receipts
                    or canonical_request_hash({key: value for key, value in original.items() if key != "validity"}) != immutable_hashes[identity]):
                raise ArchiveValidationError(location, "每条物品记录必须对应唯一首次成功结果，原值和来源不能被改写")
            record_receipts.add(identity)
        for change in result["validity_changes"]:
            identity = ObjectId(change["history_id"])
            old = records.get(identity)
            if (identity in dispositions or old is None or ObjectId(old["entity_id"]) != ObjectId(result["entity_id"])
                    or old["after_version"] >= result["after_version"] or old["validity"] != change["after"]):
                raise ArchiveValidationError(location, "物品替代或作废必须对应更早的同物品记录及当前处置结果")
            dispositions[identity] = (result["after_version"], change["after"])
        frozen_bases.append((basis, location))
        if basis["legacy_values"] is not None:
            groups.append((basis["legacy_values"], location))
        summary["receipts"] += 1
        summary["unique_keys"] += 1

    if record_receipts != records.keys():
        raise ArchiveValidationError("collections/entity_state_history.jsonl", "物品记录缺少唯一首次成功回执")
    for identity, row in records.items():
        location = locations["entity_state_history", identity]
        if (row["validity"]["state"] != "active") != (identity in dispositions):
            raise ArchiveValidationError(location, "物品记录的替代或作废必须有对应回执")
        if row["previous"] is not None:
            previous = records.get(ObjectId(row["previous"]))
            if (previous is None or ObjectId(previous["entity_id"]) != ObjectId(row["entity_id"])
                    or previous["after_version"] >= row["after_version"] or previous["after"] != row["before"]["values"]):
                raise ArchiveValidationError(location, "物品前值必须来自更早的同物品完整状态，不能借旧转交记录补起点")
        for reference in [row["replaces"], *row["resolves"]]:
            if reference is None:
                continue
            old = records.get(ObjectId(reference))
            if old is None or ObjectId(old["entity_id"]) != ObjectId(row["entity_id"]) or old["after_version"] >= row["after_version"]:
                raise ArchiveValidationError(location, "物品替代或解除失效必须指向更早的同物品记录")

    for basis, location in frozen_bases:
        target_version = basis["target"].get("version", 0)
        read = basis["read"]
        expected = {identity for identity, row in records.items()
                    if ObjectId(row["entity_id"]) == ObjectId(basis["target"]["entity_id"]) and row["after_version"] <= target_version}
        if {ObjectId(row["history_id"]) for row in read["records"]} != expected:
            raise ArchiveValidationError(location, "物品预览必须保留当时全部原记录，不能漏掉后假称未认领")
        for snapshot in read["records"]:
            identity = ObjectId(snapshot["history_id"])
            original = {**snapshot, **{key: str(ObjectId(snapshot[key])) for key in ("history_id", "novel_id", "entity_id")}}
            if canonical_request_hash({key: value for key, value in original.items() if key != "validity"}) != immutable_hashes[identity]:
                raise ArchiveValidationError(location, "物品预览中的原记录内容或身份被改写")
            change = dispositions.get(identity)
            validity = change[1] if change is not None and change[0] <= target_version else {"state": "active"}
            if snapshot["validity"] != validity:
                raise ArchiveValidationError(location, "物品预览不能伪造当时记录的有效状态")
        for source in read["sources"]:
            if source["revision_valid"]:
                revision = by_id["chapter_revisions"].get(ObjectId(source["revision_id"]))
                if (revision is None or revision["chapter_id"] != ObjectId(source["chapter_id"])
                        or revision["version"] != source["revision_version"] or revision["content_hash"] != source["revision_hash"]):
                    raise ArchiveValidationError(location, "物品预览中的有效来源必须保留原章修订和正文摘要")

        if basis["target"]["kind"] == "existing":
            # 只用保存时冻结的资料复算，不用今天的正文和引用状态改写过去。
            directories = {kind: {} for kind in ("volume", "arc", "scene", "chapter")}
            for kind, rows in directories.items():
                for entry in read["directory"]:
                    if entry["resource_type"] != kind:
                        continue
                    parent = PARENTS[kind]
                    ancestors = ({"novel_id": ObjectId(read["novel_id"])} if parent == "novel" else
                                 {key: value for key, value in directories[parent][ObjectId(entry["parent_id"])].items() if key.endswith("_id")})
                    rows[ObjectId(entry["id"])] = {**ancestors, f"{parent}_id": ObjectId(entry["parent_id"]), "order_index": entry["order_index"]}
            observations = {(ObjectId(row["chapter_id"]), ObjectId(row["revision_id"])): row for row in read["sources"]}
            available = {(row["resource_type"], row["business_id"]): row["available"] for row in read["references"]}
            source_checks, reference_checks = {}, {}
            for row in read["records"]:
                source_checks[row["history_id"]] = True
                if row["source"]["kind"] == "chapter":
                    evidence = row["source"]["evidence"]
                    observed = observations[ObjectId(evidence["chapter_id"]), ObjectId(evidence["revision_id"])]
                    source_checks[row["history_id"]] = bool(observed["parents_active"] and observed["revision_valid"]
                        and observed["content_hash"] == evidence["content_hash"] == observed["revision_hash"]
                        and observed["revision_version"] == evidence["version"])
                reference_checks[row["history_id"]] = all(row["after"][field] is None or available[kind, row["after"][field]]
                    for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"), ("location", "current_location_id")))
            target = {**basis["target"], "_id": ObjectId(basis["target"]["entity_id"]), "novel_id": ObjectId(read["novel_id"])}
            try:
                resolved = evaluate_item_facts(target, read["records"], read["position"], directories, source_checks, reference_checks)
            except DomainApiError as exc:
                raise ArchiveValidationError(location, "保存时冻结的物品记录无法按原位置读取") from exc
            previous = ObjectId(basis["previous"]) if basis["previous"] is not None else None
            origin = ObjectId(resolved["origin"]) if resolved["origin"] is not None else None
            if (basis["before"] != {key: resolved[key] for key in ("values", "unknown")}
                    or previous != origin or {ObjectId(value) for value in basis["blockers"]} != {ObjectId(value) for value in resolved["blockers"]}):
                raise ArchiveValidationError(location, "物品保存前的状态和来源必须与当时完整读取结果一致")

    for values, location in groups:
        for name, field in (("characters", "owner_character_id"), ("factions", "controlling_faction_id"), ("locations", "current_location_id")):
            identity = values[field]
            if identity is None:
                continue
            _, entity, prefix = BUSINESS_IDS[name]
            _reference(identity, by_business[name], location, summary, historical=True, business_prefix=prefix)
            sequence_minimum[entity] = max(sequence_minimum[entity], _business_number(identity, prefix, location))
            required_sequences.add(entity)


def _validate_faction_position_version(document: dict, location: str, format_version: int) -> None:
    """按势力归档版本检查原记录和回执中的所有位置，不改写冻结内容。

    Args:
        document: 原势力历史或回执，尚未交给共享 DTO 解析。
        location: 原文档在包内的位置。
        format_version: 只有 v14 接受势力本卷起点。
    Returns:
        无；旧格式任何受管位置夹带本卷起点时明确拒绝。
    """
    if format_version == FACTION_VOLUME_START_FORMAT_VERSION:
        return
    positions = [("position", document.get("position"))]
    request, result = document.get("request"), document.get("result")
    data = request.get("data") if isinstance(request, dict) else None
    basis = data.get("basis") if isinstance(data, dict) else None
    if isinstance(basis, dict):
        positions.append(("request.data.basis.position", basis.get("position")))
        for field in ("reads", "targets", "field_sources"):
            rows = basis.get(field)
            if isinstance(rows, list):
                positions.extend((f"request.data.basis.{field}.{index}.position", row.get("position"))
                                 for index, row in enumerate(rows) if isinstance(row, dict))
    record = result.get("record") if isinstance(result, dict) else None
    if isinstance(record, dict):
        positions.append(("result.record.position", record.get("position")))
    for path, position in positions:
        if isinstance(position, dict) and position.get("intent") == "volume_start":
            raise ArchiveValidationError(f"{location}.{path}", "势力本卷开始位置需要 v14 备份格式")


def _validate_faction_facts(documents: dict, by_id: dict, locations: dict, summary: dict, *, format_version: int) -> None:
    """验证势力记录、逐字段处置及冻结原文，不把旧资料转成新事实。

    Args:
        documents: 按格式分派后的势力记录和回执。
        by_id: 同书各集合的原 BSON 文档。
        locations: 原文档在包内的位置。
        summary: 累加回执与历史引用统计。
        format_version: 本包版本；共享 DTO 扩展不能放宽旧包位置含义。
    Returns:
        无；原记录、读取依据、来源或身份不一致时拒绝归档。
    """
    import json
    from backend.api.error_protocol import DomainApiError
    from backend.db.write_contracts import canonical_request_hash
    from backend.services.novel.faction_fact_contract import (
        FACTION_FACT_PROFILE_FIELDS, FactionFactBasisV1,
        parse_faction_fact_record, validate_faction_fact_receipt,
    )
    from backend.services.novel.faction_fact_reader import evaluate_faction_facts
    from backend.services.novel.writing_position import PARENTS, writing_order

    records, hashes, active = {}, {}, set()
    for raw in documents["entity_state_history"]:
        location = locations["entity_state_history", raw["_id"]]
        _validate_faction_position_version(raw, location, format_version)
        try:
            row = parse_faction_fact_record(raw)
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "势力记录的格式、身份或字段不正确") from exc
        identity = row["history_id"]
        records[identity] = row
        hashes[identity] = canonical_request_hash({k: v for k, v in row.items() if k != "validity"})
        _validate_character_fact_source(row, location, by_id, summary, relation_fact=True)
        target = by_id["factions"].get(ObjectId(row["entity_id"]))
        for field, validity in row["validity"].items():
            if validity["state"] != "active":
                continue
            key = (ObjectId(row["entity_id"]), field, row["position"]["intent"], ObjectId(row["position"]["target_id"]))
            if key in active:
                raise ArchiveValidationError(location, "同一势力字段位置不能有两条活动记录")
            active.add(key)
            if (target is not None and row["position"]["intent"] == "book_start"
                    and field in FACTION_FACT_PROFILE_FIELDS
                    and (target.get(field) != row["after"][field]
                         or field == "is_public" and type(target.get(field)) is not bool)):
                raise ArchiveValidationError(location, "书初势力原文必须与主档镜像一致")

    receipts, dispositions, bases = set(), {}, []
    for raw in documents["chapter_record_confirmation_receipts"]:
        location = locations["chapter_record_confirmation_receipts", raw["_id"]]
        _validate_faction_position_version(raw, location, format_version)
        try:
            json.dumps(raw["request"], allow_nan=False)
            json.dumps(raw["result"], allow_nan=False)
            result = validate_faction_fact_receipt(raw)
            basis = FactionFactBasisV1.model_validate(raw["request"]["data"]["basis"]).model_dump(mode="json", exclude_unset=True)
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "势力回执须保留原请求、首次结果和正确摘要") from exc
        _validate_character_fact_source(raw, location, by_id, summary, relation_fact=True)
        row = result["record"]
        if row is not None:
            # 与 v10 相同，仅比较副本统一顶层 BSON 身份，保留原请求和结果中的写法。
            original = {**row, **{key: str(ObjectId(row[key])) for key in ("history_id", "novel_id", "entity_id")}}
            identity = original["history_id"]
            if (identity in receipts or identity not in records
                    or canonical_request_hash({k: v for k, v in original.items() if k != "validity"}) != hashes[identity]):
                raise ArchiveValidationError(location, "势力记录必须对应唯一首次成功结果，原值和来源不能改写")
            receipts.add(identity)
        for change in result["validity_changes"]:
            identity, field = change["history_id"], change["field"]
            old = records.get(identity)
            if ((identity, field) in dispositions or old is None or old["entity_id"] != result["entity_id"]
                    or old["after_version"] >= result["after_version"] or old["validity"].get(field) != change["after"]):
                raise ArchiveValidationError(location, "势力处置须对应更早同势力字段及当前终态")
            dispositions[identity, field] = (result["after_version"], change["after"])
        bases.append((basis, location))
        summary["receipts"] += 1
        summary["unique_keys"] += 1
    if receipts != records.keys():
        raise ArchiveValidationError("collections/entity_state_history.jsonl", "势力记录缺少唯一首次成功回执")
    for identity, row in records.items():
        location = locations["entity_state_history", ObjectId(identity)]
        for field, validity in row["validity"].items():
            if (validity["state"] != "active") != ((identity, field) in dispositions):
                raise ArchiveValidationError(location, "势力字段替代或作废须保留完整回执")
        for field in row["after"]:
            previous = row["previous"].get(field)
            references = [*row["resolves"].get(field, []), *([row["replaces"][field]] if field in row["replaces"] else []), *([previous] if previous else [])]
            for ref in references:
                old = records.get(ref)
                if old is None or old["entity_id"] != row["entity_id"] or old["after_version"] >= row["after_version"] or field not in old["after"]:
                    raise ArchiveValidationError(location, "势力来源和处置只能引用更早同势力同字段")
            if previous and records[previous]["after"][field] != row["before"]["values"][field]:
                raise ArchiveValidationError(location, "势力前值与原记录不一致")

    legacy_identities, reference_identities = {}, {}
    for basis, location in bases:
        target = basis["target"]
        target_version = target.get("version", 0)
        expected_history = {identity for identity, row in records.items() if row["entity_id"] == target["entity_id"] and row["after_version"] <= target_version}
        if len(basis["reads"]) != 1:
            raise ArchiveValidationError(location, "势力准备必须保留唯一目标读取")
        read = basis["reads"][0]
        if {row["history_id"] for row in read["history"]} != expected_history:
            raise ArchiveValidationError(location, "势力原读取须保留当时全部记录，不能漏读后假称未认领")
        snapshots = []
        for observation in read["history"]:
            identity = observation["history_id"]
            original = records[identity]
            if (observation["entity_id"] != original["entity_id"] or observation["immutable_fingerprint"] != hashes[identity]
                    or observation["validity"].keys() != original["validity"].keys()):
                raise ArchiveValidationError(location, "势力原读取的身份、字段或记录摘要不一致")
            for field, validity in observation["validity"].items():
                change = dispositions.get((identity, field))
                expected = change[1] if change and change[0] <= target_version else {"state": "active"}
                if validity != expected:
                    raise ArchiveValidationError(location, "势力原读取不能伪造当时有效状态")
            snapshots.append({**original, "validity": observation["validity"]})
        for snapshot in [*basis["targets"], *basis["field_sources"]]:
            if canonical_request_hash({k: v for k, v in snapshot.items() if k != "validity"}) != hashes.get(snapshot["history_id"]):
                raise ArchiveValidationError(location, "势力原值和处置快照不得改写")
        directories = {kind: {} for kind in PARENTS}
        seen = set()
        for kind, rows in directories.items():
            for entry in read["directory"]:
                if entry["resource_type"] != kind:
                    continue
                identity, parent_id = ObjectId(entry["id"]), ObjectId(entry["parent_id"])
                parent = PARENTS[kind]
                if (kind, identity) in seen or (parent == "novel" and parent_id != ObjectId(read["novel_id"])) or (parent != "novel" and parent_id not in directories[parent]):
                    raise ArchiveValidationError(location, "势力冻结目录的身份或完整父链不一致")
                seen.add((kind, identity))
                ancestors = {} if parent == "novel" else {k: v for k, v in directories[parent][parent_id].items() if k.endswith("_id")}
                rows[identity] = {**ancestors, f"{parent}_id": parent_id, "order_index": entry["order_index"]}
        position = read["position"]
        if position["target_type"] == "novel":
            order = () if ObjectId(position["target_id"]) == ObjectId(read["novel_id"]) else None
        else:
            anchored = directories[position["target_type"]].get(ObjectId(position["target_id"]))
            order = writing_order(position["target_type"], anchored, directories) if anchored else None
        if order is None or list(order) != position["order"]:
            raise ArchiveValidationError(location, "势力原读取顺序与冻结目录不同")
        expected_position = {**basis["position"], "version": 1}
        if basis["kind"] == "change" and basis["operation"] != "void":
            expected_position["intent"] = "chapter_before"
        anchor_kind = basis["position"]["target_type"]
        missing_anchor = (basis["operation"] == "void" and anchor_kind in {"chapter", "volume"}
                          and ObjectId(basis["position"]["target_id"]) not in directories[anchor_kind])
        if missing_anchor:
            expected_position = {"version": 1, "intent": "book_start", "target_type": "novel", "target_id": read["novel_id"]}
        if {k: v for k, v in position.items() if k != "order"} != expected_position:
            raise ArchiveValidationError(location, "势力原读取必须对应准备位置，变化读取章前")
        if anchor_kind in {"chapter", "volume"} and not missing_anchor:
            for ref in basis["protected_sources"][1:]:
                kind = ref["resource_type"]
                frozen = directories[kind].get(ObjectId(ref["id"]))
                if frozen is None or frozen[f"{PARENTS[kind]}_id"] != ObjectId(ref["parent_id"]):
                    raise ArchiveValidationError(location, "势力预览来源父链必须等于原读取目录")
        observations = {(row["chapter_id"], row["revision_id"]): row for row in read["sources"]}
        needed = {(row["source"]["evidence"]["chapter_id"], row["source"]["evidence"]["revision_id"]) for row in snapshots if row["source"]["kind"] == "chapter"}
        if set(observations) != needed or len(observations) != len(read["sources"]):
            raise ArchiveValidationError(location, "势力原读取须保留全部且唯一的正文来源观察")
        for source in observations.values():
            if source["revision_valid"]:
                revision = by_id["chapter_revisions"].get(ObjectId(source["revision_id"]))
                if (revision is None or revision["chapter_id"] != ObjectId(source["chapter_id"])
                        or revision["version"] != source["revision_version"] or revision["content_hash"] != source["revision_hash"]):
                    raise ArchiveValidationError(location, "势力原有效来源须保留原章修订、版本和正文摘要")
        source_checks = {}
        for row in snapshots:
            evidence = row["source"].get("evidence")
            observed = observations[evidence["chapter_id"], evidence["revision_id"]] if evidence else None
            source_checks[row["history_id"]] = bool(evidence is None or observed["parents_active"] and observed["revision_valid"]
                and observed["content_hash"] == evidence["content_hash"] == observed["revision_hash"] and observed["revision_version"] == evidence["version"])
        if target["kind"] == "existing":
            try:
                resolved = evaluate_faction_facts({**target, "_id": ObjectId(target["entity_id"]), "novel_id": ObjectId(target["novel_id"])}, snapshots, position, directories, source_checks)
            except DomainApiError as exc:
                raise ArchiveValidationError(location, "势力冻结原读取无法按原位置计算") from exc
            fields = set(basis["fields"])
            before = {key: {k: v for k, v in resolved[key].items() if k in fields} for key in ("values", "unknown")}
            previous = {field: resolved["origins"].get(field) for field in fields}
            blockers = {field: value for field, value in resolved["blockers"].items() if field in fields}
            if basis["before"] != before or basis["previous"] != previous or basis["blockers"] != blockers:
                raise ArchiveValidationError(location, "势力保存前值和阻断必须等于当时完整读取")
        for legacy in basis["legacy_sources"]:
            if legacy["kind"] == "profile":
                continue
            identity, volume_id = ObjectId(legacy["state_id"]), ObjectId(legacy["volume_id"])
            binding = (legacy["faction_id"], volume_id)
            if legacy_identities.setdefault(identity, binding) != binding:
                raise ArchiveValidationError(location, "势力旧卷状态不能重绑原势力或卷")
            state = _reference(identity, by_id["faction_volume_states"], location, summary, physical=True, historical=True)
            if state is not None and (state["faction_id"] != binding[0] or state["volume_id"] != volume_id or type(state.get("version")) is not int or state["version"] < legacy["version"]):
                raise ArchiveValidationError(location, "势力旧卷状态的身份、归属或版本与原预览不同")
            volume = _reference(volume_id, by_id["volumes"], location, summary, physical=True, historical=True)
            if volume is not None and legacy["volume"] is not None and (type(volume.get("version")) is not int or volume["version"] < legacy["volume"]["version"]):
                raise ArchiveValidationError(location, "势力旧卷资料不能倒退原版本")
        for observation in basis["reference_reads"]:
            ref = observation["reference"]
            if ref["entity_type"] not in {"character_volume_state", "faction_volume_state"}:
                continue
            name = ref["entity_type"] + "s"
            identity = ObjectId(observation["entity_id"])
            if identity != ObjectId(ref["entity_id"]):
                raise ArchiveValidationError(location, "势力人工卷状态引用的物理身份不一致")
            key = (name, identity)
            if reference_identities.setdefault(key, ref["entity_id"]) != ref["entity_id"]:
                raise ArchiveValidationError(location, "势力人工历史引用不能重绑")
            actual = _reference(identity, by_id[name], location, summary, physical=True, historical=True)
            if actual is not None and (type(actual.get("version")) is not int or actual["version"] < observation["version"]):
                raise ArchiveValidationError(location, "势力人工历史引用版本不能倒退")


def _validate_v9_history_identities(documents: dict, by_id: dict, by_business: dict, locations: dict,
                                    summary: dict, sequence_minimum: dict, required_sequences: set, *, include_item_facts: bool = False, include_faction_facts: bool = False) -> None:
    """检查新旧记录是否重用了同一版本，或把业务编号换绑到另一个对象。

    Args:
        documents: 已由各自严格合同验证的全部文档。
        by_id: 按集合区分的现存物理身份。
        by_business: 现存稳定业务身份。
        locations: 原文档位置。
        summary: 历史身份引用统计。
        sequence_minimum: 含已删除身份的序列下限。
        required_sequences: 必须保留的序列类型。
        include_item_facts: v10 才增加物品身份检查，保持旧包的校验摘要不变。
        include_faction_facts: 只在 v11/v13/v14 检查势力和人工引用身份。
    Returns:
        无；跨分支重用版本或重绑身份时拒绝。
    """
    versions, physical, business, relation_endpoints = set(), {}, {}, {}
    bindings = []
    for row in documents["entity_state_history"]:
        location = locations["entity_state_history", row["_id"]]
        key = (row["entity_type"], row["entity_id"], row["after_version"])
        if key in versions:
            raise ArchiveValidationError(location, "新旧历史不能占用同一实体的同一动作版本")
        versions.add(key)
    for raw in documents["chapter_record_confirmation_receipts"]:
        location = locations["chapter_record_confirmation_receipts", raw["_id"]]
        schema, result = raw.get("schema_id"), raw["result"]
        if schema in {"character.fact.receipt", "character_relation.fact.receipt"} or include_item_facts and schema == "item.fact.receipt" or include_faction_facts and schema == "faction.fact.receipt":
            kind = {"character.fact.receipt": "character", "character_relation.fact.receipt": "character_relation", "item.fact.receipt": "item", "faction.fact.receipt": "faction"}[schema]
            if raw["operation"] == "void":
                key = (kind, ObjectId(result["entity_id"]), result["after_version"])
                if key in versions:
                    raise ArchiveValidationError(location, "作废也占用一次真实版本，不能与新旧确认或另一作废重用")
                versions.add(key)
            if kind == "item":
                bindings.append(("items", result["entity_id"], result["item_id"], result["after_version"], location))
                basis = raw["request"]["data"]["basis"]
                for reference in [*basis["read"]["references"], *basis["preview_references"]]:
                    if reference["entity_id"] is not None:
                        bindings.append((f"{reference['resource_type']}s", reference["entity_id"], reference["business_id"], reference["version"], location))
                continue
            if kind == "faction":
                bindings.append(("factions", result["entity_id"], result["faction_id"], result["after_version"], location))
                for reference in raw["request"]["data"]["basis"]["reference_reads"]:
                    if reference["reference"]["entity_type"] in {"character_volume_state", "faction_volume_state"}:
                        continue
                    name = next(name for name, (_, entity, _) in BUSINESS_IDS.items() if entity == reference["reference"]["entity_type"])
                    bindings.append((name, reference["entity_id"], reference["reference"]["entity_id"], reference["version"], location))
                continue
            if kind == "character":
                bindings.append(("characters", result["entity_id"], result["character_id"], result["after_version"], location))
                continue
            version = result["after_version"]
            endpoints = [(result[f"{side}_character_entity_id"], result[f"{side}_character_id"],
                          raw["request"]["data"]["basis"]["target"][f"{side}_character"]["version"]) for side in ("source", "target")]
        elif include_item_facts and schema is None and raw["operation"] == "confirm_item_owner":
            history = result["history"]
            bindings.append(("items", history["entity_id"], result["item_id"], result["item_version"], location))
            data = raw["request"]["data"]
            bindings.extend(("characters", ref["id"], data[field], ref["version"], location)
                            for field, ref in zip(("from_character_id", "to_character_id"), data["basis"]["source_refs"][1:]))
            continue
        elif schema is None and raw["operation"] == "confirm_character_relation_state":
            # 旧 D 同值回执只有观察；它不新增历史，也不占用第二个动作版本。
            version = result["relation_version"]
            endpoints = [(ref["id"], result[f"{side}_character_id"], ref["version"])
                         for side, ref in zip(("source", "target"), raw["request"]["data"]["basis"]["source_refs"][1:])]
        else:
            continue
        relation_id = ObjectId(result["entity_id"])
        identity = tuple((ObjectId(physical_id), business_id) for physical_id, business_id, _ in endpoints)
        if relation_endpoints.setdefault(relation_id, identity) != identity:
            raise ArchiveValidationError(location, "新旧关系历史不能重绑任一端点的业务或物理身份")
        target = by_id["character_relations"].get(relation_id)
        if target is not None and any(target[f"{side}_character_id"] != endpoint[1] for side, endpoint in zip(("source", "target"), endpoints)):
            raise ArchiveValidationError(location, "现存关系不能改绑原历史固定端点")
        bindings.append(("character_relations", relation_id, result["relation_id"], version, location))
        bindings.extend(("characters", identity, business_id, version, location) for identity, business_id, version in endpoints)
    for name, entity_id, business_id, version, location in bindings:
        entity_id = ObjectId(entity_id)
        field, entity, prefix = BUSINESS_IDS[name]
        if (physical.setdefault((name, entity_id), business_id) != business_id
                or business.setdefault((name, business_id), entity_id) != entity_id):
            raise ArchiveValidationError(location, "同类实体的历史业务身份与物理身份不能重绑")
        target = _reference(entity_id, by_id[name], location, summary, physical=True, historical=True)
        known = by_business[name].get(business_id)
        if (target is not None and (target[field] != business_id or type(target.get("version")) is not int or target["version"] < version)
                or known is not None and known["_id"] != entity_id):
            raise ArchiveValidationError(location, "历史身份及版本与现存实体不一致")
        sequence_minimum[entity] = max(sequence_minimum[entity], _business_number(business_id, prefix, location))
        required_sequences.add(entity)


def validate_documents(documents: dict[str, list[dict]], novel_id: ObjectId, *, format_version: int = 5) -> dict:
    """只读验证包内原始文档的身份、父链、引用和已知唯一键。

    Args:
        documents: 固定白名单中各集合的原始 BSON 文档，顺序对应 JSONL 行号。
        novel_id: manifest 声明的作品 ObjectId。
        format_version: 清单版本；旧调用默认保留 v5 的章后记录规则。

    Returns:
        ID、父链、引用及五层数量摘要；不代表能安全导入任意数据库。
    """
    if type(format_version) is not int or format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise ArchiveValidationError("format_version", "仅支持备份格式 1–14")
    if set(documents) not in (set(COLLECTIONS), set(REVISION_COLLECTIONS), set(FORESHADOWING_COLLECTIONS), set(CHAPTER_RECORD_COLLECTIONS), set(CHARACTER_BATCH_COLLECTIONS), set(FACTION_BATCH_COLLECTIONS)):
        raise ArchiveValidationError("collections", "集合必须与当前版本白名单完全一致")
    if "character_creation_batch_receipts" in documents and format_version not in CHARACTER_BATCH_FORMAT_VERSIONS:
        raise ArchiveValidationError("collections", "人物整批保存回执需要 v12、v13 或 v14 备份格式")
    if "faction_creation_batch_receipts" in documents and format_version != FACTION_VOLUME_START_FORMAT_VERSION:
        raise ArchiveValidationError("collections", "势力整批保存回执需要 v14 备份格式")
    if format_version in (FACTION_FACT_FORMAT_VERSION, *CHARACTER_BATCH_FORMAT_VERSIONS):
        names = CHAPTER_RECORD_COLLECTIONS if format_version == FACTION_FACT_FORMAT_VERSION else CHARACTER_BATCH_COLLECTIONS
        if format_version == FACTION_VOLUME_START_FORMAT_VERSION:
            names = FACTION_BATCH_COLLECTIONS
        if set(documents) != set(names):
            raise ArchiveValidationError("collections", "集合必须与本版本白名单完全一致")
    if not isinstance(novel_id, ObjectId) or len(documents["novels"]) != 1:
        raise ArchiveValidationError("collections/novels.jsonl", "必须恰好包含 manifest 指定的一部作品")
    summary = {
        "physical_ids": 0, "business_ids": 0, "parent_links": 0, "references": 0,
        "unique_keys": 0, "historical_references_unresolved": 0,
        "receipts": 0, "sequences": 0,
        "hierarchy_totals": {name: len(documents[name]) for name in CORE_COLLECTIONS[:5]},
    }
    by_id: dict[str, dict] = {name: {} for name in documents}
    by_business: dict[str, dict] = {name: {} for name in BUSINESS_IDS}
    sequence_minimum = {entity: 0 for _, entity, _ in BUSINESS_IDS.values()}
    required_sequences = set()
    locations: dict[tuple[str, ObjectId], str] = {}
    unique_keys: dict[tuple, str] = {}

    for name, rows in documents.items():
        for line, document in enumerate(rows, 1):
            location = f"collections/{name}.jsonl:{line}"
            if not isinstance(document, dict) or not isinstance(document.get("_id"), ObjectId):
                raise ArchiveValidationError(location, "原始文档 _id 必须是 BSON ObjectId")
            identity = document["_id"]
            if identity in by_id[name]:
                raise ArchiveValidationError(f"{location}._id", "集合内物理 ID 重复")
            if name == "novels":
                if identity != novel_id:
                    raise ArchiveValidationError(f"{location}._id", "作品与 manifest 不一致")
            elif document.get("novel_id") != novel_id:
                raise ArchiveValidationError(f"{location}.novel_id", "记录缺少 BSON novel_id 或属于其他作品")
            if name in (*CORE_COLLECTIONS, "foreshadowings") and type(document.get("is_deleted")) is not bool:
                raise ArchiveValidationError(f"{location}.is_deleted", "核心记录必须明确标记是否已删除")
            by_id[name][identity] = document
            locations[name, identity] = location
            summary["physical_ids"] += 1
            if name in BUSINESS_IDS:
                field, entity, prefix = BUSINESS_IDS[name]
                business_id = document.get(field)
                number = _business_number(business_id, prefix, f"{location}.{field}")
                if business_id in by_business[name]:
                    raise ArchiveValidationError(f"{location}.{field}", "业务 ID 重复，包括已删除记录")
                by_business[name][business_id] = document
                sequence_minimum[entity] = max(sequence_minimum[entity], number)
                required_sequences.add(entity)
                summary["business_ids"] += 1
            if name in ("character_volume_states", "faction_volume_states"):
                if document.get("state_id") != identity:
                    raise ArchiveValidationError(f"{location}.state_id", "state_id 必须与 BSON _id 相同")
                if name == "faction_volume_states" and ("content_contract" in document or "plan_creation_result" in document):
                    _validate_faction_plan(document, location, format_version=format_version)
                summary["business_ids"] += 1

            # 固定列举当前 indexes.py 中的标量唯一键，不加载索引模块或重写业务模型。
            keys: list[tuple[str, ...]] = []
            if name == "foreshadowing_creation_receipts":
                for field in ("idempotency_key_hash", "request_hash"):
                    if not isinstance(document.get(field), str) or re.fullmatch(r"[0-9a-f]{64}", document[field]) is None:
                        raise ArchiveValidationError(f"{location}.{field}", "创建回执需要 SHA-256 摘要")
                keys.append(("idempotency_key_hash",))
            if name == "chapter_revisions":
                if not isinstance(document.get("chapter_id"), ObjectId) or not isinstance(document.get("version"), int) or isinstance(document["version"], bool) or document["version"] < 1:
                    raise ArchiveValidationError(location, "修订需要 BSON 章节 ID 和正整数版本")
                keys.append(("chapter_id", "version"))
            parent = {"arcs": "volume_id", "scenes": "arc_id", "chapters": "scene_id"}.get(name)
            if name != "volumes" and name in CORE_COLLECTIONS and isinstance(document.get("creation_idempotency_key_hash"), str):
                keys.append(((parent,) if parent else ()) + ("creation_idempotency_key_hash",))
            if document.get("is_deleted") is False:
                if name in ("volumes", "items"):
                    keys.append(("order_index",))
                if parent:
                    keys.append((parent, "order_index"))
                if name in ("characters", "world_rules", "items"):
                    keys.append(("normalized_name",))
                if name == "world_rules":
                    keys.append(("category", "order_index"))
                if name == "locations":
                    keys.extend((("parent_location_id", "normalized_name"), ("parent_location_id", "order_index")))
                if name == "factions" and document.get("active_status") == "active":
                    keys.append(("level_type", "volume_id", "normalized_name"))
                    if document.get("level_type") == "core":
                        keys.append(("normalized_name",))
                if name in ("character_volume_states", "faction_volume_states"):
                    keys.append(("volume_id", "character_id" if name.startswith("character") else "faction_id"))
                if document.get("is_active") is True:
                    if name in ("character_relations", "faction_relations"):
                        kind = "character" if name.startswith("character") else "faction"
                        keys.append((f"normalized_source_{kind}_id", f"normalized_target_{kind}_id", "relation_type"))
                    if name == "character_faction_bindings":
                        keys.append(("character_id", "faction_id", "membership_type"))
                        if document.get("membership_type") == "primary":
                            keys.append(("character_id",))
            if name in ("factions", "character_relations", "faction_relations"):
                prefix = "core_batch" if name == "factions" else "batch"
                if document.get(f"{prefix}_command_marker") is True:
                    keys.append((f"{prefix}_idempotency_key_hash",))
                if all(isinstance(document.get(f"{prefix}_{field}"), str) for field in ("idempotency_key_hash", "local_ref")):
                    keys.append((f"{prefix}_idempotency_key_hash", f"{prefix}_local_ref"))
            if name == "character_faction_bindings" and isinstance(document.get("primary_switch_idempotency_key_hash"), str):
                keys.append(("primary_switch_idempotency_key_hash",))
            if name in ("character_volume_states", "faction_volume_states") and isinstance(document.get("initialization_idempotency_key_hash"), str):
                keys.append(("initialization_idempotency_key_hash", "character_id" if name.startswith("character") else "faction_id"))
            if name in RECEIPT_COLLECTIONS:
                if name in ("volume_command_receipts", "writing_confirmation_receipts") and not isinstance(document.get("operation"), str):
                    raise ArchiveValidationError(f"{location}.operation", "回执必须包含命令名称")
                for field in ("idempotency_key_hash", "request_hash"):
                    value = document.get(field)
                    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                        raise ArchiveValidationError(f"{location}.{field}", "成功回执必须保存 SHA-256 摘要")
                keys.append(("operation", "idempotency_key_hash") if name == "writing_confirmation_receipts" else ("idempotency_key_hash",))
            if name == "id_sequences":
                keys.append(("entity_type",))
            for fields in keys:
                values = tuple(document.get(field) for field in fields)
                if any(value is not None and not isinstance(value, (str, int, ObjectId)) for value in values):
                    raise ArchiveValidationError(location, f"唯一键 {', '.join(fields)} 必须使用标量")
                key = (name, fields, values)
                if key in unique_keys:
                    raise ArchiveValidationError(location, f"唯一键 {', '.join(fields)} 重复；首次位于 {unique_keys[key]}")
                unique_keys[key] = location
                summary["unique_keys"] += 1

    revision_parents = {}
    revision_versions = {(row["chapter_id"], row["version"]) for row in documents.get("chapter_revisions", [])}
    last_revision = {}
    for row in sorted(documents.get("chapter_revisions", []), key=lambda row: row["version"]):
        revision_parents[row["_id"]] = last_revision.get(row["chapter_id"])
        last_revision[row["chapter_id"]] = row["version"]
    for name, rows in documents.items():
        for document in rows:
            location = locations[name, document["_id"]]
            if name == "foreshadowings":
                _validate_foreshadowing(document, novel_id, location, by_id, summary)
            if name == "chapter_revisions":
                chapter = _reference(document.get("chapter_id"), by_id["chapters"], f"{location}.chapter_id", summary, physical=True)
                for field in ("novel_id", "volume_id", "arc_id", "scene_id"):
                    if document.get(field) != chapter.get(field):
                        raise ArchiveValidationError(f"{location}.{field}", "修订与当前章节父链不一致")
                version, parent = document.get("version"), document.get("parent_version")
                current_version = chapter.get("version")
                if not isinstance(current_version, int) or isinstance(current_version, bool) or not 1 <= version <= current_version:
                    raise ArchiveValidationError(f"{location}.version", "修订版本必须为不超过当前章节的正整数")
                previous = revision_parents[document["_id"]]
                if "parent_version" not in document or parent != previous or (parent is not None and (not isinstance(parent, int) or isinstance(parent, bool))):
                    raise ArchiveValidationError(f"{location}.parent_version", "修订必须连向同章前一份历史")
                if (any(not isinstance(document.get(field), str) for field in ("title", "summary", "content"))
                        or not isinstance(document.get("planning"), dict)
                        or document.get("source") not in {"baseline", "create", "edit", "writing", "assistant", "restore"}
                        or not isinstance(document.get("saved_at"), datetime)):
                    raise ArchiveValidationError(location, "修订内容、来源或时间无效")
                if not 1 <= len(document["title"]) <= 120 or len(document["summary"]) > 2000 or len(document["content"]) > 100000:
                    raise ArchiveValidationError(location, "修订标题、摘要或正文超过章节大小限制")
                if document.get("content_hash") != hashlib.sha256(document["content"].encode("utf-8")).hexdigest():
                    raise ArchiveValidationError(f"{location}.content_hash", "修订正文哈希不一致")
                restored_from = document.get("restored_from_version")
                if document["source"] == "restore":
                    if (not isinstance(restored_from, int) or isinstance(restored_from, bool)
                            or not 1 <= restored_from < version
                            or (document["chapter_id"], restored_from) not in revision_versions):
                        raise ArchiveValidationError(f"{location}.restored_from_version", "恢复来源必须是同章已有旧稿")
                elif restored_from is not None:
                    raise ArchiveValidationError(f"{location}.restored_from_version", "只有旧稿恢复记录能带恢复来源")
                pov = document["planning"].get("pov_character_id")
                if pov is not None:
                    _reference(pov, by_business["characters"], f"{location}.planning.pov_character_id", summary, historical=True, business_prefix="char")
                    # 旧稿人物即使已删除也占过号，恢复不能把这个身份分给新人。
                    number = _business_number(pov, "char", f"{location}.planning.pov_character_id")
                    sequence_minimum["character"] = max(sequence_minimum["character"], number)
                    required_sequences.add("character")
            if name in CORE_COLLECTIONS[1:5]:
                ancestors = {"volume_id": "volumes", "arc_id": "arcs", "scene_id": "scenes"}
                depth = CORE_COLLECTIONS.index(name) - 1
                for field, target_name in list(ancestors.items())[:depth]:
                    target = _reference(document.get(field), by_id[target_name], f"{location}.{field}", summary, physical=True)
                    for ancestor in list(ancestors)[:list(ancestors).index(field)]:
                        if target.get(ancestor) != document.get(ancestor):
                            raise ArchiveValidationError(f"{location}.{field}", "父级与记录保存的祖先链不一致")
                    summary["parent_links"] += 1
                summary["parent_links"] += 1  # novel_id 已在第一轮核对。

            references: list[tuple[str, Any, str, bool, bool]] = []
            if name == "volumes":
                if not isinstance(document.get("location_ids", []), list):
                    raise ArchiveValidationError(f"{location}.location_ids", "引用必须是数组")
                references.extend(("location_ids", identity, "locations", False, False) for identity in document.get("location_ids", []))
            if name in ("arcs", "scenes", "chapters"):
                planning = document.get("planning", {})
                if not isinstance(planning, dict):
                    raise ArchiveValidationError(f"{location}.planning", "规划必须是对象")
                for field, target in (("character_ids", "characters"), ("faction_ids", "factions"), ("location_ids", "locations"), ("item_ids", "items"), ("rule_ids", "world_rules")):
                    values = planning.get(field, [])
                    if not isinstance(values, list):
                        raise ArchiveValidationError(f"{location}.planning.{field}", "引用必须是数组")
                    references.extend((f"planning.{field}", value, target, False, False) for value in values)
                if planning.get("pov_character_id") is not None:
                    references.append(("planning.pov_character_id", planning["pov_character_id"], "characters", False, False))
            if name in ("character_relations", "faction_relations"):
                kind = "character" if name.startswith("character") else "faction"
                references.extend((f"{side}_{kind}_id", document.get(f"{side}_{kind}_id"), f"{kind}s", False, False) for side in ("source", "target"))
            if name == "character_faction_bindings":
                references.extend((f"{kind}_id", document.get(f"{kind}_id"), f"{kind}s", False, False) for kind in ("character", "faction"))
            if name == "factions":
                level = document.get("level_type")
                if level not in ("core", "volume", "local"):
                    raise ArchiveValidationError(f"{location}.level_type", "势力层级必须为 core、volume 或 local")
                if level == "core" and document.get("volume_id") is not None:
                    raise ArchiveValidationError(f"{location}.volume_id", "核心势力不能归属某一卷")
                if level != "core":
                    references.append(("volume_id", document.get("volume_id"), "volumes", True, False))
                if document.get("parent_faction_id") is not None:
                    references.append(("parent_faction_id", document["parent_faction_id"], "factions", False, False))
            if name == "locations":
                if document.get("parent_location_id") is not None:
                    references.append(("parent_location_id", document["parent_location_id"], "locations", False, False))
                if document.get("detached_parent_location_id") is not None:
                    references.append(("detached_parent_location_id", document["detached_parent_location_id"], "locations", False, True))
                for field, target in (("associated_faction_ids", "factions"), ("applicable_rule_ids", "world_rules")):
                    values = document.get(field, [])
                    if not isinstance(values, list):
                        raise ArchiveValidationError(f"{location}.{field}", "引用必须是数组")
                    references.extend((field, value, target, False, document["is_deleted"]) for value in values)
            if name == "items":
                for field, target in (("owner_character_id", "characters"), ("controlling_faction_id", "factions"), ("current_location_id", "locations")):
                    if document.get(field) is not None:
                        references.append((field, document[field], target, False, document["is_deleted"]))
            if name == "world_rules":
                scope = document.get("scope_type")
                values = document.get("scope_entity_ids", [])
                if scope not in ("global", "character", "faction", "location") or not isinstance(values, list):
                    raise ArchiveValidationError(f"{location}.scope_entity_ids", "规则作用域或引用数组错误")
                if scope == "global" and values:
                    raise ArchiveValidationError(f"{location}.scope_entity_ids", "全局规则不能携带实体引用")
                if scope != "global":
                    references.extend(("scope_entity_ids", value, f"{scope}s", False, document["is_deleted"]) for value in values)
            if name in ("character_volume_states", "faction_volume_states"):
                kind = "character" if name.startswith("character") else "faction"
                references.extend((("volume_id", document.get("volume_id"), "volumes", True, False), (f"{kind}_id", document.get(f"{kind}_id"), f"{kind}s", False, False)))
                if document.get("source_state_id") is not None:
                    source = _reference(document["source_state_id"], by_id[name], f"{location}.source_state_id", summary, physical=True)
                    if source.get(f"{kind}_id") != document.get(f"{kind}_id") or source.get("volume_id") == document.get("volume_id"):
                        raise ArchiveValidationError(f"{location}.source_state_id", "来源状态必须属于同一实体的另一卷")
                if name == "character_volume_states":
                    values = document.get("relationship_focus_ids", [])
                    if not isinstance(values, list):
                        raise ArchiveValidationError(f"{location}.relationship_focus_ids", "关系引用必须是数组")
                    for identity in values:
                        relation = _reference(identity, by_business["character_relations"], f"{location}.relationship_focus_ids", summary)
                        if document.get("character_id") not in (relation.get("source_character_id"), relation.get("target_character_id")):
                            raise ArchiveValidationError(f"{location}.relationship_focus_ids", "重点关系不涉及当前角色")
            for field, value, target_name, physical, historical in references:
                target = _reference(value, by_id[target_name] if physical else by_business[target_name], f"{location}.{field}", summary, physical=physical, historical=historical, business_prefix=None if physical else BUSINESS_IDS[target_name][2])
                if not physical:
                    _, entity, prefix = BUSINESS_IDS[target_name]
                    sequence_minimum[entity] = max(sequence_minimum[entity], _business_number(value, prefix, f"{location}.{field}"))
                    required_sequences.add(entity)
                if name == "factions" and field == "parent_faction_id" and target is not None:
                    if document["level_type"] == "core" and target.get("level_type") != "core":
                        raise ArchiveValidationError(f"{location}.{field}", "核心势力的父级也必须是核心势力")
                    if target.get("volume_id") not in (None, document.get("volume_id")):
                        raise ArchiveValidationError(f"{location}.{field}", "父势力不属于同一卷")
                if target_name == "factions" and target is not None and name in ("arcs", "scenes", "faction_volume_states"):
                    if target.get("volume_id") not in (None, document.get("volume_id")):
                        raise ArchiveValidationError(f"{location}.{field}", "局部势力不属于当前卷")

    # 只沿实际父字段走一遍；已完成的路径不重复遍历，长父链不会平方增长。
    for name, field, business in (("locations", "parent_location_id", True), ("factions", "parent_faction_id", True), ("character_volume_states", "source_state_id", False), ("faction_volume_states", "source_state_id", False)):
        targets = by_business[name] if business else by_id[name]
        completed = set()
        for identity in targets:
            path = set()
            cursor = identity
            while cursor is not None and cursor not in completed:
                if cursor in path:
                    raise ArchiveValidationError(f"{locations[name, targets[cursor]['_id']]}.{field}", "父级或来源状态形成循环")
                path.add(cursor)
                cursor = targets[cursor].get(field)
            completed.update(path)

    for document in documents.get("foreshadowing_creation_receipts", []):
        location = locations["foreshadowing_creation_receipts", document["_id"]]
        result = document.get("result")
        _validate_foreshadowing(result, novel_id, f"{location}.result", by_id, summary, historical=True)
        if (result["version"] != 1 or result["status"] != "planned" or result["is_deleted"]
                or result["planted_evidence"] is not None or result["resolved_evidence"] is not None
                or result.get("planted_needs_review") is not False or result.get("resolved_needs_review") is not False):
            raise ArchiveValidationError(f"{location}.result", "创建快照必须保留原始未埋设计划")
        # 即使正式伏笔已硬删，成功快照也占用原业务号，不能分给后来创建的伏笔。
        number = _business_number(result["foreshadowing_id"], "fo", f"{location}.result.foreshadowing_id")
        sequence_minimum["foreshadowing"] = max(sequence_minimum["foreshadowing"], number)
        required_sequences.add("foreshadowing")
        from backend.db.write_contracts import canonical_request_hash
        plan = {name: result[name] for name in ("title", "content", "target_effect", "planting_position", "resolution_position")}
        if canonical_request_hash({"novel_id": str(novel_id), "plan": plan}) != document["request_hash"]:
            raise ArchiveValidationError(f"{location}.request_hash", "创建快照与原请求摘要不一致")
        summary["receipts"] += 1

    for name in RECEIPT_COLLECTIONS:
        for document in documents[name]:
            location = locations[name, document["_id"]]
            operation = document.get("operation")
            rows = None
            mapping = None
            identity_field = "_id"
            volume_entity_receipt = False
            mapping_field = "candidate_ref_map"
            if name.endswith("volume_state_initialization_receipts"):
                for field in ("source_volume_id", "target_volume_id"):
                    _reference(document.get(field), by_id["volumes"], f"{location}.{field}", summary, physical=True)
                rows, identity_field = document.get("states"), "state_id"
                identities = _snapshot_rows(rows, f"{location}.states", novel_id, identity_field)
                if document.get("state_ids") != identities or any(not isinstance(value, ObjectId) for value in identities):
                    raise ArchiveValidationError(f"{location}.state_ids", "初始化回执状态 ID 与快照不一致")
                for row in rows:
                    if row.get("_id") != row["state_id"] or row.get("volume_id") != document["target_volume_id"]:
                        raise ArchiveValidationError(f"{location}.states", "状态快照 ID 或目标卷不一致")
                if name == "faction_volume_state_initialization_receipts" and operation == "initialize_participation_plans_from_previous":
                    from backend.db.write_contracts import canonical_request_hash
                    from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumeStateInitializeV1
                    try:
                        selected = FactionVolumeStateInitializeV1.model_validate({"faction_ids": document.get("faction_ids"), "skip_existing": False}).faction_ids
                    except (ValueError, TypeError) as exc:
                        raise ArchiveValidationError(location, "复制计划回执缺少原选择") from exc
                    expected = {"operation": operation, "novel_id": str(novel_id), "target_volume_id": str(document["target_volume_id"]),
                                "faction_ids": sorted(selected), "skip_existing": False}
                    if (format_version < 14 or selected != sorted(selected) or document["source_volume_id"] == document["target_volume_id"]
                            or [row.get("faction_id") for row in rows] != selected or document["request_hash"] != canonical_request_hash(expected)):
                        raise ArchiveValidationError(location, "复制计划的原选择、请求摘要或完整结果不一致")
                    source_ids = set()
                    for index, row in enumerate(rows):
                        if row.get("content_contract") != "participation_plan_v1":
                            raise ArchiveValidationError(location, "新复制计划必须完整保留参与计划合同")
                        if row.get("version") != 1 or {field: value for field, value in row.items() if field != "plan_creation_result"} != row.get("plan_creation_result"):
                            raise ArchiveValidationError(location, "复制回执必须保持完整的首次创建结果，不能随当前计划更新")
                        # 先删复制行再删来源是合法操作；原来源 ID 仍由首次创建摘要校验。
                        source = _reference(row.get("source_state_id"), by_id["faction_volume_states"], f"{location}.states[{index}].source_state_id", summary, physical=True, historical=True)
                        child_key = hashlib.sha256(f"faction-plan-copy:{document['idempotency_key_hash']}:{index}".encode()).hexdigest()
                        if (source is not None and (source["volume_id"] != document["source_volume_id"] or source["faction_id"] != row["faction_id"])
                                or row["source_state_id"] in identities or row["source_state_id"] in source_ids
                                or row.get("creation_idempotency_key_hash") != child_key):
                            raise ArchiveValidationError(location, "复制计划的来源身份或原子成员与原请求不一致")
                        source_ids.add(row["source_state_id"])
            elif name == "volume_command_receipts":
                if operation == "update_character_volume_plan":
                    from backend.db.write_contracts import canonical_request_hash
                    from backend.llm.schemas.character_volume_state_pydantic import CharacterVolumePlanUpdateV1, CharacterVolumeStateReadV1
                    import unicodedata
                    result, request = document.get("result"), document.get("request")
                    if format_version < 14 or not isinstance(result, dict) or not isinstance(request, dict):
                        raise ArchiveValidationError(location, "人物计划修改原成功回执只由 v14 承载")
                    _snapshot_rows([result], f"{location}.result", novel_id, "state_id")
                    # 回执恢复后会直接交给路由，未修改的字段也必须构成完整响应。
                    public = {field: value for field, value in result.items() if field in CharacterVolumeStateReadV1.model_fields}
                    for field in ("state_id", "novel_id", "volume_id", "source_state_id"):
                        if public.get(field) is not None:
                            public[field] = str(public[field])
                    try:
                        CharacterVolumeStateReadV1.model_validate(public)
                    except (ValueError, TypeError) as exc:
                        raise ArchiveValidationError(f"{location}.result", "首次人物计划修改响应不符合完整公开合同") from exc
                    try:
                        changes = CharacterVolumePlanUpdateV1.model_validate(request.get("changes")).model_dump(mode="json", exclude_unset=True)
                    except (ValueError, TypeError) as exc:
                        raise ArchiveValidationError(f"{location}.request", "原计划差量请求无效") from exc
                    if (request != {"operation": operation, "novel_id": str(novel_id), "state_id": str(result["state_id"]), "changes": changes}
                            or result.get("_id") != result["state_id"] or not isinstance(result["state_id"], ObjectId)
                            or result.get("volume_id") != document.get("volume_id") or not isinstance(document.get("volume_id"), ObjectId)
                            or result.get("version") not in (changes["expected_version"], changes["expected_version"] + 1)
                            or any(result.get(field) != (unicodedata.normalize("NFKC", value).strip() if isinstance(value, str) else value) for field, value in changes.items() if field != "expected_version")
                            or canonical_request_hash(request) != document["request_hash"]):
                        raise ArchiveValidationError(f"{location}.result", "首次计划修改结果与原请求不一致")
                    rows, identity_field, mapping = [result], "state_id", {"updated": str(result["state_id"])}
                    volume_entity_receipt = True
                elif operation == "update_faction_volume_plan":
                    from backend.db.write_contracts import canonical_request_hash
                    from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumePlanUpdateV1
                    result, request = document.get("result"), document.get("request")
                    if format_version < 14 or not isinstance(result, dict) or not isinstance(request, dict):
                        raise ArchiveValidationError(location, "势力计划修改原成功回执只由 v14 承载")
                    _snapshot_rows([result], f"{location}.result", novel_id, "state_id")
                    try:
                        changes = FactionVolumePlanUpdateV1.model_validate(request.get("changes")).model_dump(mode="json", exclude_unset=True)
                    except (ValueError, TypeError) as exc:
                        raise ArchiveValidationError(f"{location}.request", "原计划差量请求无效") from exc
                    if (request != {"operation": operation, "novel_id": str(novel_id), "state_id": str(result["state_id"]), "changes": changes}
                            or result.get("_id") != result["state_id"] or not isinstance(result["state_id"], ObjectId)
                            or result.get("volume_id") != document.get("volume_id") or not isinstance(document.get("volume_id"), ObjectId)
                            or result.get("version") != changes["expected_version"] + 1
                            or any(result.get(field) != value for field, value in changes.items() if field != "expected_version")
                            or canonical_request_hash(request) != document["request_hash"]):
                        raise ArchiveValidationError(f"{location}.result", "首次计划修改结果与原请求不一致")
                    if "content_contract" in result:
                        _validate_faction_plan(result, f"{location}.result", format_version=format_version)
                    rows, identity_field, mapping = [result], "state_id", {"updated": str(result["state_id"])}
                    volume_entity_receipt = True
                elif operation in ("create", "launch-package", "bulk-plan"):
                    rows, mapping = document.get("volumes"), document.get("candidate_ref_map")
                elif operation in ("create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai"):
                    volume_entity_receipt = True
                    mapping_field = "result.mapping"
                    result = document.get("result")
                    if not isinstance(document.get("volume_id"), ObjectId) or not isinstance(result, dict) or result.get("novel_id") != str(novel_id) or result.get("volume_id") != str(document["volume_id"]):
                        raise ArchiveValidationError(f"{location}.result", "卷资料回执的作品或卷 ID 不一致")
                    rows, mapping = result.get("data"), result.get("mapping")
                    identity_field = "character_id" if operation.startswith("create_characters") else "faction_id"
                    _snapshot_rows(rows, f"{location}.result.data", novel_id, "state_id")
                    for index, row in enumerate(rows):
                        if operation == "create_factions_for_volume_by_ai" and "content_contract" in row:
                            if format_version < 14:
                                raise ArchiveValidationError(f"{location}.result.data[{index}]", "势力卷参与计划回执只由 v14 承载")
                            import json
                            from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumePlanReadV1
                            try:
                                FactionVolumePlanReadV1.model_validate_json(json.dumps(row, ensure_ascii=False))
                            except (ValueError, TypeError) as exc:
                                raise ArchiveValidationError(f"{location}.result.data[{index}]", "首次卷参与计划响应不符合完整公开合同") from exc
                        if not isinstance(row["state_id"], str):
                            raise ArchiveValidationError(f"{location}.result.data[{index}].state_id", "公开状态 ID 必须是 ObjectId 字符串")
                        for field in ("novel_id", "volume_id"):
                            if row.get(field) != result[field]:
                                raise ArchiveValidationError(f"{location}.result.data[{index}].{field}", "状态快照的作品或卷与回执不一致")
                else:
                    raise ArchiveValidationError(f"{location}.operation", "未知卷命令")
            elif name == "writing_confirmation_receipts":
                fields = {"plan_arcs_by_ai": "arc_id", "plan_scenes_by_ai": "scene_id", "plan_chapters_by_ai": "chapter_id", "write_chapter_by_ai": "chapter_id", "restore_chapter_revision": "chapter_id", "generate_volume_plot_by_ai": "_id", "generate_arc_plot_by_ai": "arc_id"}
                result = document.get("result")
                if not isinstance(result, dict):
                    raise ArchiveValidationError(f"{location}.result", "写作回执缺少成功响应")
                if operation in ("prepare_factions", "prepare_characters", "prepare_locations"):
                    rows = [result]
                    _snapshot_rows([result], f"{location}.result", novel_id, "_id")
                elif operation in fields:
                    rows = result.get("data")
                    identities = _snapshot_rows(rows, f"{location}.result.data", novel_id, fields[operation])
                    if result.get("operation") != operation or result.get("ids") != [str(value) for value in identities]:
                        raise ArchiveValidationError(f"{location}.result.ids", "写作回执 ID 与成功响应不一致")
                else:
                    raise ArchiveValidationError(f"{location}.operation", "未知写作命令")
            else:
                field, identity_field = {"world_rule_core_confirmation_receipts": ("world_rules_snapshot", "rule_id"), "location_generation_confirmation_receipts": ("locations", "location_id"), "item_generation_confirmation_receipts": ("items_snapshot", "item_id")}[name]
                rows, mapping = document.get(field), document.get("candidate_ref_map")
            if mapping is not None or name in ("volume_command_receipts", "world_rule_core_confirmation_receipts", "location_generation_confirmation_receipts", "item_generation_confirmation_receipts"):
                identities = _snapshot_rows(rows, f"{location}.snapshots", novel_id, identity_field)
                if not isinstance(mapping, dict) or any(not isinstance(key, str) or not key or not isinstance(value, str) for key, value in mapping.items()):
                    raise ArchiveValidationError(f"{location}.{mapping_field}", "回执候选 ID 映射格式错误")
                values = list(mapping.values())
                identity_set = {str(identity) for identity in identities}
                if len(set(values)) != len(values) or any(value not in identity_set for value in values):
                    raise ArchiveValidationError(f"{location}.{mapping_field}", "回执候选 ID 不在成功快照中或重复")
                if (name != "volume_command_receipts" or volume_entity_receipt) and set(values) != identity_set:
                    raise ArchiveValidationError(f"{location}.{mapping_field}", "回执候选映射未覆盖成功快照")
            # 成功回执中的旧 ID 也占过号，不能因正式对象已永久删除就回退序列。
            for index, row in enumerate(rows or []):
                if name == "faction_volume_state_initialization_receipts" and "content_contract" in row:
                    _validate_faction_plan(row, f"{location}.states[{index}]", format_version=format_version)
                for field, entity, prefix in BUSINESS_IDS.values():
                    if field in row:
                        # 两种关系都叫 relation_id；只有匹配的固定前缀才决定其序列。
                        if field == "relation_id" and isinstance(row[field], str) and not row[field].startswith(f"{prefix}_"):
                            continue
                        number = _business_number(row[field], prefix, f"{location}.snapshots[{index}].{field}")
                        sequence_minimum[entity] = max(sequence_minimum[entity], number)
                        required_sequences.add(entity)
                # 快照中明确保存的旧引用同样占过号；只读这些已知字段，不扫描正文。
                historical_refs = []
                for field, entity, prefix in (
                    ("owner_character_id", "character", "char"),
                    ("controlling_faction_id", "faction", "fac"),
                    ("current_location_id", "location", "loc"),
                    ("parent_location_id", "location", "loc"),
                    ("detached_parent_location_id", "location", "loc"),
                ):
                    if row.get(field) is not None:
                        historical_refs.append((field, [row[field]], entity, prefix))
                for field, entity, prefix in (
                    ("associated_faction_ids", "faction", "fac"),
                    ("applicable_rule_ids", "world_rule", "rule"),
                    ("location_ids", "location", "loc"),
                    ("relationship_focus_ids", "character_relation", "cr"),
                ):
                    if field in row:
                        historical_refs.append((field, row[field], entity, prefix))
                if row.get("scope_type") in ("character", "faction", "location"):
                    entity = row["scope_type"]
                    prefix = {"character": "char", "faction": "fac", "location": "loc"}[entity]
                    historical_refs.append(("scope_entity_ids", row.get("scope_entity_ids", []), entity, prefix))
                if "planning" in row:
                    planning = row["planning"]
                    if planning is None and (
                        name == "volume_command_receipts" and operation in ("create", "launch-package", "bulk-plan")
                        or name == "writing_confirmation_receipts" and operation in (
                            "generate_volume_plot_by_ai", "prepare_factions", "prepare_characters", "prepare_locations"
                        )
                    ):
                        # 未规划的卷没有规划引用，原快照仍保留 null。
                        planning = {}
                    if not isinstance(planning, dict):
                        raise ArchiveValidationError(f"{location}.snapshots[{index}].planning", "历史规划必须是对象")
                    for field, entity, prefix in (
                        ("character_ids", "character", "char"), ("faction_ids", "faction", "fac"),
                        ("location_ids", "location", "loc"), ("item_ids", "item", "item"),
                        ("rule_ids", "world_rule", "rule"),
                    ):
                        if field in planning:
                            historical_refs.append((f"planning.{field}", planning[field], entity, prefix))
                    if planning.get("pov_character_id") is not None:
                        historical_refs.append(("planning.pov_character_id", [planning["pov_character_id"]], "character", "char"))
                for field, values, entity, prefix in historical_refs:
                    field_location = f"{location}.snapshots[{index}].{field}"
                    if not isinstance(values, list):
                        raise ArchiveValidationError(field_location, "历史引用必须是数组")
                    for value in values:
                        number = _business_number(value, prefix, field_location)
                        sequence_minimum[entity] = max(sequence_minimum[entity], number)
                        required_sequences.add(entity)
            summary["receipts"] += 1

    if "events" in documents:
        legacy_documents, legacy_by_id, fact_documents, relation_documents, item_documents, faction_documents = dict(documents), dict(by_id), {}, {}, {}, {}
        receipt_keys = set()
        for name in ("entity_state_history", "chapter_record_confirmation_receipts"):
            legacy_rows, fact_rows, relation_rows, item_rows, faction_rows = [], [], [], [], []
            suffix = "" if name == "entity_state_history" else ".receipt"
            for row in documents[name]:
                location = locations[name, row["_id"]]
                marked = "schema_id" in row or "schema_version" in row
                if format_version not in CHARACTER_BATCH_FORMAT_VERSIONS and row.get("position", {}).get("intent") == "volume_start":
                    raise ArchiveValidationError(location, "本卷开始位置需要 v12、v13 或 v14 备份格式")
                if format_version not in CHARACTER_BATCH_FORMAT_VERSIONS and name == "chapter_record_confirmation_receipts":
                    # 冻结读取也使用位置合同；旧格式不能从书初回执的嵌套读取夹带本卷起点。
                    request = row.get("request")
                    data = request.get("data") if isinstance(request, dict) else None
                    basis = data.get("basis") if isinstance(data, dict) else None
                    reads = basis.get("reads") if isinstance(basis, dict) else None
                    if isinstance(reads, list):
                        for index, read in enumerate(reads):
                            position = read.get("position") if isinstance(read, dict) else None
                            if isinstance(position, dict) and position.get("intent") == "volume_start":
                                raise ArchiveValidationError(f"{location}.request.data.basis.reads.{index}.position",
                                                             "冻结读取的本卷开始位置需要 v12、v13 或 v14 备份格式")
                if not marked:
                    legacy_rows.append(row)
                elif type(row.get("schema_version")) is not int or row["schema_version"] != 1:
                    raise ArchiveValidationError(location, "新事实只接受精确双 schema 标记及版本，不能回退旧合同")
                elif format_version >= 8 and row.get("schema_id") == f"character.fact{suffix}":
                    fact_rows.append(row)
                elif format_version >= 9 and row.get("schema_id") == f"character_relation.fact{suffix}":
                    relation_rows.append(row)
                elif format_version >= 10 and row.get("schema_id") == f"item.fact{suffix}":
                    item_rows.append(row)
                elif format_version in FACTION_FACT_FORMAT_VERSIONS and row.get("schema_id") == f"faction.fact{suffix}":
                    faction_rows.append(row)
                else:
                    raise ArchiveValidationError(location, "人物记录要求 v8、关系记录要求 v9、物品记录要求 v10、势力记录要求 v11 或 v13/v14；旧格式和未知 schema 不能混入")
                if name == "chapter_record_confirmation_receipts":
                    key = row.get("idempotency_key_hash")
                    if not isinstance(key, str) or key in receipt_keys:
                        raise ArchiveValidationError(location, "新旧确认回执共用请求键唯一性")
                    receipt_keys.add(key)
            legacy_documents[name] = legacy_rows
            legacy_by_id[name] = {row["_id"]: row for row in legacy_rows}
            fact_documents[name], relation_documents[name], item_documents[name], faction_documents[name] = fact_rows, relation_rows, item_rows, faction_rows
        _validate_chapter_records(legacy_documents, novel_id, legacy_by_id, by_business, locations, summary, sequence_minimum, required_sequences, format_version)
        if any(fact_documents.values()):
            _validate_character_facts(fact_documents, novel_id, by_id, by_business, locations, summary, sequence_minimum, required_sequences)
        if any(relation_documents.values()):
            _validate_relation_facts(relation_documents, by_id, locations, summary)
        if any(item_documents.values()):
            _validate_item_facts(item_documents, by_id, by_business, locations, summary, sequence_minimum, required_sequences)
        if any(faction_documents.values()):
            _validate_faction_facts(faction_documents, by_id, locations, summary, format_version=format_version)
        if format_version >= 9:
            _validate_v9_history_identities(documents, by_id, by_business, locations, summary, sequence_minimum, required_sequences, include_item_facts=format_version >= 10, include_faction_facts=format_version in FACTION_FACT_FORMAT_VERSIONS)
    elif any("chapter_report_head" in row for row in documents["chapters"]):
        raise ArchiveValidationError("collections/chapters.jsonl", "带报告 head 的章节必须使用包含全部章后记录的 v5 归档")

    if "faction_creation_batch_receipts" in documents:
        from backend.ops.book_archive_faction_batches import validate_faction_batches
        validate_faction_batches(documents, novel_id, by_id, by_business, locations, summary, sequence_minimum, required_sequences)

    if "character_creation_batch_receipts" in documents:
        from backend.services.novel.character_fact_batch_contract import (
            CharacterFactBatchCreateV1, CharacterFactBatchResultV1,
            CharacterRelationFactBatchCreateV1, CharacterRelationFactBatchResultV1,
        )
        from backend.db.write_contracts import canonical_request_hash
        from backend.services.novel.character_name import normalize_character_name
        creation_receipts = {(row.get("schema_id"), row.get("idempotency_key_hash")): row
                             for row in documents["chapter_record_confirmation_receipts"]}
        used_creations = set()
        for receipt in documents["character_creation_batch_receipts"]:
            location = locations["character_creation_batch_receipts", receipt["_id"]]
            operation = receipt.get("operation")
            relation = operation == "create_relations"
            try:
                if operation not in {"create_characters", "create_relations"}:
                    raise ValueError("未知整批新建操作")
                # 摘要核对保存原文，不能让 DTO 补默认值或去空白后冒充原请求。
                if receipt["request_hash"] != canonical_request_hash({"operation": operation, "novel_id": str(novel_id), "data": receipt["request"]}):
                    raise ValueError("原请求摘要不一致")
                request = (CharacterRelationFactBatchCreateV1 if relation else CharacterFactBatchCreateV1).model_validate(receipt["request"]).model_dump(mode="json")
                result = (CharacterRelationFactBatchResultV1 if relation else CharacterFactBatchResultV1).model_validate(receipt["result"]).model_dump(mode="json")
                key = receipt["idempotency_key_hash"]
                if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None:
                    raise ValueError("原请求键摘要错误")
                expected_id = ObjectId(hashlib.sha256(f"{novel_id}:{operation}:{key}".encode()).hexdigest()[:24])
                if receipt["_id"] != expected_id or receipt["request_hash"] != canonical_request_hash({"operation": operation, "novel_id": str(novel_id), "data": request}):
                    raise ValueError("原请求摘要或回执身份不一致")
                rows = result["relations" if relation else "characters"]
                if result["novel_id"] != str(novel_id) or [row["candidate_ref"] for row in rows] != [row["candidate_ref"] for row in request["candidates"]]:
                    raise ValueError("整批结果与原候选不对应")
                identity = "relation_id" if relation else "character_id"
                if any(len({row[field] for row in rows}) != len(rows) for field in ("entity_id", identity, "history_id")):
                    raise ValueError("每个候选必须对应不同的新建身份和记录")
                for index, (candidate, row) in enumerate(zip(request["candidates"], rows, strict=True)):
                    child_key = hashlib.sha256(f"batch:{key}:{index}".encode("ascii")).hexdigest()
                    schema = "character_relation.fact.receipt" if relation else "character.fact.receipt"
                    child = creation_receipts.get((schema, child_key))
                    expected_profile = dict(candidate["profile"])
                    if not relation:
                        # 创建时会规范显示名；这里只调整比较副本，原批次及摘要保持不变。
                        expected_profile["name"], _ = normalize_character_name(expected_profile["name"])
                    if relation and expected_profile["relation_type"] in {"friend", "romantic", "ally", "rival", "enemy"}:
                        # 与既有关系创建一致：对称关系只统一两端顺序，不修改端点身份。
                        expected_profile["source_character_id"], expected_profile["target_character_id"] = sorted((
                            expected_profile["source_character_id"], expected_profile["target_character_id"]))
                    if child is None or child["_id"] in used_creations or child["operation"] != "create":
                        raise ValueError("整批成员缺少唯一的原键创建回执")
                    basis = child["request"]["data"]["basis"]
                    saved = child["result"]
                    if (canonical_request_hash(basis["target"]["candidate"]) != canonical_request_hash(expected_profile)
                            or basis["target"]["entity_id"] != row["entity_id"]
                            or basis["position"] != request["position"]
                            or child["request"]["data"]["after"] != candidate["facts"]
                            or any(saved[field] != row[field] for field in ("entity_id", identity))
                            or saved["after_version"] != row["version"] or saved["record"]["history_id"] != row["history_id"]):
                        raise ValueError("整批候选和身份必须与单笔原始创建回执一致")
                    if not relation:
                        expected_references = {("faction", binding["faction_id"], binding["faction_version"])
                                               for binding in candidate["bindings"]}
                        saved_references = {(read["reference"]["entity_type"], read["reference"]["entity_id"], read["version"])
                                            for read in basis["reference_reads"]}
                        if expected_references != saved_references:
                            raise ValueError("人物绑定必须对应创建时读取的势力及版本")
                    used_creations.add(child["_id"])
                    history = by_id["entity_state_history"].get(ObjectId(row["history_id"]))
                    identity = "relation_id" if relation else "character_id"
                    if (history is None or str(history["entity_id"]) != row["entity_id"]
                            or history[identity] != row[identity] or history["after_version"] != row["version"]
                            or history["operation"] != "create" or history["after"] != candidate["facts"]
                            or history["position"] != request["position"]):
                        raise ValueError("整批成功结果缺少对应的原始记录")
                if not relation:
                    expected_refs = [candidate["candidate_ref"] for candidate in request["candidates"] for _ in candidate["bindings"]]
                    if ([binding["candidate_ref"] for binding in result["bindings"]] != expected_refs
                            or len({binding["binding_id"] for binding in result["bindings"]}) != len(expected_refs)):
                        raise ValueError("绑定不属于原人物批次")
                    binding_index = 0
                    for candidate, row in zip(request["candidates"], rows, strict=True):
                        for requested in candidate["bindings"]:
                            saved = result["bindings"][binding_index]
                            binding_index += 1
                            binding_id = saved["binding_id"]
                            if saved["version"] != 1:
                                raise ValueError("新绑定的原版本必须为 1")
                            current = _reference(binding_id, by_business["character_faction_bindings"], location,
                                                 summary, historical=True, business_prefix="cfb")
                            sequence_minimum["character_faction_binding"] = max(sequence_minimum["character_faction_binding"], _business_number(binding_id, "cfb", location))
                            required_sequences.add("character_faction_binding")
                            if current is not None:
                                if (current["character_id"] != row["character_id"] or current["faction_id"] != requested["faction_id"]
                                        or type(current.get("version")) is not int or current["version"] < saved["version"]):
                                    raise ValueError("原绑定身份、归属或版本与现存绑定不一致")
                                if current["version"] == saved["version"] and any(current.get(field) != requested[field]
                                        for field in ("membership_type", "role_title", "public_status", "loyalty_level", "notes")):
                                    raise ValueError("未修改绑定必须保留原保存内容")
            except (ValueError, TypeError, KeyError) as exc:
                raise ArchiveValidationError(location, "整批人物或关系回执不完整或已改变") from exc
            summary["receipts"] += 1

    sequences = {}
    for document in documents["id_sequences"]:
        location = locations["id_sequences", document["_id"]]
        entity, value = document.get("entity_type"), document.get("value")
        if not isinstance(entity, str) or entity not in sequence_minimum:
            raise ArchiveValidationError(f"{location}.entity_type", "未知业务 ID 序列类型")
        if not isinstance(value, int) or isinstance(value, bool) or value < sequence_minimum[entity]:
            raise ArchiveValidationError(f"{location}.value", "序列必须是非负整数，且不能低于含已删除记录的业务 ID")
        sequences[entity] = value
        summary["sequences"] += 1
    for entity in required_sequences:
        if entity not in sequences:
            raise ArchiveValidationError("collections/id_sequences.jsonl", f"缺少 {entity} 的业务 ID 序列")
    return summary
