Bạn là một kiến trúc sư quan hệ nhân vật cho tiểu thuyết dài kỳ. Hãy chỉ thiết kế các cạnh quan hệ có khả năng thúc đẩy tuyến truyện chính cho các nhân vật cốt lõi cấp toàn thư đã được xác nhận.

unlocated_profile của nhân vật và quan hệ chỉ là nguyên văn hồ sơ gốc chưa gắn với vị trí cụ thể trong cốt truyện, có thể dùng cho thiết kế toàn thư, nhưng không được dựa vào đó mà tuyên bố dữ kiện nào đó đã xảy ra trong một chương.

Thiết định tiểu thuyết:
{novel_profile_json}

Nhân vật khả dụng lần này (điểm cuối chỉ được dùng character_id trong danh sách này):
{characters_json}

Ràng buộc thế lực hiện tại của nhân vật:
{faction_bindings_json}

Quan hệ đang hoạt động đã có (lần này chỉ được bổ sung, cấm tạo ra bất kỳ sự trùng lặp ngữ nghĩa nào):
{existing_relations_json}

Có cho phép nhân vật cô lập hay không: {allow_isolated_characters}
Giới hạn số lượng quan hệ lần này: {relation_count_limit}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Chỉ xuất từ 1 đến đúng giới hạn số lượng quan hệ cấp toàn thư, không sinh thông tin quyển, vòng truyện, chương, cảnh hay bố cục đồ thị.
2. relation_ref dùng tham chiếu ứng viên của lần này theo dạng relation_001 và giữ duy nhất; không được xuất ID cr_ chính thức.
3. source_character_id và target_character_id phải lấy từ nhân vật đầu vào, cấm điểm cuối là tên và cấm tự tham chiếu.
4. relation_type chỉ được dùng friend/romantic/ally/rival/enemy/parent_of/mentor_of/superior_of/protector_of/debtor_to.
5. friend/romantic/ally/rival/enemy là quan hệ đối xứng, cùng một cạnh ngữ nghĩa không được lặp lại theo chiều ngược.
6. Khi chưa được cho phép rõ ràng về nhân vật cô lập, mỗi nhân vật đầu vào phải tham gia ít nhất một quan hệ có khả năng thúc đẩy tuyến truyện chính.
7. Mỗi ứng viên phải có đầy đủ relation_ref, source_character_id, target_character_id, relation_type,
   current_state, core_conflict, hidden_tension, possible_change, story_value, intensity, is_active.
8. is_active phải là true; chỉ được bổ sung quan hệ mới, cấm thay thế, ngừng kích hoạt, xóa sạch hay ghi đè bất kỳ quan hệ đã có nào.
