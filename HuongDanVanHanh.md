# Hướng dẫn vận hành & xử lý lỗi — Việt Tiểu Thuyết

Dành cho người hỗ trợ kỹ thuật (hoặc khách tự chữa). Đọc từ trên xuống, dừng ở mục khớp triệu chứng.

Cổng cố định: MongoDB **27017** · Backend **8200** · Frontend **3300**.
Log: `e:\laragon\www\viettieuthuyet\runtime\logs\` (mongod.log, backend.log, frontend.log).
PID: `runtime\pids\*.pid`.

---

## 0. Kiểm tra nhanh 30 giây

```powershell
cd e:\laragon\www\viettieuthuyet\app
.\status.bat                       # 3 dòng DANG CHAY / DUNG
powershell -NoProfile -Command "(Invoke-WebRequest http://127.0.0.1:8200/docs -UseBasicParsing).StatusCode"
```

Nếu cả ba dịch vụ `DANG CHAY`, `http://127.0.0.1:3300` vẫn trắng → xem mục 4.

## 1. Lỗi sau khi khởi động lại máy (Laragon không tự chạy gì cả)

Dấu hiệu: mở web báo "Không kết nối được với cơ sở dữ liệu".
Nguyên nhân: MongoDB là tiến trình tay, mất khi reboot.
Xử lý: bấm `start-all.bat` (script tự bật mongod, tự kiểm tra replica set).

## 2. MongoDB không lên

```powershell
# 2.1 Xem log
Get-Content e:\laragon\www\viettieuthuyet\runtime\logs\mongod.log -Tail 40

# 2.2 Cổng 27017 đã bị chiếm?
netstat -ano | findstr :27017

# 2.3 Khởi động tay (để đọc thông báo lỗi trực tiếp)
& 'e:\laragon\www\viettieuthuyet\tools\m\bin\mongod.exe' --dbpath 'e:\laragon\www\viettieuthuyet\mongodata' --replSet rs0 --bind_ip 127.0.0.1 --port 27017
```

| Dòng trong log | Ý nghĩa | Cách sửa |
|---|---|---|
| `Failed to acquire lock` / `Unable to lock` | Còn mongod chạy ở tiến trình khác | `taskkill /F /IM mongod.exe` rồi chạy `start-all.bat` |
| `IllegalInstruction` / `tcmalloc` crash | CPU/Windows không tương thích bản 8.0 | đổi sang MongoDB 7.0 hoặc 8.2 (targeted build) trong `tools\` |
| `No replset config has been received` | DATA mới, chưa initiate | script tự gọi `tools\rs_init.py`; hoặc chạy: `python ..\tools\rs_init.py` |
| `attempt to write a readonly database` | Quyền thư mục `mongodata` | cấp quyền Write cho user hiện hành, không chạy mongod bằng user khác |

**Quan trọng**: `mongodata` (khác) không phải `mongodata2`. Nếu trước đây chạy bằng tay trên dbpath khác,
sửa `VT_MONGO_DATA` trỏ về đúng thư mục cũ, đừng tạo db mới rồi tưởng mất truyện.

## 3. Port bị chiếm / phải đổi cổng

```powershell
$env:VT_FRONTEND_PORT = 3310     # chi ap dung trong cua so PowerShell nay
$env:VT_BACKEND_PORT  = 8210
e:\laragon\www\viettieuthuyet\app\start-all.bat
```

Frontend đọc backend lúc **build**; đổi `VT_BACKEND_PORT` thì phải build lại:

```powershell
cd e:\laragon\www\viettieuthuyet\app\frontend
$env:NEXT_PUBLIC_API_BASE = 'http://127.0.0.1:8210'
& 'D:\nodejs\npm.cmd' run build
```

Không dùng cổng 80/443 (Laragon Apache/Nginx giữ) và không đổi cổng tạm liên tục — tab cũ sẽ dính cache.

## 4. Web mở được nhưng không lưu được truyện

1. **Cài đặt → Cấu hình cơ sở dữ liệu**: URL phải là
   `mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true`, tên db `novel_generator`, bấm **Lưu**.
2. Lưu xong app tự kiểm tra kết nối. Nếu báo đỏ:
   - "Không kết nối được…" → mongod chết (mục 1/2).
   - "Xác thực…" → URL có user/password không phù hợp.
3. Lỗi `Transaction numbers ... replica set required` → mongod chạy standalone (thiếu `--replSet rs0`), dung `stop-all.bat` roi `start-all.bat`.

## 5. AI báo lỗi khi tạo truyện

| Message | Nguyên nhân | Cách sử |
|---|---|---|
| 401/403 | Sai hoặc hết hạn API key | Cài đặt → Nhà cung cấp → dán lại key → **Kiểm tra** |
| 429 / "đang chờ thử lại" | vượt hạn mức (RPM/TPM) | giảm **Số token tối đa**, đợi, hoặc thêm provider phụ |
| "cấu trúc trả về không hợp lệ" | Model nhỏ không tuân thủ JSON schema | đổi model mạnh hơn (deepseek-chat, gpt-4.1, gemini-2.5-pro…), bấm **Thử lại bước thất bại** |
| Timeout | Mạng/proxy | tăng **Thời gian chờ** (60→180 s); ở VN một số endpoint cần proxy riêng |
| Không có phản hồi nào | `enabled = false` hoặc chưa chọn provider mặc định | bật công tắc **Kích hoạt**, chọn ở **Cấu hình quy trình sáng tác** |

## 6. Truyện / dữ liệu

- Dữ liệu nằm trong `mongodata`. Sao lưu: `stop-all.bat` → chép `mongodata` + `app\user_data`.
- Xóa hẳn một cuốn: Giá sách → xóa (vào **Thùng rác**) → **Xóa vĩnh viễn**.
- Không bao giờ xóa `user_data\config\config.yaml` (mất key), thay vào đó sao lưu nó.

## 7. RESET khi muốn bắt đầu sạch (CẨN THẬN: mất truyện)

```powershell
e:\laragon\www\viettieuthuyet\app\stop-all.bat
Rename-Item e:\laragon\www\viettieuthuyet\mongodata mongodata.bak-$(Get-Date -Format yyyyMMddHHmm)
e:\laragon\www\viettieuthuyet\app\start-all.bat   # tự tạo db mới + initiate rs0
```

## 8. Chạy lại bộ kiểm tra bản Việt hóa (dành cho người bảo trì)

```powershell
cd e:\laragon\www\viettieuthuyet\app
.\.venv\Scripts\python.exe tools\i18n_prompts.py verify     # 0 problem = prompt OK
.\.venv\Scripts\python.exe tools\i18n_prompts_audit.py      # 0 problem = khong hong cau truc
node frontend\tools\i18n_split_merge.js merge               # tai tao messages\vi.json
```

Nếu kéo bản mới từ upstream, chạy lại 4 lệnh trên; `audit` sẽ chỉ ra file nào còn chuỗi Hán
hoặc placeholder bị đổi.
