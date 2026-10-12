请严格输出 JSON，不要输出额外内容:
{
  "core_factions": [
    {
      "faction_ref": "faction_001",
      "name": "阵营名称",
      "faction_type": "国家政权/宗门组织/地下势力/商业联盟/宗教组织/异族势力/研究组织/中立组织/秘密结社等",
      "positioning": "阵营在世界结构中的位置",
      "public_stance": "公开维护城市秩序",
      "core_goal": "真实核心目标",
      "hidden_goal": "隐藏目标，可为空字符串",
      "resources_and_advantages": ["资源或优势1", "资源或优势2"],
      "organization_style": "组织气质或行动风格",
      "core_values": ["价值观1", "价值观2"],
      "conflict_with_mainline": "该阵营与主线冲突的关系",
      "is_public": true,
      "influence_scope": "全域级/多区域级/区域级",
      "expandability": "后续可扩展方向",
      "tags": ["标签1", "标签2"]
    }
  ],
  "faction_relations": [
    {
      "relation_ref": "relation_001",
      "source": {"kind": "candidate", "faction_ref": "faction_001"},
      "target": {"kind": "existing", "faction_id": "fac_000001"},
      "relation_type": "hostile",
      "current_state": "当前关系状态",
      "core_conflict": "双方争夺档案控制权",
      "hidden_tension": "深层张力",
      "possible_change": "证据公开后转为暂时合作",
      "intensity": 5,
      "is_active": true
    }
  ]
}
