"""人物关系的离线按位置求值；生产入口尚未切换到此实现。"""

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.services.novel.character_fact_contract import CharacterFactReadPositionV1
from backend.services.novel.character_relation_fact_contract import (
    CHARACTER_RELATION_FACT_FIELDS, CharacterRelationFactRecordV1, CharacterRelationFactsAtPositionV1,
)
from backend.services.novel.fact_field_reader import FactPositionConflictError, evaluate_fact_fields


def evaluate_character_relation_facts(
    relation: dict, characters: list[dict], records: list[dict], position: dict,
    directories: dict, source_validity: dict[str, bool],
) -> dict:
    """用关系记录和真实端点身份计算状态，不读取裸 current_state 或计划。

    Args:
        relation: 当前关系 BSON 主档，仅提供关系身份、两端业务 ID 和版本。
        characters: 本书两端人物的当前 BSON 文档；缺失与回收不会变成无关系。
        records: 本关系的全部严格公开记录，保留逐字段处置和当时端点身份。
        position: P1 已解析的读取位置，包含完整目录顺序。
        directories: 同一份四级活动目录。
        source_validity: 按原记录 ID 提供的来源核验；缺项视为无效。
    Returns:
        严格关系事实结果；来源失效或端点不可用均不能退回旧值。
    """
    position = CharacterFactReadPositionV1.model_validate(position).model_dump()
    endpoint_ids = {relation["source_character_id"], relation["target_character_id"]}
    endpoints = {row["character_id"]: row for row in characters}
    if (len(endpoint_ids) != 2 or len(endpoints) != len(characters)
            or len({row["_id"] for row in characters}) != len(characters)
            or not endpoints.keys() <= endpoint_ids
            or any(row["novel_id"] != relation["novel_id"] for row in characters)):
        raise DomainApiError("CHARACTER_RELATION_FACT_IDENTITY_INVALID", "关系人物的身份或所属小说不一致，请检查资料", status_code=409)

    normalized, identities, source_checks, unavailable = [], set(), {}, set()
    endpoint_bindings = None
    for payload in records:
        record = CharacterRelationFactRecordV1.model_validate(payload).model_dump(exclude_unset=True)
        original_id = record["history_id"]
        # 只统一本次求值副本中的物理身份，不改原记录或冻结请求的文字。
        for name in ("history_id", "novel_id", "entity_id", "source_character_entity_id", "target_character_entity_id"):
            record[name] = str(ObjectId(record[name]))
        identity = record["history_id"]
        if (ObjectId(record["novel_id"]) != relation["novel_id"]
                or ObjectId(record["entity_id"]) != relation["_id"] or record["relation_id"] != relation["relation_id"]
                or record["source_character_id"] != relation["source_character_id"]
                or record["target_character_id"] != relation["target_character_id"] or identity in identities):
            raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系事实的身份、两端人物或记录编号不一致，请检查记录", status_code=409)
        binding = (record["source_character_entity_id"], record["target_character_entity_id"])
        if endpoint_bindings is not None and binding != endpoint_bindings:
            raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "同一关系的历史不能改绑人物物理身份，请检查记录", status_code=409)
        endpoint_bindings = binding
        for side in ("source", "target"):
            endpoint = endpoints.get(record[f"{side}_character_id"])
            if (endpoint is None or endpoint["is_deleted"]
                    or endpoint["_id"] != ObjectId(record[f"{side}_character_entity_id"])):
                unavailable.add(identity)
        record["position"]["version"] = 1
        record["position"]["target_id"] = str(ObjectId(record["position"]["target_id"]))
        for name in ("previous", "replaces"):
            record[name] = {field: str(ObjectId(value)) if value is not None else None for field, value in record[name].items()}
        record["resolves"] = {field: [str(ObjectId(value)) for value in values] for field, values in record["resolves"].items()}
        for validity in record["validity"].values():
            if validity["state"] == "replaced":
                validity["by_history_id"] = str(ObjectId(validity["by_history_id"]))
        identities.add(identity)
        source_checks[identity] = source_validity.get(original_id) is True
        normalized.append(record)

    try:
        fields = evaluate_fact_fields(CHARACTER_RELATION_FACT_FIELDS, normalized, position, directories,
                                      source_checks, unavailable_references=unavailable)
    except FactPositionConflictError as exc:
        raise DomainApiError("CHARACTER_RELATION_FACT_POSITION_CONFLICT", "同一位置有重复的关系状态，请明确替代原记录", status_code=409) from exc
    return CharacterRelationFactsAtPositionV1.model_validate({
        "entity_id": str(relation["_id"]), "relation_id": relation["relation_id"],
        "source_character_id": relation["source_character_id"], "target_character_id": relation["target_character_id"],
        "version": relation["version"], **fields,
    }).model_dump(exclude_unset=True)
