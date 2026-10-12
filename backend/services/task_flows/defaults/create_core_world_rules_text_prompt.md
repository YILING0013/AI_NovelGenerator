请只输出严格 JSON，不要输出解释或 Markdown。根字段必须且只能是 core_world_rules，并严格使用以下完整结构:
{
  "core_world_rules": [
    {
      "candidate_ref": "rule_candidate_1",
      "name": "规则名称",
      "category": "规则分类",
      "statement": "可以直接执行和判断的规则陈述",
      "scope_type": "global",
      "scope_entity_ids": [],
      "enforcement": "规则如何生效",
      "exceptions": [
        {"condition": "例外条件", "effect": "例外发生后的效果"}
      ],
      "costs_and_consequences": ["违反或使用规则的代价"],
      "priority": 50,
      "tags": ["标签"]
    }
  ]
}
