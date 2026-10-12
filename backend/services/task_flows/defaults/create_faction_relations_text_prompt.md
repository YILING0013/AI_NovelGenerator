请只输出严格 JSON，不要输出解释或 Markdown。根字段必须且只能是 relations，并严格使用以下完整结构:
{
  "relations": [
    {
      "relation_ref": "relation_001",
      "source_faction_id": "fac_000001",
      "target_faction_id": "fac_000002",
      "relation_type": "allied",
      "current_state": "当前关系状态",
      "core_conflict": "核心矛盾",
      "hidden_tension": "深层张力",
      "possible_change": "跨全书可能发生的变化",
      "intensity": 4,
      "is_active": true
    }
  ]
}
