# Hướng dẫn sử dụng — Việt Tiểu Thuyết (AI Novel Generator bản tiếng Việt)

Tài liệu này dành cho người **không biết lập trình**. Bạn chỉ cần làm theo thứ tự.

- Website làm việc: **http://127.0.0.1:3300**
- Backend (máy chủ nội bộ): http://127.0.0.1:8200 (không cần mở)
- Cơ sở dữ liệu: MongoDB ngay trên máy bạn, cổng 27017
- Ngôn ngữ giao diện: **Tiếng Việt** (có thể đổi sang 中文 / English ở góc trên bên phải)

> Mọi dữ liệu truyện nằm trong thư mục `mongodata` trên máy bạn. Không cần internet
> ngoài việc gọi API của nhà cung cấp AI (OpenAI / Gemini / Claude / DeepSeek…).

---

## Phần 1 — Cài đặt một lần (chỉ làm lần đầu)

### 1.1. Cài hai chương trình nền

| Chương trình | Tải về | Kiểm tra đã cài |
|---|---|---|
| Python 3.13 | https://www.python.org/downloads/ (bỏ chọn "Use admin privileges" nếu máy công ty) | `python --version` hiện `Python 3.13.x` |
| Node.js 22 hoặc 24 | https://nodejs.org/en/download | `node --version` hiện `v22+` |

Mở **Windows PowerShell** (nhấn phím Windows, gõ `powershell`) rồi chạy hai lệnh trên để kiểm tra.

### 1.2. Mở thư mục chương trình

Toàn bộ chương trình nằm ở:

```text
e:\laragon\www\viettieuthuyet\app
```

Trong thư mục này đã có sẵn:

```text
start-all.bat        <- bấm đúp để chạy  (quan trọng nhất)
stop-all.bat         <- bấm đúp để tắt
status.bat           <- xem đang chạy hay đã tắt
scripts\stack.ps1    <- script điều khiển 3 dịch vụ
tools\m\bin\mongod.exe        <- MongoDB 8.0 đi kèm (không cần cài đặt)
frontend\                     <- giao diện website
backend\                      <- trí tuệ nhân tạo + lưu trữ
HuongDanSuDung.md             <- tài liệu này
```

### 1.3. Cài phần nền cho chương trình (chạy 1 lần, mất ~5-15 phút)

Mở PowerShell, dán từng dòng một:

```powershell
cd e:\laragon\www\viettieuthuyet\app

# 1) Tạo môi trường Python riêng và cài thư viện
& 'E:\laragon\bin\python\python-3.13\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) Cài thư viện giao diện web
Set-Location frontend
& 'D:\nodejs\npm.cmd' ci
& 'D:\nodejs\npm.cmd' run build
Set-Location ..
```

Dấu hiệu thành công: lệnh `run build` in ra bảng danh sách trang (`/[locale]/settings`,
`/[locale]/writing/...`) và **không** có dòng chữ `Error`.

> Nếu máy bạn không có Python ở `E:\laragon\bin\python\python-3.13`, thay đường dẫn đầu
> tiên bằng `python -m venv .venv`.

### 1.4. Cấu hình sẵn (đã làm hộ bạn, chỉ cần kiểm tra)

File `app\user_data\config\config.yaml` đã trỏ MongoDB cục bộ:

```yaml
mongodb_url: "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mongo_database_name: "novel_generator"
```

Không cần sửa gì thêm.

---

## Phần 2 — Bắt đầu làm việc hằng ngày

### Bước 1: Bấm đúp `start-all.bat`

Cửa sổ đen hiện ra và bạn sẽ thấy 4 dòng:

```text
[1/4] MongoDB...        [OK] MongoDB (PID ..., cong 27017)
[2/4] Backend...        [OK] Backend (PID ..., cong 8200)
[3/4] Frontend...       [OK] Frontend (cong 3300)
[4/4] Mo trinh duyet...
```

Trình duyệt tự mở tại **http://127.0.0.1:3300**. Lần mở đầu có thể mất 10–30 giây.

Nếu dòng nào báo `[LOI]`, xem mục **Phần 6 — Xử lý lỗi**.

### Bước 2: Kết nối AI (chỉ làm một lần)

1. Bấm **biểu tượng bánh răng** (góc trên bên phải) → trang **Cài đặt**.
2. Chọn mục **Nhà cung cấp mô hình** trong thanh bên trái.
3. Bấm **Thêm nhà cung cấp**, điền:
   - **Kiểu giao diện**: `openai` (dùng được cho OpenAI, DeepSeek, và đa lớn dịch vụ trung gian),
     `gemini`, `claude`, hoặc `deepseek`.
   - **Địa chỉ cơ sở (base URL)** với dịch vụ Trung Quốc/ trung gian, ví dụ DeepSeek:
     `https://api.deepseek.com`
   - **Khóa API**: dán key bạn mua từ nhà cung cấp.
   - **Mẫu mặc định**: ví dụ `deepseek-chat`, `gpt-4o-mini`, `gemini-2.5-flash`.
   - Bật công tắc **Kích hoạt**.
4. Bấm **Kiểm tra** (nút thử nghiệm trong danh sách nhà cung cấp) để xác nhận key đúng.
5. Bấm **Lưu** ở góc trên bên phải.
6. Trở lại mục **Cấu hình quy trình sáng tác**, chọn **Nhà cung cấp mặc định** = nhà cung cấp
   vừa tạo, rồi **Lưu** lần nữa.

Giải thích ngắn gọn các thông số (ở mục *Thiết lập tạo sinh*):

| Thông số | Ý nghĩa | Gợi ý |
|---|---|---|
| Nhiệt độ (temperature) | Càng cao càng bay bổng, càng thấp càng ổn định | 0.7 – 1.0 cho sáng tác |
| Top P | Cắt bớt từ ít gặp | để trống nếu không rõ |
| Số token tối đa | Giới hạn độ dài trả lời | 4096–8192 cho chương dài |
| Prompt hệ thống | Chỉ thị chung cho AI | có thể ghi "Luôn viết bằng tiếng Việt tự nhiên" |
| Phản hồi streaming | Hiện chữ dần khi AI viết | nên bật để đỡ phải chờ |

### Bước 3: Kiểm tra kết nối cơ sở dữ liệu

Trong **Cài đặt → Cấu hình cơ sở dữ liệu**, nếu thấy **Đã cấu hình kết nối** và nhấn **Lưu**
không báo đỏ là xong. Nếu báo *Không kết nối được với cơ sở dữ liệu*, chạy `stop-all.bat`
rồi `start-all.bat` lại (MongoDB chưa bật — đây là lỗi phổ biến nhất sau khi khởi động lại máy).

---

## Phần 3 — Viết cuốn truyện đầu tiên

### 3.1. Tạo đề cương bằng AI

1. Ở **Giá sách**, bấm **Tạo truyện mới**.
2. Chọn thẻ **Sáng tác bằng AI**.
3. Nhập **Ý tưởng của bạn** — càng cụ thể càng tốt, ví dụ:

   > Một nữ quan tư pháp ở Huế năm 1932 phát hiện các vụ án chết đuối đều liên quan đến
   > một hội kín buôn cổ vật; cô phải chọn giữa thăng quan và cứu em gái mình.

4. Nhập **Số chương dự kiến** (ví dụ 60) và **Số chữ mỗi chương** (ví dụ 2500).
5. Bấm **Bắt đầu sáng tác bằng AI**. Chương trình sẽ chạy 4 bước, mỗi bước hiện tiến trình:
   1. **Trích xuất ý tưởng** – rút ý lõi từ đoạn bạn viết.
   2. **Tạo hạt nhân cốt truyện** – câu công thức "khi [nhân vật] gặp [biến cố]…".
   3. **Tạo thiết lập truyện** – tên, thể loại, giọng điệu, thế giới quan, văn phong.
   4. **Triển khai cốt truyện đầy đủ** – đề cương toàn bộ cuốn.
6. Khi thấy **Xem trước kết quả do AI tạo**, bạn có thể sửa trực tiếp từng ô, rồi bấm
   **Lưu & tạo truyện**.

Bấm **Thử lại bước thất bại** nếu một bước lỗi (thường do mạng hoặc hết hạn mức key).

### 3.2. panels làm việc bên trong một cuốn truyện

Mở truyện từ Giá sách, thanh bên trái có các khu:

| Khu | Dùng để |
|---|---|
| **Thông tin truyện** | tên, bìa, thể loại, tóm tắt, văn phong, góc nhìn |
| **Trình chỉnh sửa chương** | viết/sửa văn bản từng chương, xem phiên bản cũ |
| **Lập kế hoạch quyển** | chia cuốn thành quyển, kế hoạch chương của quyển |
| **Nhân vật / Địa điểm / Thế lực / Vật phẩm / Quy tắc & Thiết lập** | hồ sơ thực thể, có nút tạo bằng AI |
| **Đồ thị quan hệ** | sơ đồ quan hệ nhân vật–thế lực |

Ở đầu trang có bảng **Tiến độ viết** — đây là "la bàn" của bạn. Nó liệt kê các bước theo
trình tự và bấm **Tiếp tục** để chạy từng bước:

```text
Tạo cuốn sách
 └ Chi tiết mở truyện: Thế lực cốt lõi → Nhân vật chính → Quan hệ nhân vật
    → Quy tắc thế giới (tuỳ chọn) → Vật phẩm quan trọng (tuỳ chọn)
 └ Cốt truyện quyển → Bộ khởi động quyển đầu tiên
    → Địa điểm cho quyển → Nhân vật cho quyển
 └ Chuẩn bị chương tiếp theo → Viết · Chương N
 └ Xem lại hoặc tiếp tục lên kế hoạch
```

Gợi ý thật dụng: hãy chạy lần lượt theo **Tiến độ viết** thay vì nhảy cóc; mỗi bước AI
đều đọc lại hồ sơ đã lưu nên truyện mới giữ được tính nhất quán.

### 3.3. Viết một chương

Trong **Trình chỉnh sửa chương**:

1. Chọn chương đã được lên kế hoạch (bên phải hoặc danh sách chương).
2. Bấm **Sinh / Viết chương** — AI viết dựa theo dàn ý, cảnh, hồ sơ nhân vật và văn bản trước.
3. Kết quả hiện ra dạng **ứng viên**; bạn đọc, sửa, rồi bấm **Lưu**.
4. Muốn viết tiếp chương sau: làm tương tự. Muốn viết lại: chọn **Viết lại** và ghi rõ
   **Yêu cầu của tác giả** (ví dụ "giọng dứt khoát hơn, thêm đối thoại, giảm mô tả").
5. Nút **Xuất bản nháp** tải chương ra file `.txt`; bản sao cũng được lưu vào
   `app\user_data\exports`.

### 3.4. Kiểm tra tính nhất quán

Sau khi lưu chương, các luồng **Kiểm tra tâm lý sau chương**, **Kiểm tra người giữ vật phẩm**,
**Kiểm tra quy tắc thế giới**… chỉ ra điểm mâu thuẫn với hồ sơ cũ. Bạn bấm **Áp dụng / Xác nhận**
cho những thay đổi bạn đồng ý. Đây là điểm mạnh nhất của công cụ: truyện dài vẫn không "quăng bút".

---

## Phần 4 — Tắt máy và sao lưu

### 4.1. Tắt

Bấm đúp `stop-all.bat`. Dữ liệu không mất.

### 4.2. Sao lưu toàn bộ truyện

Chép 2 thư mục sau (khi app đã tắt) sang ổ khác:

```text
e:\laragon\www\viettieuthuyet\mongodata     <- toàn bộ truyện, hồ sơ, lịch sử
e:\laragon\www\viettieuthuyet\app\user_data <- cấu hình + file xuất + ảnh bìa
```

Khôi phục: tắt app → ghi đè 2 thư mục ngược lại → bật `start-all.bat`.

---

## Phần 5 — Đổi ngôn ngữ giao diện

Ở góc trên bên phải mọi trang có 3 nút: **中文 · English · Tiếng Việt**.
Mặc định là Tiếng Việt. Khi đổi, liên kết hiện tại (đang sửa chương nào) vẫn được giữ.

Prompt sinh truyện (câu lệnh gửi cho AI) cũng đã được dịch sang tiếng Việt trong
`backend\services\task_flows\defaults\` và mô tả trường trong `backend\llm\schemas\`,
nên truyện sinh ra viết bằng tiếng Việt tự nhiên.

---

## Phần 6 — Gặp lỗi thì làm gì (xử lý 90% trường hợp)

| Hiện tượng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| Mở website trắng / "Không truy cập được" | Frontend chưa lên | chạy `status.bat`; nếu Frontend `DUNG`, chạy `start-all.bat` |
| "Không kết nối được với cơ sở dữ liệu" | MongoDB chưa chạy (thường sau khi restart máy) | `stop-all.bat` → `start-all.bat` |
| "Xác thực cơ sở dữ liệu thất bại" | URL MongoDB sai | Cài đặt → Cấu hình cơ sở dữ liệu → Thay thế kết nối → dán: `mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true` → Lưu |
| Báo lỗi khi Lưu / tạo truyện, log có "replica set" | MongoDB chạy ở mode standalone | tắt `mongod` rồi chạy lại `start-all.bat` (script luôn khởi động kèm `--replSet rs0`) |
| "Cổng 3300/8200 đã bị chiếm" | Có ứng dụng khác đang dùng cổng đó | chạy `stop-all.bat`, đóng ứng dụng kia, hoặc đặt cổng khác: `$env:VT_FRONTEND_PORT=3310` rồi `start-all.bat` |
| AI không trả lời / lỗi 401, 403, 429 | Sai khóa API, hết tiền, bị giới hạn | Cài đặt → Nhà cung cấp mô hình → Kiểm tra; thử lại sau ít phút |
| Truyện sinh ra lẫn chữ Trung Quốc | Prompt hệ thống cũ còn ghi tiếng Trung | trong provider, đặt Prompt hệ thống: "Hãy viết hoàn toàn bằng tiếng Việt." |
| Một bước tạo truyện báo "Tạo nội dung thất bại" | Mất mạng / mô hình trả lời sai mẫu | bấm **Thử lại bước thất bại**; lặp lại 2-3 lần vẫn lỗi → đổi model khác |
| Máy chậm, treo khi truyện rất dài | RAM/ổ cứng | giảm **Số chữ mỗi chương**, tắt bớt tab, giữ `mongodata` trên SSD |

Xem log chi tiết: bấm đúp `log.bat` (hoặc mở `runtime\logs\*.log`).

---

## Phần 7 — Câu hỏi thường gặp

**1. Tôi cần gì để dùng?**
Máy Windows 10/11, Python 3.13, Node.js, một khóa API của nhà cung cấp AI, và khoảng 2 GB ổ cứng.

**2. Có cần Docker không?**
Không. Bản này dùng MongoDB chạy trực tiếp từ `tools\m\bin\mongod.exe`, do `start-all.bat` tự bật.

**3. Truyện có thuộc về tôi không?AI có giữ bản sao không?**
Toàn bộ nằm trên máy bạn. Chỉ nội dung cần thiết được gửi tới nhà cung cấp AI bạn cấu hình.

**4. Một chương bao nhiêu chữ, mất bao lâu và tốn bao nhiêu?**
Tuỳ model. Với ~2500 chữ/chương và model giá rẻ (deepseek-chat, gpt-4o-mini) thường chỉ vài
nghìn đồng một chương. Truyện 60 chương (~150.000 chữ) tốn cỡ vài trăm nghìn đồng tiền API.

**5. Có viết được truyện ngắn / nhiều quyển không?**
Được. Đặt **Số chương dự kiến** nhỏ, hoặc dùng **Lập kế hoạch quyển** để chia nhiều quyển.

**6. Đổi nhà cung cấp giữa chừng được không?**
Được, ngay trong từng bước của luồng sáng tác (chọn provider cho node).

**7. Sửa hồ sơ nhân vật đã lưu có làm thay đổi chương cũ không?**
Không tự động sửa văn bản cũ. Hãy dùng **Viết lại** cho chương cần hợp nhất.

**8. Tôi muốn đổi luôn câu lệnh AI (prompt) thì sửa ở đâu?**
`backend\services\task_flows\defaults\*.md` và `*.json` (đổi xong chạy `stop-all.bat`
→ `start-all.bat`), hoặc chỉnh trực quan trong **Cài đặt → Cấu hình quy trình sáng tác**
(nút mở trình chỉnh sửa luồng).

**9. Sao không thấy nút "Đăng xuất"/người dùng?**
Đây là phần mềm chạy trên máy cá nhân, mỗi máy một người dùng; quyền chọn nằm ở cấp cấu hình.

**10. Muốn cập nhật bản gốc mới thì sao?**
Bản Việt hoá nằm ở nhánh `vietnamese`; khi upstream ra bản mới, cần hợp nhất và chạy lại
bộ kiểm tra dịch (`node frontend\tools\i18n_split_merge.js merge`, `python tools\i18n_prompts.py verify`).

---

Cần hỗ trợ: chụp màn hình chỗ báo lỗi + gửi 20 dòng cuối trong `runtime\logs\backend.log`.
