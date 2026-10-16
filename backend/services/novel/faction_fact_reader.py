"""只用明确势力记录按位置求值；不读取数据库或旧主档动态值。"""

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.services.novel.character_fact_contract import CharacterFactReadPositionV1 as FactReadPositionV1
from backend.services.novel.faction_fact_contract import (
    FACTION_FACT_FIELDS, FactionFactRecordV1, FactionFactsAtPositionV1,
)
from backend.services.novel.fact_field_reader import FactPositionConflictError, evaluate_fact_fields


def evaluate_faction_facts(
    faction: dict, records: list[dict], position: dict, directories: dict,
    source_validity: dict[str, bool],
) -> dict:
    """计算势力在明确位置的十一字段事实，不以管理停用推断剧情状态。

    Args:
        faction: 当前势力 BSON 主档，仅提供 _id、novel_id、faction_id、name 和 version。
        records: 本势力的严格公开记录，包含全部逐字段处置状态。
        position: P1 已解析的读取位置和目录顺序。
        directories: 解析位置所用的本书四级活动目录，以 ObjectId 为键。
        source_validity: 按输入记录 ID 提供的来源核验；缺项或非 True 均视为无效。
    Returns:
        严格位置结果；来源失效保留阻断，不回退更早值，不改变输入。
    """
    position = FactReadPositionV1.model_validate(position).model_dump()
    if position["intent"] == "book_start" and ObjectId(position["target_id"]) != faction["novel_id"]:
        raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力读取位置不属于当前小说", status_code=409)
    normalized, identities, source_checks = [], set(), {}
    for payload in records:
        record = FactionFactRecordV1.model_validate(payload).model_dump(exclude_unset=True)
        original_id = record["history_id"]
        # 只统一本次计算的物理身份副本，原记录、原文和冻结请求保持不变。
        for name in ("history_id", "novel_id", "entity_id"):
            record[name] = str(ObjectId(record[name]))
        identity = record["history_id"]
        if (ObjectId(record["novel_id"]) != faction["novel_id"]
                or ObjectId(record["entity_id"]) != faction["_id"]
                or record["faction_id"] != faction["faction_id"] or identity in identities):
            raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力事实的身份或记录编号不一致，请检查记录", status_code=409)
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
        fields = evaluate_fact_fields(FACTION_FACT_FIELDS, normalized, position, directories, source_checks)
    except FactPositionConflictError as exc:
        raise DomainApiError("FACTION_FACT_POSITION_CONFLICT", "同一位置有重复的势力事实，请明确替代原记录", status_code=409) from exc
    return FactionFactsAtPositionV1.model_validate({
        "entity_id": str(faction["_id"]), "faction_id": faction["faction_id"],
        "name": faction["name"], "version": faction["version"], **fields,
    }).model_dump(exclude_unset=True)
