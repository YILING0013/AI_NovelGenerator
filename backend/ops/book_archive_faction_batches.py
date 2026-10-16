"""v14 势力批次回执与原子命令成员的离线交叉验证。"""

from hashlib import sha256
import json
import re
import unicodedata

from bson import ObjectId

from backend.db.write_contracts import canonical_request_hash
from backend.llm.schemas.faction_relation_pydantic import FactionRelationCreateRequestV1, build_faction_relation_semantic_key
from backend.services.novel.faction_fact_batch_contract import FactionFactBatchCreateV1, FactionFactBatchResultV1


def validate_faction_batches(documents, novel_id, by_id, by_business, locations, summary, sequence_minimum, required_sequences):
    """校验首次完整结果，不拿当前实体内容替代历史保存结果。

    Args:
        documents: 已检查同书物理身份的原始集合。
        novel_id: 包中作品身份。
        by_id: 原始物理身份映射。
        by_business: 现存业务身份映射。
        locations: 原文档的包内行号。
        summary: 累计校验结果。
        sequence_minimum: 历史编号下限。
        required_sequences: 需要保留的分配器。
    Returns:
        无；损坏回执在任何恢复写入前拒绝。
    """
    from backend.ops.book_archive_contract import ArchiveValidationError, _business_number, _reference

    children = {(row.get("schema_id"), row.get("idempotency_key_hash")): row
                for row in documents["chapter_record_confirmation_receipts"]}
    used_children, used_relations, used_keys = set(), set(), set()
    for receipt in documents["faction_creation_batch_receipts"]:
        location = locations["faction_creation_batch_receipts", receipt["_id"]]
        try:
            if receipt["operation"] != "create_factions":
                raise ValueError("未知势力批次操作")
            key = receipt["idempotency_key_hash"]
            if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None or key in used_keys:
                raise ValueError("重复或无效的原键")
            used_keys.add(key)
            if receipt["_id"] != ObjectId(sha256(f"{novel_id}:create_factions:{key}".encode()).hexdigest()[:24]):
                raise ValueError("批次物理身份与原键不符")
            request = FactionFactBatchCreateV1.model_validate(receipt["request"]).model_dump(mode="json")
            result = FactionFactBatchResultV1.model_validate_json(json.dumps(receipt["result"], ensure_ascii=False)).model_dump(mode="json")
            digest = lambda value: canonical_request_hash(value)
            if (digest(request) != digest(receipt["request"]) or digest(result) != digest(receipt["result"])
                    or receipt["request_hash"] != digest({"operation": "create_factions", "novel_id": str(novel_id), "data": request})):
                raise ValueError("原请求或首次完整结果改变")
            rows = result["factions"]
            if (result["novel_id"] != str(novel_id)
                    or [row["candidate_ref"] for row in rows] != [row["candidate_ref"] for row in request["candidates"]]
                    or result["faction_ref_map"] != {row["candidate_ref"]: row["result"]["faction_id"] for row in rows}):
                raise ValueError("势力顺序及映射与原候选不符")
            for field in ("entity_id", "faction_id"):
                if len({row["result"][field] for row in rows}) != len(rows):
                    raise ValueError("批次成员重复")
            for index, (candidate, row) in enumerate(zip(request["candidates"], rows, strict=True)):
                child_key = sha256(f"faction-batch:{key}:{index}".encode("ascii")).hexdigest()
                child = children.get(("faction.fact.receipt", child_key))
                profile = dict(candidate["profile"])
                # 与保存时保持相同的名称规则；离线校验不加载数据库仓储。
                profile["name"] = unicodedata.normalize("NFKC", profile["name"]).strip()
                if not profile["name"] or len(profile["name"]) > 80:
                    raise ValueError("势力名称不能为空或超过 80 个字符")
                if child is None or child["_id"] in used_children or child["operation"] != "create":
                    raise ValueError("缺少唯一的原子创建成员")
                used_children.add(child["_id"])
                data = child["request"]["data"]
                if (digest(child["result"]) != digest(row["result"])
                        or digest(data["basis"]["target"]["candidate"]) != digest(profile)
                        or data["basis"]["position"] != request["position"] or data["after"] != candidate["facts"]):
                    raise ValueError("批次内容与首次成员回执不符")
                record = row["result"]["record"]
                history = by_id["entity_state_history"].get(ObjectId(record["history_id"]))
                if history is None or history["entity_id"] != ObjectId(row["result"]["entity_id"]) or history["operation"] != "create":
                    raise ValueError("缺少原始创建记录")
            first_names = {row["result"]["faction_id"]: row["result"]["faction_name"] for row in rows}
            relation_rows = result["relations"]
            if ([row["relation_ref"] for row in relation_rows] != [row["relation_ref"] for row in request["relations"]]
                    or result["relation_ref_map"] != {row["relation_ref"]: row["result"]["relation_id"] for row in relation_rows}):
                raise ValueError("关系顺序及映射与原候选不符")
            for candidate, row in zip(request["relations"], relation_rows, strict=True):
                # 候选端点已经通过严格合同校验，只按原映射还原正式 ID。
                payload = {field: candidate[field] for field in (
                    "relation_type", "current_state", "core_conflict", "hidden_tension", "possible_change", "intensity", "is_active")}
                for endpoint in ("source", "target"):
                    value = candidate[endpoint]
                    payload[f"{endpoint}_faction_id"] = (result["faction_ref_map"][value["faction_ref"]]
                        if value["kind"] == "candidate" else value["faction_id"])
                expected = FactionRelationCreateRequestV1.model_validate(payload).model_dump(mode="json")
                source, target, _ = build_faction_relation_semantic_key(expected["source_faction_id"], expected["target_faction_id"], expected["relation_type"])
                expected.update(source_faction_id=source, target_faction_id=target)
                saved = row["result"]
                for endpoint in ("source", "target"):
                    first_name = first_names.get(saved[f"{endpoint}_faction_id"])
                    if first_name is not None and saved[f"{endpoint}_faction_name"] != first_name:
                        raise ValueError("首次关系名称与同批新势力的首次名称不符")
                identity = saved["relation_id"]
                if (identity in used_relations or saved["novel_id"] != str(novel_id) or saved["version"] != 1
                        or saved["is_deleted"] or saved["deleted_at"] is not None
                        or saved["deletion_sources"] or saved["disabled_by_faction_ids"]
                        or saved["user_is_active"] != expected["is_active"]
                        or any(saved[field] != value for field, value in expected.items())):
                    raise ValueError("首次关系结果与原候选不符")
                used_relations.add(identity)
                current = _reference(identity, by_business["faction_relations"], location, summary, historical=True, business_prefix="fr")
                sequence_minimum["faction_relation"] = max(sequence_minimum["faction_relation"], _business_number(identity, "fr", location))
                required_sequences.add("faction_relation")
                if current is not None and (current["version"] < 1 or {current["source_faction_id"], current["target_faction_id"]} != {saved["source_faction_id"], saved["target_faction_id"]}):
                    raise ValueError("当前关系身份与原保存结果不符")
                if current is not None and current["version"] == 1 and any(current[field] != saved[field] for field in ("source_faction_id", "target_faction_id", "relation_type", "current_state", "core_conflict", "hidden_tension", "possible_change", "intensity")):
                    raise ValueError("未修改关系的内容与首次结果不符")
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveValidationError(location, "势力整批回执、首次完整结果或原子成员不完整或已改变") from exc
        summary["receipts"] += 1
