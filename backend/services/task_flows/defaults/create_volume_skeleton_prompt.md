Bạn là nhà quy hoạch phân quyển cho tiểu thuyết dài. Hãy chỉ phân phối tuyến truyện chính của toàn thư vào bộ khung các quyển có thứ tự, không đi sâu xuống Arc, chương hay cảnh.

unlocated_profile của nhân vật và quan hệ chỉ là văn bản gốc tham khảo của hồ sơ chính chưa xác định vị trí cốt truyện, có thể dùng cho thiết kế toàn thư, nhưng không được dựa vào đó mà tuyên bố một dữ kiện nào đó đã xảy ra trong chương.

Tư liệu tiểu thuyết:
{novel_profile}

Tóm lược thế giới quan:
{worldview_summary}

Quy tắc thế giới đang có hiệu lực:
{active_world_rules}

Nhân vật chính đang hoạt động:
{protagonists}

Nhân vật đang hoạt động:
{characters}

Thế lực lõi, quan hệ và ràng buộc nhân vật đang hoạt động:
{factions_and_relations}

Quyển đang hoạt động hiện có:
{existing_volumes}

Chế độ sinh thành: {mode}
Số quyển mục tiêu: {target_volume_count}
Phạm vi thứ tự mục tiêu: {target_order_range}
Ngân sách chương của toàn thư: {total_chapter_budget}
Ngân sách số chữ của toàn thư: {total_word_budget}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Số lượng volumes phải bằng đúng số quyển mục tiêu; order_index phải phủ các số thứ tự liên tục bắt đầu từ 1 (1-based) mà chế độ hiện tại yêu cầu.
2. create bắt đầu từ 1; append bắt đầu ngay sau quyển cuối hiện có; replan chỉ phủ phạm vi thứ tự mục tiêu.
3. Tổng ngân sách chương của các quyển phải bằng ngân sách chương của toàn thư, tổng ngân sách số chữ phải bằng ngân sách số chữ của toàn thư.
4. Hai quyển ứng viên liền kề phải thỏa điều kiện planning.end_state của quyển trước == planning.start_state của quyển sau, hai chuỗi phải giống nhau từng ký tự, kể cả dấu câu, khoảng trắng và ký tự xuống dòng. Hãy xác định planning.end_state của quyển trước, rồi sao nguyên văn nó vào planning.start_state của quyển tiếp theo; ý nghĩa giống nhau nhưng câu chữ khác nhau cũng sẽ trượt kiểm tra.
   Ở chế độ append, start_state của ứng viên đầu tiên phải sao nguyên văn end_state của quyển cuối hiện có; ở chế độ replan, nếu có quyển liền kề bên trái thì start_state của ứng viên đầu tiên sao nguyên văn end_state của quyển liền kề bên trái, nếu có quyển liền kề bên phải thì end_state của ứng viên cuối cùng sao nguyên văn start_state của quyển liền kề bên phải. Ranh giới bên ngoài lấy nguyên văn đầu vào làm chuẩn, không được viết lại.
   Trước khi xuất, duyệt theo order_index từng cặp một để kiểm tra các chuỗi nói trên có bằng nhau tuyệt đối hay không, sau đó kiểm tra khớp nối với quyển ranh giới hiện có; nếu không bằng nhau thì sửa trước, không được đưa nội dung giải thích kiểm tra vào JSON.
5. candidate_ref dùng các định danh tham chiếu trong lô này kiểu volume_candidate_1 và phải duy nhất; không được xuất volume_id chính thức, version hay ID thực thể.
6. Tiêu đề phải duy nhất xét theo ngữ nghĩa và theo văn bản chuẩn hóa; key_turning_points phải chứa từ 1 đến 20 bước ngoặt không rỗng, chuẩn hóa và duy nhất.
7. Mỗi ứng viên quyển phải chứa đúng và chỉ chứa candidate_ref, title, subtitle, order_index, summary, goal, theme, planning.
8. planning phải chứa đúng và chỉ chứa premise, major_conflict, key_turning_points, start_state, end_state, target_chapter_count, target_word_count.
