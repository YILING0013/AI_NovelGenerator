"""只用已读取的确认记录，计算人物在指定剧情位置的事实。"""

from backend.api.error_protocol import DomainApiError
from backend.services.novel.character_fact_contract import (
    CHARACTER_FACT_FIELDS,
    CharacterFactReadPositionV1,
    CharacterFactRecordV1,
    CharacterFactsAtPositionV1,
)
from backend.services.novel.fact_field_reader import FactPositionConflictError, evaluate_fact_fields


def evaluate_character_facts(
    character: dict, records: list[dict], position: dict, directories: dict,
    source_validity: dict[str, bool],
) -> dict:
    """计算人物在明确剧情位置的十五字段事实，不读取数据库或当前裸字段。

    Args:
        character: 当前人物 BSON 主档，提供 _id、novel_id、character_id、name 和 version。
        records: 已公开化的本人物 CharacterFactRecordV1 记录，保留全部逐字段状态。
        position: P1 已解析的 CharacterFactReadPositionV1，包含真实目录顺序。
        directories: 解析位置时使用的本书四级活动目录，以 ObjectId 为键。
        source_validity: 逐记录来源核验结果，缺失或非 True 均不能提供已知值。
    Returns:
        严格 CharacterFactsAtPositionV1 形状；所有字段明确分为已知或未知，
        来源失效、坏锚和前值不符均保留阻断，不退回更早值。
    """
    position = CharacterFactReadPositionV1.model_validate(position).model_dump()
    normalized = []
    identities = set()
    for payload in records:
        record = CharacterFactRecordV1.model_validate(payload).model_dump(exclude_unset=True)
        # 位置版本有合法缺省，比较替代锚时统一到严格合同的同一形状。
        record["position"]["version"] = 1
        identity = record["history_id"]
        if (record["novel_id"] != str(character["novel_id"])
                or record["entity_id"] != str(character["_id"])
                or record["character_id"] != character["character_id"] or identity in identities):
            raise DomainApiError("CHARACTER_FACT_RECORD_INVALID", "人物事实的身份或记录编号不一致，请检查记录", status_code=409)
        normalized.append(record)
        identities.add(identity)

    try:
        fields = evaluate_fact_fields(CHARACTER_FACT_FIELDS, normalized, position, directories, source_validity)
    except FactPositionConflictError as exc:
        raise DomainApiError("CHARACTER_FACT_POSITION_CONFLICT", "同一位置有重复的人物事实，请明确替代原记录", status_code=409) from exc
    result = {
        "entity_id": str(character["_id"]), "character_id": character["character_id"],
        "name": character["name"], "version": character["version"], **fields,
    }
    return CharacterFactsAtPositionV1.model_validate(result).model_dump(exclude_unset=True)
