Hãy chỉ xuất JSON đúng nghiêm ngặt, không xuất giải thích hay Markdown. Trường gốc bắt buộc và chỉ được là locations, đồng thời sử dụng đúng cấu trúc sau:
{
  "locations": [
    {
      "candidate_ref": "location_candidate_1",
      "name": "Tên địa điểm mới",
      "aliases": ["Bí danh địa điểm"],
      "location_type": "Loại địa điểm",
      "parent_location_ref": null,
      "parent_location_id": null,
      "description": "Mô tả địa điểm",
      "environment": "Môi trường",
      "atmosphere": "Bầu không khí",
      "geography": "Địa lý",
      "rules_and_constraints": ["Ràng buộc của chính địa điểm"],
      "applicable_rule_ids": [],
      "associated_faction_ids": [],
      "story_function": "Chức năng tự sự trong quyển này",
      "tags": ["Nhãn"]
    }
  ]
}
