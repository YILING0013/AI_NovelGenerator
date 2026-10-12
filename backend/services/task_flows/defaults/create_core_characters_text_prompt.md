请只输出严格 JSON，不要输出解释或 Markdown。根字段必须且只能是 core_characters 与 binding_candidates，并严格使用以下完整结构:
{
  "core_characters": [
    {
      "character_ref": "character_01",
      "name": "角色名",
      "aliases": ["别名"],
      "role_type": "protagonist",
      "importance_level": "core",
      "gender": "性别描述",
      "age_group": "年龄阶段",
      "race": "种族或物种",
      "identity": "身份与社会位置",
      "appearance": "外貌特征",
      "personality": "核心性格",
      "core_desire": "核心欲望",
      "core_fear": "核心恐惧",
      "strengths": ["优势"],
      "weaknesses": ["弱点"],
      "abilities": ["能力"],
      "conflict_with_mainline": "与全书主线的核心冲突",
      "relationship_with_protagonist": "与主角的初始关系",
      "initial_state": "故事开始时的状态",
      "growth_direction": "跨全书成长或堕落方向",
      "story_function": "推动主线的叙事功能",
      "arc_seed": "可跨卷展开的角色弧种子",
      "tags": ["标签"]
    }
  ],
  "binding_candidates": [
    {
      "character_ref": "character_01",
      "faction_id": null,
      "membership_type": null,
      "role_title": null,
      "public_status": null,
      "loyalty_level": null,
      "reason": null
    }
  ]
}
