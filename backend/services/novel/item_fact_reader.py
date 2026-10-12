"""物品四字段的离线整组求值；不读取裸主档状态或数据库。"""

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.services.novel.character_fact_contract import CharacterFactReadPositionV1
from backend.services.novel.fact_field_reader import FactPositionConflictError, evaluate_fact_fields
from backend.services.novel.item_fact_contract import ItemFactRecordV1, ItemFactsAtPositionV1


def evaluate_item_facts(
    item: dict, records: list[dict], position: dict, directories: dict,
    source_validity: dict[str, bool], reference_validity: dict[str, bool],
) -> dict:
    """用同一位置与来源机制一次求值完整物品组，绝不逐字段拼接。

    Args:
        item: 当前物品 BSON 主档，只提供物理身份、所属小说、业务 ID、名称和版本。
        records: 本物品的全部严格公开记录，包括未来、替代和作废记录；不接收旧 B。
        position: 共同位置函数已解析的读取位置，包含当前完整目录顺序。
        directories: 解析位置时使用的同书四级活动目录。
        source_validity: 每条记录的来源核验结果，缺项视为无效。
        reference_validity: 每条记录完整三引用的核验结果，无引用也须明确 True；
            缺失、回收或身份不符须为 False，本函数不查询或猜测引用身份。
    Returns:
        完整四字段值或整组未知，以及来源和阻断记录；不修改任何输入。
    """
    position = CharacterFactReadPositionV1.model_validate(position).model_dump()
    normalized, identities, source_checks, unavailable = [], set(), {}, set()
    for payload in records:
        record = ItemFactRecordV1.model_validate(payload).model_dump()
        original_id = record["history_id"]
        identity = str(ObjectId(original_id))
        if (ObjectId(record["novel_id"]) != item["novel_id"] or ObjectId(record["entity_id"]) != item["_id"]
                or record["item_id"] != item["item_id"] or identity in identities):
            raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品事实的身份或记录编号不一致，请检查记录", status_code=409)
        identities.add(identity)
        source_checks[identity] = source_validity.get(original_id) is True
        if reference_validity.get(original_id) is not True:
            unavailable.add(identity)
        record["position"]["target_id"] = str(ObjectId(record["position"]["target_id"]))
        validity = record["validity"]
        if validity["state"] == "replaced":
            validity["by_history_id"] = str(ObjectId(validity["by_history_id"]))
        # 只在本次求值内把四字段装成一个值，before 比较和所有处置便不会拆散它。
        normalized.append({
            "history_id": identity, "kind": record["kind"], "position": record["position"],
            "before": {
                "values": {"item_state": record["before"]["values"]} if record["before"]["values"] is not None else {},
                "unknown": {"item_state": record["before"]["unknown"]} if record["before"]["unknown"] is not None else {},
            },
            "after": {"item_state": record["after"]},
            "previous": {"item_state": str(ObjectId(record["previous"])) if record["previous"] is not None else None},
            "replaces": {"item_state": str(ObjectId(record["replaces"]))} if record["replaces"] is not None else {},
            "resolves": {"item_state": [str(ObjectId(value)) for value in record["resolves"]]},
            "validity": {"item_state": validity},
        })
    try:
        result = evaluate_fact_fields(frozenset({"item_state"}), normalized, position, directories,
                                      source_checks, unavailable_references=unavailable)
    except FactPositionConflictError as exc:
        raise DomainApiError("ITEM_FACT_POSITION_CONFLICT", "同一位置有重复的物品状态，请明确替代原整组记录", status_code=409) from exc
    return ItemFactsAtPositionV1.model_validate({
        "entity_id": str(item["_id"]), "item_id": item["item_id"], "name": item["name"], "version": item["version"],
        "values": result["values"].get("item_state"), "unknown": result["unknown"].get("item_state"),
        "origin": result["origins"].get("item_state"), "blockers": result["blockers"].get("item_state", []),
        "claimed": bool(result["claimed_fields"]),
    }).model_dump()
