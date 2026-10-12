请只输出严格 JSON，不要输出解释或 Markdown。根字段必须且只能是 items，并严格使用以下结构:
{
  "items": [
    {
      "candidate_ref": "item_candidate_1",
      "name": "物品名称",
      "aliases": ["物品别名"],
      "item_type": "物品类型",
      "description": "物品的用途、影响和重要特征",
      "appearance": "外观",
      "origin": "来源",
      "abilities": ["能力"],
      "limitations": ["限制"],
      "costs": ["使用代价"],
      "owner_character_id": null,
      "controlling_faction_id": null,
      "current_location_id": null,
      "lifecycle_status": "available",
      "story_function": "该物品如何推动主线或人物选择",
      "tags": ["标签"]
    }
  ]
}
