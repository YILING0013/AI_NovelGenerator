Dựa trên cốt truyện quyển vừa được tạo, hãy hoàn thiện kế hoạch hiện có của quyển này. Chỉ xuất planning, coverage_notes và source_conflicts, không xuất lại plot.

Mục tiêu hiện tại là quyển, nên planning chỉ dùng các trường của quyển: premise, major_conflict, key_turning_points, start_state, end_state, target_chapter_count, target_word_count. Chỉ hoàn thiện tiền đề câu chuyện, xung đột chính và các bước ngoặt then chốt; start_state, end_state và ngân sách vốn có phải được giữ nguyên. Không xuất các trường của vòng truyện là goal, key_beats, continuity_notes hay mảng ID thực thể. Khi đã có cấp dưới, những dòng kế hoạch này chỉ mang tính gợi ý, server chỉ lưu cốt truyện.

coverage_notes nêu ngắn gọn cốt truyện bao phủ các bước ngoặt then chốt của quyển này và nối tiếp sang quyển sau ra sao; khi phát hiện xung đột thực sự giữa kế hoạch quyển cũ và cốt truyện mới, hãy chỉ rõ, không được nói là đã tự động giải quyết.

source_conflicts báo cáo những xung đột nghi nhận giữa phần văn bản chính đã viết và kế hoạch cũ đã lưu mà lần này thực sự nhận được, tối đa 12 mục. Mỗi mục gồm message, saved_text, old_plan; cả hai bên đều phải điền resource_type, id, field, quote. quote phải là câu nguyên văn, liên tiếp từng chữ và không rỗng trong trường tương ứng (tối đa 2000 chữ), message tối đa 1000 chữ. saved_text chỉ trích excerpt hoặc content của chapter; old_plan trích các trường cụ thể dưới plot, planning hoặc nguyên văn trong summary của tiểu thuyết, quyển, vòng truyện, cảnh hay chương đã lưu; với trường dạng mảng hãy dùng đường dẫn bắt đầu từ 0, ví dụ planning.key_beats.0.

Chỉ được trích nguyên văn mà writing_context thực sự mang lại và các đoạn mà server thực sự đọc trong prepared_context.previous_text. Plot cũ của mục tiêu hiện tại đã được gỡ khỏi writing_context, không được bịa bù; các ý kiến chuẩn bị như boundaries, coverage trong prepared_context và plot, planning vừa tạo đều không phải nguồn đã lưu. Không được giả mạo "ứng viên mới khác kế hoạch cũ" thành "hai nguồn đã lưu xung đột nhau". Với nghi vấn thực sự mà chưa chắc chắn, có thể báo cáo và giao tác giả đối chiếu, không tuyên bố là đã giải quyết, không thay tác giả ấn định thứ tự ưu tiên nguồn vĩnh viễn. Khi không phát hiện mục nào đáng báo cáo thì xuất []; khi báo cáo chưa hoàn thành thì xuất null, không được mô tả null là không có xung đột. Hiện tại chỉ thấy đoạn cuối của những chương trước đó gần nhất cùng các đoạn chương trước mà lần này đọc thêm, không được nói là đã kiểm tra toàn bộ phần văn bản chính đã viết của quyển này.

Kế hoạch và ranh giới của quyển cũ:
{writing_context}

Cốt truyện quyển:
{plot}

Tư liệu đã chuẩn bị lần này:
{prepared_context}
