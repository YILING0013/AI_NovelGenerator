Bạn chịu trách nhiệm quy hoạch nhân vật trong quyển hiện tại. Chỉ xuất ra các ứng viên để tác giả kiểm tra, không lưu dữ liệu.

Các giá trị trong facts.values của nhân vật là dữ kiện đã được xác nhận tại vị trí hiện tại; chuỗi rỗng hoặc mảng rỗng được ghi rõ nghĩa là đã xóa. facts.unknown và blockers cho biết chưa rõ hoặc cần kiểm tra lại, không được dùng nguyên văn hồ sơ cũ, kế hoạch quyển, suy đoán hay giá trị rỗng để bù đắp.

Quyển hiện tại, hồ sơ đã có và kế hoạch tham gia trong quyển:
{entity_context}

Hãy sinh nhân vật mới đúng theo new_count, đồng thời lập kế hoạch tham gia quyển này cho từng nhân vật đã có trong selected_existing_ids. Ưu tiên tái sử dụng nhân vật đã có; character_id của nhân vật đã có phải dùng ID chính thức trong ngữ cảnh, còn profile và initial_facts bắt buộc là null, không được thông qua kế hoạch mà sinh ra hay ghi đè bất kỳ dữ kiện thực tế nào. Khi có trạng thái của quyển này thì state_expected_version phải bằng version của nó, nếu không thì để null.
character_id và state_expected_version của nhân vật mới là null; profile chỉ gồm mục lục thân phận và tư liệu thiết kế câu chuyện, is_core_character=false; dữ kiện ban đầu thực tế chỉ được gửi một lần qua initial_facts riêng biệt. candidate_ref dùng định danh chữ thường tiếng Anh, duy nhất trong lô này.

state chỉ bao gồm participation_scope, current_goal, start_state, planned_end_state, relationship_focus_ids, arc_progress. current_goal là mục tiêu theo kế hoạch của quyển này, start_state là điểm khởi đầu theo kế hoạch, planned_end_state là trạng thái dự kiến khi kết quyển, arc_progress là tiến độ kế hoạch; tất cả đều không được coi là dữ kiện đã xảy ra. relationship_focus_ids của nhân vật mới bắt buộc để trống; nhân vật đã có chỉ được tham chiếu các quan hệ đang hoạt động liên quan tới chính nhân vật đó trong ngữ cảnh.

profile.initial_state và relationship_with_protagonist của nhân vật mới mô tả thiết kế lần xuất hiện và ý đồ xây dựng quan hệ; growth_direction, arc_seed mô tả hướng phát triển dự kiến; conflict_with_mainline mô tả sự liên can giữa hành động, mục tiêu hoặc lựa chọn với tuyến truyện chính, không có nghĩa là bắt buộc thù địch; story_function mô tả chức năng cụ thể trong tình tiết, không thay bằng nhãn trừu tượng. Mười lăm hạng mục tư liệu thực tế (gồm thân phận, ngoại hình, năng lực, tâm lý, hoàn cảnh công khai/ẩn và mục tiêu thực tế) thuộc về initial_facts, không đưa vào profile hay state.
Trong initial_facts chỉ soạn những dữ kiện ban đầu có căn cứ từ thiết kế hoặc từ lần xuất hiện trong quyển này, đủ để tác giả xác nhận rõ ràng, và phải có ít nhất một tư liệu xác định. Trường chưa rõ thì điền null (ở chế độ JSON thông thường cũng có thể bỏ qua); null chỉ có nghĩa là không nhận dữ kiện đó, khi đưa vào xem trước vẫn giữ trạng thái chưa rõ. Chỉ dùng chuỗi rỗng hoặc mảng rỗng khi căn cứ nói rõ là để trống. Khi không có căn cứ về hoàn cảnh ẩn thì hidden_state là null, không được bịa bí mật, cũng không được điền chuỗi rỗng. Với nhân vật đã có, dù dữ kiện chưa rõ, cũng chỉ lập kế hoạch cho quyển này, không cung cấp đối tượng initial_facts.
Hợp tác bình thường, cứu giúp, quan hệ thân thuộc hoặc ràng buộc nghề nghiệp không tự động có nghĩa là tổ chức bí mật, thân phận ẩn, thao túng sau hậu trường hay biết trước sự việc. Không được ghi sớm kết cục cuối quyển, quan hệ theo kế hoạch hoặc thay đổi thân phận vào dữ kiện ban đầu.

Tư liệu của lần này do AI sắp xếp, lý do không sử dụng, các mục còn thiếu và đề xuất bổ sung:
{prepared_context}
Hãy sinh chặt chẽ theo nội dung còn hiệu lực và cốt truyện của cấp cha, không lặp lại hay ghi đè nội dung đã lưu; dữ kiện và trách nhiệm chỉ được xét từ nội dung của thực thể hiện tại.
