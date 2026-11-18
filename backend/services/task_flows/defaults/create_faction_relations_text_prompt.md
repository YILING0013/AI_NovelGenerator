Hãy chỉ xuất JSON đúng định dạng nghiêm ngặt, không xuất giải thích hay Markdown. Trường gốc bắt buộc và chỉ có thể là relations, và tuân thủ chặt chẽ toàn bộ cấu trúc sau:
{
  "relations": [
    {
      "relation_ref": "relation_001",
      "source_faction_id": "fac_000001",
      "target_faction_id": "fac_000002",
      "relation_type": "allied",
      "current_state": "Trạng thái quan hệ hiện tại",
      "core_conflict": "Mâu thuẫn cốt lõi",
      "hidden_tension": "Căng thẳng sâu kín",
      "possible_change": "Biến đổi có thể xảy ra trong suốt toàn sách",
      "intensity": 4,
      "is_active": true
    }
  ]
}
