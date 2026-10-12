"""人物和人物关系共用的逐字段求值；不读取主档当前值或数据库。"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from bson import ObjectId

from backend.services.novel.writing_position import fact_position_visible, writing_order


class FactPositionConflictError(ValueError):
    """同一实体字段在同一位置出现多个活动记录。"""


@dataclass
class _FieldValue:
    """求值期间保留当前值或阻断它的具体记录，不修改原记录。"""

    unknown: str
    value: Any = None
    origin: str | None = None
    blockers: dict[str, str] = field(default_factory=dict)

    def block(self, identity: str, reason: str) -> None:
        """加入一项阻断，清除不可再使用的旧值。

        Args:
            identity: 造成阻断的记录 ID。
            reason: 来源失效、前值失效或明确作废。
        Returns:
            无；更新本次求值的临时状态。
        """
        self.blockers[identity] = reason
        self.value, self.origin = None, None
        reasons = set(self.blockers.values())
        self.unknown = ("needs_review" if "needs_review" in reasons else
                        "unresolved_reference" if "unresolved_reference" in reasons else "voided")


def _replacement_is_linked(record: dict, name: str, by_id: dict[str, dict]) -> bool:
    """确认整条替代链指向同位置的实际记录，环和缺失引用不能吞掉旧记录。

    Args:
        record: 已退出活动状态的记录。
        name: 当前求值字段。
        by_id: 同一实体的全部严格记录。
    Returns:
        替代链完整且最终指向活动或作废记录时为 True。
    """
    visited = set()
    current = record
    while current["validity"][name]["state"] == "replaced":
        identity = current["history_id"]
        if identity in visited:
            return False
        visited.add(identity)
        following = by_id.get(current["validity"][name]["by_history_id"])
        if (following is None or name not in following["after"]
                or following["replaces"].get(name) != identity
                or following["position"] != current["position"] or following["kind"] != current["kind"]):
            return False
        current = following
    return True


def _before_matches(record: dict, name: str, before: _FieldValue) -> bool:
    """比较变化所依赖的章前值和记录来源，不把同章后旧结果当作前值。

    Args:
        record: 待检查的章后变化。
        name: 当前字段。
        before: 同章后这一组记录生效之前的字段状态。
    Returns:
        已知值及其来源一致，或明确未知原因一致时为 True。
    """
    if name in record["before"]["values"]:
        return (before.origin is not None and record["previous"][name] == before.origin
                and record["before"]["values"][name] == before.value)
    if before.origin is not None or record["previous"][name] is not None:
        return False
    reason = record["before"]["unknown"][name]
    # 首条记录写入后，永久接管会把章前 unclaimed 变成 before_start。
    # 两者只有在没有前值和阻断时等价；不能放宽来源失效等其他未知原因。
    return reason == before.unknown or (not before.blockers and
        {reason, before.unknown} <= {"unclaimed", "before_start"})


def _evaluate_field(
    name: str, records: list[dict], by_id: dict[str, dict], orders: dict[str, tuple | None],
    visible: dict[str, bool | None], source_validity: dict[str, bool], unavailable_references: set[str],
) -> _FieldValue:
    """按一个字段的真实位置处理起点、变化及不可回退的阻断。

    Args:
        name: 固定白名单中的一个字段。
        records: 该字段全部记录，包括未来、替代和作废记录。
        by_id: 同一实体全部记录，用于核对明确引用。
        orders: 由共同目录函数计算的位置，不使用编辑版本和确认时间。
        visible: 记录在本次读取位置是否生效；None 表示锚无法定位。
        source_validity: 每条记录的来源是否有效，缺项视为无效。
        unavailable_references: 引用的实体已缺失、回收或物理身份不符的记录。
    Returns:
        当前完整值，或未知原因和具体阻断记录。
    """
    state = _FieldValue("before_start" if records else "unclaimed")
    groups: dict[tuple, list[dict]] = {}
    active_boundaries = set()
    for record in records:
        identity = record["history_id"]
        validity = record["validity"][name]["state"]
        boundary = orders[identity]
        if validity == "active":
            # 无法定位的同一稳定锚仍不能容许两个活动值。
            active_key = boundary if boundary is not None else (
                "missing", record["position"]["intent"], record["position"]["target_id"],
            )
            if active_key in active_boundaries:
                raise FactPositionConflictError("同一字段位置存在重复的活动记录")
            active_boundaries.add(active_key)
        if validity == "replaced" and _replacement_is_linked(record, name, by_id):
            continue
        if visible[identity] is None:
            state.block(identity, "voided" if validity == "voided" else
                        "unresolved_reference" if validity == "replaced" else "needs_review")
        elif visible[identity]:
            groups.setdefault(boundary, []).append(record)

    for boundary in sorted(groups):
        rows = groups[boundary]
        before = deepcopy(state)
        # 作废和坏替代先占住原边界；后续活动记录必须明确处置它们。
        for record in rows:
            validity = record["validity"][name]["state"]
            if validity != "active":
                state.block(record["history_id"], "voided" if validity == "voided" else "unresolved_reference")
        for record in rows:
            identity = record["history_id"]
            if record["validity"][name]["state"] != "active":
                continue
            if source_validity.get(identity) is not True:
                state.block(identity, "needs_review")
                continue
            if identity in unavailable_references:
                state.block(identity, "unresolved_reference")
                continue
            replaced_id = record["replaces"].get(name)
            replaced = by_id.get(replaced_id) if replaced_id is not None else None
            if replaced_id is not None and (replaced is None or name not in replaced["after"]
                    or replaced["validity"][name] != {"state": "replaced", "by_history_id": identity}
                    or replaced["position"] != record["position"] or replaced["kind"] != record["kind"]):
                state.block(identity, "unresolved_reference")
                continue
            resolved = record["resolves"].get(name, [])
            if any(target not in by_id or name not in by_id[target]["after"] for target in resolved):
                state.block(identity, "unresolved_reference")
                continue
            if record["kind"] == "change" and not _before_matches(record, name, before):
                state.block(identity, "unresolved_reference")
                continue
            for target in [*resolved, *([replaced_id] if replaced_id is not None else [])]:
                state.blockers.pop(target, None)
            if state.blockers:
                # 新起点不能自动抹去失效来源；变化还依赖未解除的章前阻断。
                if record["kind"] == "change":
                    state.block(identity, "unresolved_reference")
                else:
                    first = next(iter(state.blockers))
                    state.block(first, state.blockers[first])
                continue
            state.value = deepcopy(record["after"][name])
            state.origin = identity
            state.unknown = ""
    return state


def evaluate_fact_fields(
    fields: frozenset[str], records: list[dict], position: dict, directories: dict,
    source_validity: dict[str, bool], *, unavailable_references: set[str] | None = None,
) -> dict:
    """按共同目录和前值依据计算已通过各自严格合同的字段记录。

    Args:
        fields: 调用方实际支持的固定字段集合。
        records: 同一实体的严格记录，身份及记录编号已由调用方核验。
        position: 已解析的 P1 读取位置。
        directories: 同一份四级活动目录。
        source_validity: 逐记录的来源核验结果，缺项不得提供已知值。
        unavailable_references: 确认记录依赖的实体已不可用；不能退回更早值。
    Returns:
        已知值、未知原因、来源、阻断记录和永久认领字段；不改变输入。
    """
    by_id = {record["history_id"]: record for record in records}
    orders, visible = {}, {}
    for record in records:
        identity = record["history_id"]
        visible[identity] = fact_position_visible(record["position"], position, directories)
        if record["position"]["intent"] == "book_start":
            orders[identity] = ()
        else:
            kind = record["position"]["target_type"]
            anchor = directories[kind].get(ObjectId(record["position"]["target_id"]))
            order = writing_order(kind, anchor, directories) if anchor is not None else None
            orders[identity] = (order if kind == "volume" else (*order, int(record["position"]["intent"] == "chapter_after"))) if order is not None else None
    result = {"values": {}, "unknown": {}, "origins": {}, "blockers": {}, "claimed_fields": []}
    for name in sorted(fields):
        field_records = [record for record in records if name in record["after"]]
        if field_records:
            result["claimed_fields"].append(name)
        value = _evaluate_field(name, field_records, by_id, orders, visible, source_validity,
                                unavailable_references or set())
        if value.origin is not None:
            result["values"][name] = value.value
            result["origins"][name] = value.origin
        else:
            result["unknown"][name] = value.unknown
            if value.blockers:
                result["blockers"][name] = sorted(value.blockers)
    return result
