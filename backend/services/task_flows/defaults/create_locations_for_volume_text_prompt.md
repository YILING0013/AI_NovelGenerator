请只输出严格 JSON，不要输出解释或 Markdown。根字段必须且只能是 locations，并严格使用以下结构:
{
  "locations": [
    {
      "candidate_ref": "location_candidate_1",
      "name": "新地点名称",
      "aliases": ["地点别名"],
      "location_type": "地点类型",
      "parent_location_ref": null,
      "parent_location_id": null,
      "description": "地点描述",
      "environment": "环境",
      "atmosphere": "氛围",
      "geography": "地理",
      "rules_and_constraints": ["地点自身约束"],
      "applicable_rule_ids": [],
      "associated_faction_ids": [],
      "story_function": "本卷中的叙事功能",
      "tags": ["标签"]
    }
  ]
}
