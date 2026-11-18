Căn cứ vào cốt truyện vòng truyện vừa được sinh, hãy hoàn thiện quy hoạch hiện có của vòng truyện này. Chỉ xuất planning, coverage_notes và source_conflicts, không xuất lại plot.

Mục tiêu hiện tại là vòng truyện, nên planning chỉ dùng các trường của vòng truyện: goal, start_state, end_state, key_beats, continuity_notes, target_chapter_count, target_word_count, character_ids, faction_ids, location_ids, item_ids, rule_ids. Không xuất các trường của quyển là premise, major_conflict, key_turning_points, cũng không vì quy hoạch của quyển cha có những trường đó mà dùng lại chúng.

Chỉ hoàn thiện goal, key_beats và continuity_notes, nêu rõ hành động của nhân vật, cách thúc đẩy nhân quả và khớp nối trước sau. Start_state, end_state, ngân sách và năm mảng ID thực thể vốn có của vòng truyện hiện tại phải được xuất đầy đủ và giữ nguyên văn; không được xóa tham chiếu hay thêm ID chưa từng được đọc. Khi đã có cấp dưới thì những văn bản quy hoạch này chỉ mang tính kiến nghị, server chỉ lưu cốt truyện.

coverage_notes nêu ngắn gọn cốt truyện đã phủ các nhịp của phần này như thế nào và tiếp nối phần sau ra sao; nếu phát hiện xung đột thật giữa quy hoạch vòng truyện cũ và cốt truyện mới thì chỉ rõ, không tuyên bố là đã tự động giải quyết. Không coi quy hoạch quyển cấp trên như quy hoạch vòng truyện cần xuất lần này.

source_conflicts báo cáo các nghi vấn xung đột giữa phần văn bản chính đã viết và quy hoạch cũ đã lưu mà bạn thực sự nhận được trong lần này, tối đa 12 mục. Mỗi mục gồm message, saved_text, old_plan; cả hai phía đều phải điền resource_type, id, field, quote. quote phải là nguyên văn từng chữ, liên tục và không rỗng trong trường tương ứng (tối đa 2000 chữ), message tối đa 1000 chữ. saved_text chỉ tham chiếu excerpt hoặc content của chapter; old_plan tham chiếu các trường cụ thể nằm dưới plot hoặc planning, hoặc nguyên văn như summary, của tiểu thuyết, quyển, vòng truyện, cảnh hay chương đã lưu; với trường dạng mảng hãy dùng đường dẫn bắt đầu từ 0, ví dụ planning.key_beats.0.

Chỉ được tham chiếu nguyên văn mà writing_context thực sự mang tới và các phân đoạn mà server thực sự đọc trong prepared_context.previous_text. Plot cũ của mục tiêu hiện tại đã bị loại khỏi writing_context nên không được hư cấu bổ sung; các ý kiến tổng hợp như boundaries, coverage trong prepared_context, cùng plot và planning vừa sinh đều không phải nguồn đã lưu. Không được đánh tráo "ứng viên mới khác quy hoạch cũ" thành "hai nguồn đã lưu xung đột với nhau". Nghi vấn thật nhưng chưa chắc chắn thì có thể báo cáo để tác giả kiểm tra, không tuyên bố đã giải quyết, không thay tác giả ấn định thứ tự ưu tiên nguồn vĩnh viễn. Khi không phát hiện mục nào đáng báo cáo thì xuất []; khi chưa hoàn thành báo cáo thì xuất null, không được mô tả null là không có xung đột. Hiện bạn chỉ thấy phân đoạn cuối của các chương gần trước cùng các phân đoạn chương trước đọc thêm trong lần này, không được tuyên bố đã kiểm tra toàn bộ văn bản chính đã viết của quyển hiện tại.

Quy hoạch vòng truyện gốc và ranh giới:
{writing_context}

Cốt truyện vòng truyện:
{plot}

Tư liệu tổng hợp lần này:
{prepared_context}
