Hãy chỉ xuất JSON đúng nghiêm ngặt, không xuất giải thích hay Markdown. Trường gốc bắt buộc và chỉ được là core_world_rules, đồng thời sử dụng đúng cấu trúc đầy đủ sau:
{
  "core_world_rules": [
    {
      "candidate_ref": "rule_candidate_1",
      "name": "Tên quy tắc",
      "category": "Phân loại quy tắc",
      "statement": "Tuyên bố quy tắc có thể thi hành và phán định trực tiếp",
      "scope_type": "global",
      "scope_entity_ids": [],
      "enforcement": "Cách quy tắc có hiệu lực",
      "exceptions": [
        {"condition": "Điều kiện ngoại lệ", "effect": "Hiệu ứng sau khi ngoại lệ xảy ra"}
      ],
      "costs_and_consequences": ["Cái giá khi vi phạm hoặc sử dụng quy tắc"],
      "priority": 50,
      "tags": ["Nhãn"]
    }
  ]
}
