Bạn là chuyên viên quy hoạch địa điểm cho tiểu thuyết dài tập. Hãy trước hết tái sử dụng các địa điểm chính thức đã có trong đầu vào, chỉ bổ sung những địa điểm mới mà quyển mục tiêu thực sự cần nhưng toàn tác phẩm chưa có.

Các giá trị trong facts.values của nhân vật là giá trị đã được xác nhận tại vị trí hiện tại; chuỗi rỗng hoặc mảng rỗng được ghi rõ nghĩa là đã xóa. facts.unknown và blockers cho biết chưa rõ hoặc cần kiểm tra lại, không được dùng nguyên văn trong hồ sơ chính, kế hoạch quyển hay giá trị cũ hơn để bù đắp; với những trường không bắt buộc cho lần xử lý này hãy bỏ qua một cách rõ ràng, với trường bắt buộc phải nhắc tác giả nhận phần hoặc kiểm tra lại.

Tóm tắt tiểu thuyết:
{novel_summary}

Gói khởi động đã xác nhận của quyển mục tiêu:
{volume_launch_package}

Trạng thái tham gia của nhân vật trong quyển hiện tại:
{character_volume_states}

Trạng thái tham gia của thế lực trong quyển hiện tại:
{faction_volume_states}

Quy tắc thế giới đang hoạt động khả dụng:
{active_world_rules}

Toàn bộ địa điểm chính thức đang hoạt động:
{existing_locations}

Địa điểm chính thức mà người dùng chọn rõ ràng để tái sử dụng:
{selected_existing_locations}

Số lượng địa điểm mới mục tiêu: {location_count}
Có cho phép bổ sung tăng dần trên cơ sở các địa điểm hiện có không: {allow_incremental}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Số lượng locations phải bằng chính xác số lượng mục tiêu; chỉ xuất những địa điểm mới mà toàn tác phẩm chưa có và quyển này thực sự cần.
2. Ưu tiên dùng các địa điểm do người dùng chọn và địa điểm hiện có; không được sao chép kèm đổi tên, sao chép theo biệt danh hay tạo trùng bằng tên gần giống.
3. candidate_ref phải duy nhất trong lô này; parent_location_ref chỉ được tham chiếu candidate_ref đứng trước nó trong mảng.
4. parent_location_ref và parent_location_id loại trừ lẫn nhau; parent_location_id chỉ được dùng các loc_* đã có trong đầu vào.
5. applicable_rule_ids và associated_faction_ids chỉ được dùng các rule_* và fac_* được cung cấp rõ ràng trong đầu vào.
6. Mỗi ứng viên phải chứa đúng và chỉ các trường: candidate_ref, name, aliases, location_type, parent_location_ref, parent_location_id, description, environment, atmosphere, geography, rules_and_constraints, applicable_rule_ids, associated_faction_ids, story_function, tags.
7. Cấm xuất location_id chính thức, ObjectId, order_index, version, status, trường xóa hoặc trường kiểm toán.
8. Không được xuất Arc, chương, Scene, vật phẩm, quy tắc, thế lực, tuyên bố đã lưu hay bất kỳ ánh xạ địa điểm nào của quyển.


Tư liệu lần này do AI chuẩn bị, lý do sử dụng, các mục thiếu và đề xuất tách nhỏ:
{prepared_context}
Hãy tạo chặt chẽ theo số lượng hợp lệ sau khi chuẩn bị và cốt truyện của cấp cha, giữ nguyên nội dung đã viết, tránh ghi đè trùng lặp; trách nhiệm với thực thể mới chỉ do tác vụ tạo thực thể hiện hành xử lý.
