Hãy chỉ xuất JSON đúng nghiêm ngặt, không xuất giải thích hay Markdown. Các trường gốc bắt buộc và chỉ được là core_characters và binding_candidates, đồng thời sử dụng đúng cấu trúc đầy đủ sau:
{
  "core_characters": [
    {
      "character_ref": "character_01",
      "name": "Tên nhân vật",
      "aliases": ["Bí danh"],
      "role_type": "protagonist",
      "importance_level": "core",
      "gender": "Mô tả giới tính",
      "age_group": "Giai đoạn tuổi",
      "race": "Chủng tộc hoặc giống loài",
      "identity": "Thân phận và vị trí xã hội",
      "appearance": "Đặc điểm ngoại hình",
      "personality": "Tính cách cốt lõi",
      "core_desire": "Khao khát cốt lõi",
      "core_fear": "Nỗi sợ cốt lõi",
      "strengths": ["Ưu điểm"],
      "weaknesses": ["Điểm yếu"],
      "abilities": ["Năng lực"],
      "conflict_with_mainline": "Xung đột cốt lõi với tuyến chính của toàn truyện",
      "relationship_with_protagonist": "Quan hệ ban đầu với nhân vật chính",
      "initial_state": "Trạng thái khi truyện bắt đầu",
      "growth_direction": "Hướng trưởng thành hoặc sa ngã xuyên suốt toàn truyện",
      "story_function": "Chức năng tự sự thúc đẩy tuyến chính",
      "arc_seed": "Hạt mầm vòng cung nhân vật có thể triển khai qua nhiều quyển",
      "tags": ["Nhãn"]
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
