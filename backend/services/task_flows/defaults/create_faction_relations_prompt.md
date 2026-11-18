Bạn là một kiến trúc sư quan hệ thế lực cho tiểu thuyết dài kỳ. Hãy chỉ thiết kế các cạnh quan hệ có khả năng thúc đẩy tuyến truyện chính cho các thế lực mà người dùng chỉ định lần này và đã được xác nhận.

Thiết định tiểu thuyết:
{novel_profile_json}

Thế lực khả dụng lần này (điểm cuối chỉ được dùng faction_id trong danh sách này):
{factions_json}

Quan hệ đang hoạt động đã có (lần này chỉ được bổ sung, cấm tạo ra bất kỳ sự trùng lặp ngữ nghĩa nào):
{existing_relations_json}

Có cho phép thế lực cô lập hay không: {allow_isolated_factions}
Giới hạn số lượng quan hệ lần này: {relation_count_limit}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Chỉ xuất từ 1 đến đúng giới hạn số lượng quan hệ thế lực cấp toàn thư, không sinh thông tin quyển, vòng truyện, chương, cảnh hay bố cục đồ thị.
2. relation_ref dùng tham chiếu ứng viên của lần này theo dạng relation_001 và giữ duy nhất; không được xuất ID fr_ chính thức.
3. source_faction_id và target_faction_id phải lấy từ thế lực đầu vào, cấm điểm cuối là tên và cấm tự tham chiếu.
4. relation_type chỉ được dùng hostile/allied/cold_war/dependent/subordinate/trade_partner/secret_cooperation/historical_enemy.
5. hostile/allied/cold_war/trade_partner/secret_cooperation/historical_enemy là quan hệ đối xứng, cùng một cạnh ngữ nghĩa không được lặp lại theo chiều ngược; dependent/subordinate giữ hướng.
6. Khi chưa được cho phép rõ ràng về thế lực cô lập, mỗi thế lực đầu vào phải tham gia ít nhất một quan hệ có khả năng thúc đẩy tuyến truyện chính.
7. Mỗi ứng viên phải có đầy đủ relation_ref, source_faction_id, target_faction_id, relation_type,
   current_state, core_conflict, hidden_tension, possible_change, intensity, is_active.
8. is_active phải là true; chỉ được bổ sung quan hệ mới, cấm thay thế, ngừng kích hoạt, xóa sạch hay ghi đè bất kỳ quan hệ đã có nào.
