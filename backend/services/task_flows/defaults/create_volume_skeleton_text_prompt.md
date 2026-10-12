请只输出严格 JSON，不要输出解释或 Markdown。根字段必须且只能是 volumes，并严格使用以下结构:
{
  "volumes": [
    {
      "candidate_ref": "volume_candidate_1",
      "title": "卷标题",
      "subtitle": "卷副标题",
      "order_index": 1,
      "summary": "卷摘要",
      "goal": "本卷目标",
      "theme": "本卷主题",
      "planning": {
        "premise": "本卷前提",
        "major_conflict": "主要冲突",
        "key_turning_points": ["关键转折"],
        "start_state": "起始状态",
        "end_state": "结束状态",
        "target_chapter_count": 10,
        "target_word_count": 100000
      }
    }
  ]
}
