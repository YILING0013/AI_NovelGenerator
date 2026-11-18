Bạn là một nhà hoạch định khởi động quyển cho tiểu thuyết dài kỳ. Hãy chỉ mở rộng gói khởi động của quyển đích, không sắp xếp lại, viết lại hay bổ sung cho các quyển kề bên.

facts.values của nhân vật là các giá trị đã được xác nhận tại vị trí hiện tại; chuỗi trống hoặc mảng trống có chủ đích nghĩa là đã được xóa sạch. facts.unknown và blockers cho biết chưa xác định hoặc chờ kiểm tra lại, không được lấy nguyên văn hồ sơ chính, kế hoạch quyển hay giá trị sớm hơn để bổ sung; các trường không cần thiết cho lần này phải lược bỏ rõ ràng, với trường bắt buộc phải nhắc tác giả nhận hoặc kiểm tra lại.

Tư liệu tiểu thuyết:
{novel_profile}

Tóm tắt thế giới quan:
{worldview_summary}

Quy tắc thế giới đang hoạt động khả dụng:
{active_world_rules}

Nhân vật chính đang hoạt động:
{protagonists}

Nhân vật đang hoạt động:
{characters}

Thế lực cốt lõi, quan hệ và ràng buộc nhân vật đang hoạt động:
{factions_and_relations}

Quyển trước (có thể trống):
{previous_volume}

Quyển đích:
{target_volume}

Quyển sau (có thể trống):
{next_volume}

Số chương mục tiêu: {target_chapter_count}
Số chữ mục tiêu: {target_word_count}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Chỉ xuất launch_package của quyển đích, không xuất sửa đổi quyển kề bên, Arc, chương, cảnh hay văn bản chính.
2. Điểm bắt đầu theo kế hoạch của gói khởi động phải nối tiếp điểm kết thúc theo kế hoạch của quyển trước, điểm kết thúc theo kế hoạch nên nối tiếp điểm bắt đầu theo kế hoạch của quyển sau; những dự hoạch này không chứng minh sự kiện đã xảy ra, trạng thái thực tế không được cung cấp cứ giữ là chưa xác định.
3. Số chương và số chữ mục tiêu trong planning phải chính xác bằng ngân sách đã cho.
4. key_turning_points phải chứa từ 1 đến 20 bước ngoặt không trống, duy nhất sau chuẩn hóa.
5. launch_package phải chứa và chỉ chứa title, subtitle, summary, goal, theme, planning.
6. planning phải chứa và chỉ chứa premise, major_conflict, key_turning_points, start_state, end_state, target_chapter_count, target_word_count.
7. Cấm xuất volume_id, version, order_index, status, các trường ảnh hưởng, trường kiểm toán hoặc bất kỳ ID thực thể chính thức nào.
