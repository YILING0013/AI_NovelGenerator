Bạn là một chuyên gia thiết kế thế giới quan dày dạn kinh nghiệm cho tiểu thuyết dài tập, đang tạo "thế lực cốt lõi cấp toàn thư" và "quan hệ cốt lõi giữa các thế lực" cho một bộ tiểu thuyết đã được lưu.

Thông tin cơ bản của tiểu thuyết:
Tiêu đề: {title}
Thể loại: {genre}
Giọng điệu: {tone}
Đối tượng độc giả: {target_audience}
Ý tưởng cốt lõi: {core_idea}
Dung lượng: khoảng {number_of_chapters} chương (mỗi chương {words_per_chapter} chữ)
Thẻ: {tags_json}

Hạt nhân câu chuyện:
{core_seed}

Giới thiệu sơ lược:
{summary}

Thế giới quan:
{worldview}

Phong cách viết: {writing_style}
Góc nhìn kể chuyện: {narrative_pov}
Bối cảnh thời đại: {era_background}

Văn bản cốt truyện chính:
{plot}

Thế lực cốt lõi đã lưu (chỉ dùng làm ngữ cảnh và điểm nối quan hệ tham khảo, cấm xuất lặp lại vào core_factions):
{existing_core_factions_json}

Tham số tạo lần này:
- Số thế lực mới mục tiêu (null/None để AI tự quyết): {faction_count}
- Chiến lược tạo bổ sung:
{generation_strategy}

Mục tiêu tạo:
1. Chỉ tạo các thế lực cốt lõi cấp toàn thư có tác động lâu dài tới xung độtcủa tuyến chính và vị trí đứng của các nhân vật chính.
2. Khi chỉ định một số nguyên, số lượng core_factions của lần này phải bằng đúng "số thế lực mới mục tiêu", và chỉ được xuất ra các thế lực mới.
3. Thế lực cốt lõi không phải bách khoa thư thế giới, đừng tạo tổ chức địa phương cấp quyển, đội tạm thời, nhóm theo nhiệm vụ hoặc tổ chức của sự kiện trong chương.
4. Giai đoạn này nhân vật chưa được tạo, tuyệt đối cấm xuất danh sách nhân vật,sự thuộc về của nhân vật, thân phận nhân vật, liên kết nhân vật, chức vụ phái hệ của nhân vật.
5. Nếu văn bản cốt truyện chính đã xuất hiện tên người, cũng chỉ được coi đó là manh mối cốt truyện, không tạo thông tin nhân vật xoay quanh người đó.
6. Mỗi thế lực phải phục vụ trực tiếp tuyến truyện chính, nêu rõ nó cụ thể mang lại trợ giúp gì hoặc gây trở ngại gì trong nhiều quyển, không nhất thiết thế lực nào cũng phải gánh việc đối đầu hay âm mưu.
7. faction_relations có thể để trống; nếu xuất quan hệ, điểm đầu thuộc thế lực mới chỉ được dùng faction_ref, điểm đầu thuộc thế lực đã có chỉ được dùng faction_id chính thức có trong đầu vào, mỗi quan hệ phải nối ít nhất một thế lực mới của lần này.
8. Thế lực không được thiết lập quan hệ trực tiếp trong lô này không được xuất hiện trong source hoặc target của faction_relations, số lượng phải khớp với tham số tạo; các thế lực mới còn lại phải có quan hệ với thế lực cũ và mới. Ở đây chỉ giới hạn quan hệ xuất ra của lô này, không có nghĩa là thế lực đó vĩnh viễn độc lập, không thuộc về thế lực nào hoặc tồn tại ẩn.
9. Nếu người dùng cung cấp độ chính trực hoặc độ lượng hóa quan hệ, phải thi hành theo chiến lược tạo bổ sung, không viết phần mô tả của thanh trượt vào văn bản trường.
10. Hãy thiết kế bí mật và mâu thuẫn dựa theo thiết lập sẵn có của tiểu thuyết và yêu cầu rõ ràng của người dùng; bản thân tổ chức cứu trợ thông thường, nghề nghiệp công cộng hay quan hệ thân nhân không phải là căn cứ để cho rằng đó là tổ chức bí mật, thân phận bí mật hay chuỗi lợi ích đứng sau màn. Bí mật và mâu thuẫn có căn cứ thì có thể giữ lại và triển khai, không vì muốn điền đủ trường mà bịa ra bí mật.

Mỗi thế lực cốt lõi phải bao gồm:
- faction_ref: tham chiếu ổn định và duy nhất trong phạm vi các ứng viên của lần này, dạng như faction_001, không được xuất ID chính thức dạng fac_
- name: tên thế lực
- faction_type: loại thế lực
- positioning: chức trách thực tế của thế lực trong thế giới, cụ thể phụ trách việc gì
- public_stance: tuyên bố hoặc chủ trương công khai ra bên ngoài, không lặp lại chức trách hay khẩu hiệu mục tiêu để điền cho đủ
- core_goal: lợi ích, yêu sách hoặc kết quả cụ thể mà thế lực muốn giành lấy, không yêu cầu phải trái ngược với tuyên bố công khai
- hidden_goal: mục tiêu chưa công khai, phải có thiết lập hoặc yêu cầu của người dùng làm hậu thuẫn; không có căn cứ thì để chuỗi rỗng, không vì muốn điền đủ trường mà bịa ra bí mật
- resources_and_advantages: 1 đến 6 tài nguyên hoặc ưu thế
- organization_style: khí chất tổ chức hoặc phong cách hành động
- core_values: 1 đến 6 giá trị cốt lõi
- conflict_with_mainline: sự trợ giúp cụ thể mang lại hoặc trở ngại cụ thể gây ra cho hành động của tuyến truyện chính
- is_public: có tồn tại công khai hay không
- influence_scope: phạm vi ảnh hưởng
- expandability: hướng phát triển có thể có về sau, không được coi như sự kiện đã xảy ra lúc mở đầu
- tags: thẻ của thế lực, có thể là mảng rỗng

Mỗi quan hệ giữa các thế lực phải bao gồm:
- relation_ref: tham chiếu ổn định và duy nhất trong phạm vi các ứng viên của lần này, dạng như relation_001
- source/target: phân biệt nghiêm ngặt hai điểm đầu; thế lực mới dùng {"kind":"candidate","faction_ref":"faction_001"}, thế lực đã có dùng {"kind":"existing","faction_id":"fac_000001"}
- relation_type: chỉ được dùng hostile/allied/cold_war/dependent/subordinate/trade_partner/secret_cooperation/historical_enemy
- current_state: trạng thái quan hệ lúc mở đầu câu chuyện, không viết trước liên minh, phản bội hay kết cục về sau
- core_conflict: mâu thuẫn cốt lõi trong quan hệ
- hidden_tension: mâu thuẫn sâu chưa bùng phát, có thể để chuỗi rỗng
- possible_change: biến đổi có thể xảy ra về sau, viết dưới dạng kế hoạch hoặc khả năng, không viết thành sự kiện đã xảy ra
- intensity: cường độ quan hệ từ 1 đến 5
- is_active: có hiệu lực ở thời điểm hiện tại hay không

Khi tham số số lượng faction_count là null hoặc None, bạn tự quyết định số lượng theo nhu cầu thực tế của câu chuyện, tối thiểu 1 và tối đa 6; không coi mức trần là mục tiêu, cũng không mặc định phải cho đủ số lượng. Khi chỉ định một số nguyên thì tuân thủ nghiêm ngặt số lượng đó.
