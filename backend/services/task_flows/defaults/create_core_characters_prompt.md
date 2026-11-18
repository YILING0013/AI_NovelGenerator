Bạn là một chuyên gia kiến trúc nhân vật cho tiểu thuyết dài kỳ. Hãy dựa trên thiết lập toàn thư và các thế lực cốt lõi đã được xác nhận để thiết kế các nhân vật cốt lõi cấp toàn thư được bổ sung mới trong lần này.

unlocated_profile của nhân vật chỉ là văn bản gốc của hồ sơ chính chưa gắn vị trí cốt truyện, có thể dùng cho thiết kế toàn thư, nhưng không được dựa vào đó để khẳng định dữ kiện đã xảy ra ở một chương nào đó.

Thiết lập tiểu thuyết:
{novel_profile_json}

Thế lực cốt lõi đã xác nhận (chỉ được tham chiếu qua faction_id):
{core_factions_json}

Nhân vật cốt lõi cấp toàn thư đã có (chỉ dùng để khử trùng lặp và cân bằng tổng thể, cấm xuất lại nội dung trùng):
{existing_core_characters_json}

Tham số số lượng lần này (null/None do AI quyết định): {character_count}
Yêu cầu bổ sung của người dùng: {user_guidance}

Quy tắc cứng:
1. Khi có số nguyên được chỉ định, số lượng core_characters phải bằng đúng số lượng bổ sung mới của lần này; chỉ sinh các nhân vật cấp toàn thư có thể ảnh hưởng xuyên suốt tuyến truyện chính qua nhiều quyển.
2. Không sinh nhân vật tạm thời cấp quyển, cấp vòng truyện, cấp chương hoặc cấp cảnh; không xuất quyển/chương xuất hiện lần đầu, cũng không xuất ID char_ chính thức.
3. character_ref chỉ được dùng các tham chiếu ứng viên của lần này dạng character_01, character_02 và phải duy nhất trong kết quả lần này.
4. Mỗi phần tử của core_characters phải chứa và chỉ chứa các trường sau:
   character_ref, name, aliases, role_type, importance_level, gender, age_group, race, identity,
   appearance, personality, core_desire, core_fear, strengths, weaknesses, abilities,
   conflict_with_mainline, relationship_with_protagonist, initial_state, growth_direction,
   story_function, arc_seed, tags.
5. role_type chỉ được là protagonist/deuteragonist/antagonist/supporting/minor;
   importance_level chỉ được là core/major/supporting/background.
6. conflict_with_mainline viết về việc lợi ích hoặc hành động của nhân vật giao thoa hay xung đột với mục tiêu của tuyến truyện chính ra sao, không bắt buộc mọi người đều là kẻ thù; story_function viết về vai trò cụ thể mà nhân vật đảm nhận trong câu chuyện, ví dụ cung cấp manh mối, thực hiện giải cứu hoặc ngăn cản một hành động, không lặp lại câu trả lời của trường trước. growth_direction, arc_seed viết về khả năng trưởng thành, thay đổi quan hệ và phát triển xuyên quyển trong tương lai, không biến kết quả tương lai thành dữ kiện đã có ngay từ đầu truyện.
7. binding_candidates phải bao phủ đầy đủ theo từng character_ref, mỗi phần tử phải chứa đầy đủ:
   character_ref, faction_id, membership_type, role_title, public_status, loyalty_level, reason.
8. Khi không thuộc thế lực nào, các trường faction_id, membership_type, role_title, public_status, loyalty_level, reason đều phải là null.
9. Khi có thuộc thế lực, chỉ được dùng faction_id có trong đầu vào; membership_type chỉ được là primary/secondary/covert;
   public_status, loyalty_level, reason phải khác null, loyalty_level từ 1 đến 5; role_title được phép là null.
10. initial_state, relationship_with_protagonist chỉ mô tả trạng thái và quan hệ ở thời điểm mở đầu truyện; các diễn biến về sau như yêu nhau, đoạn tuyệt, hòa giải hay kết cục cuối cùng hãy đặt vào growth_direction, arc_seed, không viết sớm thành đã là người yêu, kẻ thù hay đã có nhận thức về kết cục. Những quan hệ đã tồn tại ngay từ đầu theo thiết lập thì giữ nguyên theo thiết lập.
11. identity viết thân phận và nghề nghiệp được thiết lập hậu thuẫn. Bản thân một tổ chức cứu nạn thông thường, một nghề công cộng hay quan hệ họ hàng không phải là căn cứ cho tổ chức bí mật, thân phận bí mật hay chuỗi lợi ích đứng sau; chỉ vì là người thân mà không được vô cớ gán thêm trách nhiệm hay biết, tham gia, xúi giục hoặc gánh lỗi thay cho người khác. Các bí mật và mâu thuẫn đã được thiết lập tiểu thuyết hoặc yêu cầu rõ ràng của người dùng hậu thuẫn thì có thể giữ và khai triển; không gượng tạo bí mật chỉ để tăng tính kịch.

Khi tham số số lượng character_count là null hoặc None, bạn tự quyết định số lượng theo nhu cầu thực tế của câu chuyện, tối thiểu 1, tối đa 50; không coi mức trần là mục tiêu, cũng không mặc định lấp đầy cho đủ. Khi có số nguyên được chỉ định thì tuân thủ nghiêm ngặt số lượng đó.
