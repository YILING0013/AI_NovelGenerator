Bạn là một nhà thiết kế quy tắc thế giới cho tiểu thuyết dài tập. Hãy biên tập những dữ kiện tiểu thuyết đã được xác nhận cùng bản tóm tắt thế giới quan thành các ứng viên quy tắc cốt lõi để tác giả xem xét từng điều một.

unlocated_profile của nhân vật chỉ là nguyên văn hồ sơ chính chưa gắn vị trí cốt truyện, có thể dùng cho việc thiết kế toàn sách, nhưng không được dựa vào đó mà khẳng định dữ kiện đã xảy ra ở chương nào.

Tóm tắt tiểu thuyết (trong đó worldview chỉ là tóm tắt sáng tác, không phải quy tắc chính thức):
{novel_summary}

Nhân vật chính đang hoạt động (chỉ được tham chiếu character_id trong danh sách này):
{protagonists}

Nhân vật chính thức đang hoạt động (chỉ được tham chiếu character_id trong danh sách này):
{characters}

Thế lực cốt lõi đang hoạt động (chỉ được tham chiếu faction_id trong danh sách này):
{factions}

Quan hệ giữa các thế lực cốt lõi đang hoạt động:
{faction_relations}

Quy tắc chính thức đang hoạt động đã có (cấm sinh ra nội dung trùng ngữ nghĩa hoặc trùng tên):
{existing_world_rules}

Tham số số lượng lần này (null/None do AI tự quyết): {core_rule_count}
Có cho phép bổ sung dần trên các quy tắc đã có hay không: {allow_incremental}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Khi core_world_rules chỉ định một số nguyên, số lượng phải đúng bằng yêu cầu lần này; mỗi quy tắc đều phải khả thi, nêu rõ ngoại lệ, cách thực thi, cái giá hoặc hậu quả.
2. Đầu ra chỉ là ứng viên; không được tuyên bố đã lưu, đã có hiệu lực hay đã trở thành dữ kiện của tiểu thuyết; không được viết lại bản tóm tắt worldview.
3. candidate_ref phải dùng các tham chiếu trong lô như rule_candidate_1, rule_candidate_2 và phải duy nhất; không được xuất ID rule_ chính thức.
4. scope_type chỉ có thể là global, faction hoặc character; cấm xuất location, quyển, chương, cảnh, sự kiện hay phần văn bản chính.
5. Hãy xác định quy tắc thực sự có hiệu lực với những ai trước, rồi chọn một scope_type duy nhất và điền scope_entity_ids đúng nghiêm ngặt theo các yêu cầu sau:
   - global: dùng cho quy tắc chung toàn cục; scope_entity_ids bắt buộc phải là []. Ngay cả khi phần văn bản nhắc đến nhân vật hay thế lực cụ thể cũng không được thêm ID của chúng.
   - faction: dùng cho quy tắc của một thế lực xác định; scope_entity_ids phải là mảng khác rỗng và mỗi phần tử phải lấy nguyên văn từ faction_id trong "Thế lực cốt lõi đang hoạt động", cấm chứa bất kỳ character_id nào.
   - character: dùng cho quy tắc của một nhân vật xác định; scope_entity_ids phải là mảng khác rỗng và mỗi phần tử phải lấy nguyên văn từ character_id trong "Nhân vật chính đang hoạt động" hoặc "Nhân vật chính thức đang hoạt động", cấm chứa bất kỳ faction_id nào.
   - Một mảng chỉ được chứa ID thuộc kiểu đã chọn; không được trộn ID nhân vật với ID thế lực, không được trùng, không được đặt tên, và không được đổi tiền tố để biến loại ID này thành loại khác.
   - scope_entity_ids chỉ biểu thị đối tượng áp dụng của quy tắc, không phải danh sách toàn bộ nhân vật và thế lực có liên quan trong phần văn bản. Quy tắc nhắm vào một thế lực và do một nhân vật kích hoạt thì nên chọn faction và chỉ điền ID của thế lực đó; điều kiện về nhân vật hãy viết vào statement hoặc exceptions. Quy tắc chỉ có hiệu lực với một nhân vật thì chọn character, không được vì nhân vật đó thuộc một thế lực mà thêm ID thế lực.
   - Ví dụ (chỉ khi các ID này thật sự tồn tại trong dữ liệu vào tương ứng): scope_type="faction" đi với scope_entity_ids=["fac_000001"]; scope_type="character" đi với scope_entity_ids=["char_000002"]. Dù chọn kiểu nào cũng cấm xuất ["fac_000001", "char_000002"]; không được chép nguyên ID trong ví dụ.
6. Mỗi ứng viên phải chứa và chỉ chứa candidate_ref, name, category, statement, scope_type, scope_entity_ids, enforcement, exceptions, costs_and_consequences, priority, tags.
7. Mỗi phần tử trong exceptions phải chứa và chỉ chứa condition và effect; mọi mảng phải được viết dưới dạng mảng JSON, khi không có nội dung thì dùng mảng rỗng.
8. Tên và ngữ nghĩa quy tắc không được trùng với quy tắc đang hoạt động đã có hoặc với ứng viên khác trong cùng lô; không được bịa ID nhân vật hay thế lực không có trong dữ liệu vào.
9. Trước khi xuất, kiểm tra từng điều: mảng ID của global phải rỗng; mọi ID của faction phải đến từ thế lực trong dữ liệu vào; mọi ID của character phải đến từ nhân vật trong dữ liệu vào; không có ID nào trùng. Nếu phát hiện trộn lẫn, hãy sửa theo đối tượng áp dụng thật sự của quy tắc, không được đổi thành global chỉ để qua kiểm tra. Chỉ xuất kết quả sau khi kiểm tra, không xuất quá trình kiểm tra.

Khi tham số số lượng core_rule_count là null hoặc None, hãy tự quyết định số lượng theo nhu cầu thật sự của câu chuyện, tối thiểu 1 và tối đa 20; không coi giới hạn trên như mục tiêu, cũng không mặc nhiên cho đủ số. Khi có chỉ định một số nguyên, tuân thủ nghiêm ngặt số lượng đó.
