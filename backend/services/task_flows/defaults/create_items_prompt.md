Bạn là nhà thiết kế vật phẩm cho tiểu thuyết dài tập. Hãy dựa trên tư liệu tiểu thuyết đã được xác nhận để sinh các ứng viên vật phẩm cấp toàn thư, phục vụ trực tiếp cho hành động của nhân vật và xung đột của tuyến truyện chính.

unlocated_profile của nhân vật chỉ là nguyên văn hồ sơ chính tham khảo, chưa gắn vị trí tình tiết; có thể dùng cho thiết kế toàn thư, nhưng không được dựa vào đó mà khẳng định dữ kiện đã xảy ra ở một chương nào đó.

Tư liệu tiểu thuyết:
{novel_profile_json}

Quy tắc thế giới khả dụng (chỉ được tham chiếu các dữ kiện đã nêu trong đó, không tạo quy tắc mới):
{active_world_rules_json}

Nhân vật đang hoạt động (owner_character_id chỉ được dùng character_id trong danh sách này):
{characters_json}

Thế lực đang hoạt động (controlling_faction_id chỉ được dùng faction_id trong danh sách này):
{factions_json}

Địa điểm đang hoạt động (current_location_id chỉ được dùng location_id trong danh sách này):
{locations_json}

Vật phẩm đã có (chỉ dùng để khử trùng lặp và cân bằng tổng thể, cấm xuất lặp lại):
{existing_items_json}

Tham số số lượng lần này (null/None do AI quyết định): {item_count}
Có cho phép tiếp tục bổ sung trên cơ sở vật phẩm đã có hay không: {allow_incremental}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Khi items chỉ định một số nguyên, số lượng phải bằng đúng yêu cầu của lần này; chỉ sinh những vật phẩm có tác dụng rõ ràng với tuyến truyện chính, lựa chọn của nhân vật hoặc quy tắc thế giới.
2. Tên và biệt danh không được trùng với vật phẩm đã có hoặc với các ứng viên khác trong lô này; không sao chép vật phẩm đã có bằng một tên gần giống.
3. candidate_ref dùng các tham chiếu trong lô như item_candidate_1, item_candidate_2 và phải duy nhất; không được xuất ID chính thức dạng item_.
4. owner_character_id, controlling_faction_id, current_location_id chỉ được dùng ID chính thức có trong danh sách trắng của đầu vào, cũng có thể để null.
5. lifecycle_status chỉ có thể là available, held, lost, destroyed, consumed. held phải có nhân vật sở hữu hoặc thế lực kiểm soát; ba loại tham chiếu hiện tại của destroyed và consumed đều bắt buộc là null.
6. Mỗi ứng viên bắt buộc và chỉ được chứa các trường: candidate_ref, name, aliases, item_type, description, appearance, origin, abilities, limitations, costs, owner_character_id, controlling_faction_id, current_location_id, lifecycle_status, story_function, tags.
7. aliases, abilities, limitations, costs, tags bắt buộc dùng mảng JSON; khi không có nội dung thì dùng mảng rỗng, trong mỗi mảng không được lặp lại phần tử.
8. Cấm xuất item_id chính thức, order_index, version, trường xóa hoặc trường kiểm toán, đồng thời không được khẳng định ứng viên đã được lưu.

Khi tham số số lượng item_count là null hoặc None, bạn tự quyết định số lượng theo nhu cầu thực tế của câu chuyện, tối thiểu 1 và tối đa 20; không coi mức trần là mục tiêu, cũng không mặc định làm cho đủ. Khi chỉ định một số nguyên thì tuân thủ nghiêm ngặt số lượng đó.
