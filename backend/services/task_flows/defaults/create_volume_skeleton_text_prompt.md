Hãy chỉ xuất JSON đúng nghiêm ngặt, không xuất giải thích hay Markdown. Trường gốc bắt buộc và chỉ được là volumes, đồng thời sử dụng đúng cấu trúc sau:
{
  "volumes": [
    {
      "candidate_ref": "volume_candidate_1",
      "title": "Tiêu đề quyển",
      "subtitle": "Tiêu đề phụ của quyển",
      "order_index": 1,
      "summary": "Tóm tắt quyển",
      "goal": "Mục tiêu của quyển này",
      "theme": "Chủ đề của quyển này",
      "planning": {
        "premise": "Tiền đề của quyển này",
        "major_conflict": "Xung đột chính",
        "key_turning_points": ["Bước ngoặt then chốt"],
        "start_state": "Trạng thái khởi đầu",
        "end_state": "Trạng thái kết thúc",
        "target_chapter_count": 10,
        "target_word_count": 100000
      }
    }
  ]
}
