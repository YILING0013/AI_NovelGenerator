Hãy xuất JSON đúng nghiêm ngặt, không xuất thêm nội dung thừa:
{
  "core_factions": [
    {
      "faction_ref": "faction_001",
      "name": "Tên thế lực",
      "faction_type": "Chính quyền quốc gia/tổ chức môn phái/thế lực ngầm/liên minh thương mại/tổ chức tôn giáo/thế lực ngoại tộc/tổ chức nghiên cứu/tổ chức trung lập/bí mật kết xã, v.v.",
      "positioning": "Vị trí của thế lực trong cấu trúc thế giới",
      "public_stance": "Công khai gìn giữ trật tự thành phố",
      "core_goal": "Mục tiêu cốt lõi thực sự",
      "hidden_goal": "Mục tiêu ẩn, có thể là chuỗi rỗng",
      "resources_and_advantages": ["Tài nguyên hoặc lợi thế 1", "Tài nguyên hoặc lợi thế 2"],
      "organization_style": "Khí chất tổ chức hoặc phong cách hành động",
      "core_values": ["Giá trị 1", "Giá trị 2"],
      "conflict_with_mainline": "Quan hệ của thế lực này với xung đột tuyến chính",
      "is_public": true,
      "influence_scope": "Cấp toàn lãnh thổ/cấp đa khu vực/cấp khu vực",
      "expandability": "Hướng có thể mở rộng về sau",
      "tags": ["Nhãn 1", "Nhãn 2"]
    }
  ],
  "faction_relations": [
    {
      "relation_ref": "relation_001",
      "source": {"kind": "candidate", "faction_ref": "faction_001"},
      "target": {"kind": "existing", "faction_id": "fac_000001"},
      "relation_type": "hostile",
      "current_state": "Trạng thái quan hệ hiện tại",
      "core_conflict": "Hai bên tranh giành quyền kiểm soát kho hồ sơ",
      "hidden_tension": "Căng thẳng tiềm ẩn sâu",
      "possible_change": "Chuyển sang hợp tác tạm thời sau khi bằng chứng được công khai",
      "intensity": 5,
      "is_active": true
    }
  ]
}
