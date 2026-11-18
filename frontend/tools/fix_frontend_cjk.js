// Dich thu cong cac chuoi loi hien thi cho nguoi dung trong ma frontend (con lai sau i18n).
// Thay the literal (split/join), khong dung regex voi chuoi co ky tu dac biet.
// Cac gia tri DATA (vi du "第一人称" cua NARRATIVE_POV_OPTIONS, WRITING_DEFAULT_TITLES/NAMES
// trong TaskFlowForm) CO Y GIU NGUYEN vi backend luu va so sanh bang chuoi do.
// Cach dung: node frontend/tools/fix_frontend_cjk.js
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "src");

const EDITS = [
  [
    "components/writing/entity-graph/graphModel.ts",
    [
      ['"实体缺少稳定业务 ID，已跳过。"', '"Thực thể thiếu ID nghiệp vụ ổn định, đã bỏ qua."'],
      ['"发现重复节点业务 ID，保留首条记录。"', '"Phát hiện ID nghiệp vụ nút trùng lặp, giữ bản ghi đầu tiên."'],
      ['"势力层级无法识别，节点仍保留以便未来扩展。"', '"Cấp thế lực không xác định được, nút vẫn được giữ để mở rộng sau này."'],
      ['"关系缺少稳定业务 ID，已跳过。"', '"Quan hệ thiếu ID nghiệp vụ ổn định, đã bỏ qua."'],
      ['"自引用关系不会进入图谱。"', '"Quan hệ tự tham chiếu sẽ không vào đồ thị."'],
      ['"关系端点不存在，已跳过且未创建虚构节点。"', '"Điểm cuối quan hệ không tồn tại, đã bỏ qua và không tạo nút hư cấu."'],
      ['"发现重复关系业务 ID，保留首条记录。"', '"Phát hiện ID nghiệp vụ quan hệ trùng lặp, giữ bản ghi đầu tiên."'],
    ],
  ],
  [
    "lib/api.ts",
    [
      ['"SSE 响应没有可读取的响应体"', '"Phản hồi SSE không có phần thân để đọc"'],
      ['`SSE 事件 ${currentEventType} 的 data 不是合法 JSON`', '`data của sự kiện SSE ${currentEventType} không phải JSON hợp lệ`'],
      ['"SSE 连接中断时仍有未结束的事件"', '"Kết nối SSE gián đoạn khi vẫn còn sự kiện chưa kết thúc"'],
      ['"SSE 连接读取中断"', '"Đang đọc kết nối SSE thì gián đoạn"'],
      ['"SSE 事件必须以空行结束完整帧"', '"Mỗi sự kiện SSE phải kết thúc bằng một dòng trống"'],
      ['"SSE 响应的 Content-Type 必须为 text/event-stream"', '"Content-Type của phản hồi SSE phải là text/event-stream"'],
      ['`SSE 收到未声明的业务事件: ${event}`', '`SSE nhận được sự kiện nghiệp vụ chưa khai báo: ${event}`'],
      ['`SSE 收到重复终态: ${event}`', '`SSE nhận trạng thái kết thúc trùng lặp: ${event}`'],
      ['`SSE 在终态 ${terminalEvent} 之后仍收到业务事件: ${event}`', '`SSE vẫn nhận sự kiện nghiệp vụ sau trạng thái kết thúc ${terminalEvent}: ${event}`'],
      ['"SSE 连接在收到 done 或 error 终态前关闭"', '"Kết nối SSE đóng trước khi nhận trạng thái kết thúc done hoặc error"'],
    ],
  ],
  [
    "components/writing/characters/useCharacterBatchCreation.ts",
    [
      ['"另一页已处理这批保存，请重新打开查看最新结果"', '"Một trang khác đã xử lý lô lưu này, hãy mở lại để xem kết quả mới nhất"'],
      ['"保存回复不完整，请保留这批内容并重试原请求"', '"Phản hồi lưu không đầy đủ, hãy giữ nội dung lô này và thử lại yêu cầu gốc"'],
    ],
  ],
  [
    "components/writing/factions/factionFactBatch.ts",
    [
      ['"所选势力候选已变化，请保留原稿"', '"Ứng viên thế lực đã chọn thay đổi, hãy giữ bản thảo gốc"'],
      ['"所选关系候选已变化，请保留原稿"', '"Ứng viên quan hệ đã chọn thay đổi, hãy giữ bản thảo gốc"'],
    ],
  ],
  [
    "components/writing/factions/factionFactPreparation.ts",
    [
      ['"另一页已保存或更新这份草稿，请重新打开查看；本页文字仍会保留"', '"Một trang khác đã lưu hoặc cập nhật bản nháp này, hãy mở lại để xem; nội dung trang này vẫn được giữ"'],
      ['"请先填写或修改要保存的资料"', '"Hãy điền hoặc sửa tư liệu cần lưu trước"'],
      ['"作者确认这处剧情位置的势力资料"', '"Tác giả xác nhận tư liệu thế lực tại vị trí cốt truyện này"'],
      ['"这些资料来自不同的剧情记录，请从对应历史记录更正；编辑内容已保留"', '"Những tư liệu này đến từ các bản ghi cốt truyện khác nhau, hãy sửa từ bản ghi lịch sử tương ứng; nội dung đã sửa vẫn được giữ"'],
    ],
  ],
];

let applied = 0;
const problems = [];
for (const [rel, pairs] of EDITS) {
  const p = path.join(SRC, rel);
  let text = fs.readFileSync(p, "utf8");
  for (const [oldStr, newStr] of pairs) {
    if (!text.split(oldStr).length) problems.push(rel + " khong tim thay: " + oldStr);
    const before = text;
    text = text.split(oldStr).join(newStr);
    if (before === text) problems.push(rel + " KHONG THAY: " + oldStr);
    else applied += 1;
  }
  fs.writeFileSync(p, text, "utf8");
}
console.log("applied=" + applied + " problems=" + problems.length);
for (const x of problems) console.log("  " + x);
