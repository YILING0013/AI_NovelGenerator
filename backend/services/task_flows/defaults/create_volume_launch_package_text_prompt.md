Hãy chỉ xuất JSON đúng định dạng nghiêm ngặt, không xuất giải thích hay Markdown. Trường gốc bắt buộc và chỉ có thể là launch_package, và tuân thủ chặt chẽ cấu trúc sau:
{
  "launch_package": {
    "title": "Tiêu đề quyển",
    "subtitle": "Tiêu đề phụ của quyển",
    "summary": "Tóm tắt quyển",
    "goal": "Mục tiêu của quyển",
    "theme": "Chủ đề của quyển",
    "planning": {
      "premise": "Tiền đề của quyển",
      "major_conflict": "Xung đột chính",
      "key_turning_points": ["Bước ngoặt then chốt"],
      "start_state": "Trạng thái khởi đầu",
      "end_state": "Trạng thái kết thúc",
      "target_chapter_count": 10,
      "target_word_count": 100000
    }
  }
}
