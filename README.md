# H2M Download Manager (HDM)

**H2M Download Manager (HDM)** là trình quản lý tải xuống chuyên nghiệp, đa luồng hiệu năng cao được xây dựng hoàn toàn bằng **Python 3.11+**, **PySide6 (Qt6)** và nền tảng bất đồng bộ **asyncio + httpx**.

Phiên bản hiện tại: **1.0.1**. Động cơ tải chia tệp thành số phân đoạn cố định đúng bằng số kết nối đã cấu hình (1–32), ghi trực tiếp vào tệp đích bằng **NTFS Sparse File** và gom toàn bộ dữ liệu tạm vào một thư mục ẩn duy nhất. Ngoài HTTP/HTTPS, HDM tải được video HLS/DASH và các nền tảng streaming (YouTube, Facebook, TikTok…) qua **yt-dlp**. Giao diện Desktop hỗ trợ Dark/Light Mode, cùng tiện ích mở rộng tự động bắt link cho Chromium (Chrome, Edge, Cốc Cốc, Brave, Vivaldi) và Firefox.

---

## 🚀 Tính năng Nổi bật

### 1. Tải đa luồng với số phân đoạn cố định
- **Tải song song 1–32 kết nối** qua giao thức HTTP/HTTPS Range (RFC 9110), bật HTTP/2 khi máy chủ hỗ trợ.
- **Proxy HTTP/HTTPS/SOCKS4/SOCKS5**: khai báo một lần trong **Cài đặt → Trình duyệt & Kết nối** (hỗ trợ `user:pass@host:port`), áp dụng cho cả tải Range, tải khóa HLS và yt-dlp. Để trống = kết nối trực tiếp.
- **Xác thực site (HTTP Basic)**: lưu đăng nhập theo host trong tab **Tài khoản** (hỗ trợ `*.domain.com`). Mật khẩu được mã hóa bằng **Windows DPAPI** của tài khoản đang dùng; header `Authorization` chỉ gửi tới đúng host đã khai báo nên không rò sang host CDN.
- **Số phân đoạn = số kết nối**: tệp được chia đúng `N` đoạn ngay từ đầu, mỗi worker phụ trách tuần tự các đoạn của mình. Không có cơ chế tách đoạn ngẫu nhiên, nên **số luồng tải không bao giờ vượt quá cấu hình** — kể cả khi resume, số worker vẫn bị chặn ở `num_connections`.
- **Zero-Copy Direct File Writing (NTFS Sparse File)**:
  - Kích hoạt thuộc tính **Sparse File** (`FSCTL_SET_SPARSE` trên Windows NTFS) và mở tệp ở chế độ `r+b`.
  - Các luồng ghi trực tiếp vào vị trí byte đích thông qua `seek()` qua một bộ đệm ghi bất đồng bộ dùng chung.
  - **Không sinh file tạm rời rạc (`part1.tmp`, `part2.tmp`)**, không có giai đoạn ghép tệp ở 100%, tiết kiệm I/O và bảo vệ tuổi thọ SSD/NVMe.

### 2. Tạm dừng & Tiếp tục Tải (Pause & Resume an toàn)
- Toàn bộ dữ liệu tạm nằm trong một thư mục ẩn duy nhất `<thư mục lưu>/.hdm_tmp`:
  - `<id>.part` — dữ liệu tải dở (tệp sparse đã cấp phát sẵn).
  - `<id>.meta` — bản đồ phân đoạn (chunk state) + ETag của máy chủ.
  - `ytdl_<id>/` — fragment tạm của yt-dlp khi tải luồng video.
- Khi hoàn tất, tệp `.part` được đổi tên nguyên tử ngay trong cùng ổ đĩa rồi xóa `.hdm_tmp` nếu không còn tác vụ nào dùng.
- Khi resume, HDM đối chiếu **ETag**; nếu tệp trên máy chủ đã thay đổi thì tải lại từ đầu để tránh tệp hỏng. Tệp `.hdm_part`/`.hdm_meta` của bản ≤ 1.0.0 được tự động di trú sang thư mục mới ở lần chạy kế tiếp.

### 3. Hẹn giờ tải (Download Scheduler)
- **Khung giờ tải trong ngày**: bật trong **Cài đặt → Tải xuống & Lưu trữ**, nhập giờ bắt đầu / kết thúc dạng `HH:MM` (để trống một đầu = không giới hạn phía đó).
- **Tự tạm dừng ngoài khung giờ**: các tác vụ đang chạy (đang kết nối, đang tải, đang xử lý) và tác vụ đang chờ được tự động tạm dừng; khi vào khung giờ, **chỉ những tác vụ do hẹn giờ tạm dừng** mới được tự tiếp tục — tác vụ người dùng chủ động tạm dừng vẫn giữ nguyên.
- **Khung giờ vắt qua nửa đêm**: nếu giờ bắt đầu lớn hơn giờ kết thúc, khung giờ chạy qua 0h (ví dụ `23:00 → 06:00`). Giờ bắt đầu được tính, giờ kết thúc thì không.

### 4. Tải video & luồng phát trực tuyến (HLS/DASH/YouTube)
- Nhận diện URL streaming (`m3u8`, `mpd`, YouTube) và chuyển sang **yt-dlp** thay vì tải thô.
- Nhận playlist HLS do trang sinh bằng JavaScript (`blob:`) qua cầu nối MAIN-world của extension, chọn chất lượng (1080p/720p/480p/360p/MP3 128–320 kbps) ngay trên hộp thoại xác nhận.
- Với luồng HLS có mã hóa AES-128, khóa giải mã được tải lại bằng đúng cookie/Referer của phiên trình duyệt người dùng (không trích xuất hay phát lại khóa của bên thứ ba).
- Ghép video + audio và trích xuất MP3 bằng FFmpeg (tự dò bản cài sẵn hoặc dùng `imageio-ffmpeg`).

### 5. Giao diện Người dùng Hiện đại (PySide6 Desktop GUI)
- **Hỗ trợ Giao diện Tối & Sáng (Dark & Light Mode)**: thiết kế chuẩn phong cách Slate hiện đại, độ tương phản text chuẩn WCAG, chuyển đổi mượt mà không sai lệch vị trí.
- **Bản đồ Phân đoạn Trực quan (Interactive Chunk Map Widget)**:
  - Hiển thị thanh tiến trình đồ họa chia theo từng phân đoạn tải theo thời gian thực.
  - Xem chi tiết từng phân đoạn: ID, phạm vi byte, dung lượng đã tải, tốc độ tức thời và trạng thái.
- **Tự động Phân loại Danh mục (Smart Categorization)**:
  - Tự động nhận diện và phân loại: 📦 Nén, 💻 Phần mềm, 🎬 Video, 🎵 Âm nhạc, 📄 Tài liệu, 🖼 Hình ảnh, 📂 Khác.
  - Tùy chọn tự động phân luồng lưu vào các thư mục con tương ứng; không ghi đè thư mục người dùng đã chọn tay.
- **Tích hợp Khay Hệ thống (System Tray)**: thu nhỏ xuống khay đồng hồ, hiển thị thông báo khi tải hoàn tất, autostart khi khởi động Windows ở chế độ ẩn (không bật cửa sổ).

### 6. Tích hợp Trình duyệt (Chrome / Edge / Cốc Cốc / Brave / Vivaldi / Firefox)
- Tiện ích mở rộng **Manifest V3** giao tiếp với máy chủ HTTP cục bộ chạy nền tại `http://127.0.0.1:9618` (chỉ nhận request từ extension, chặn Origin của trang web thường để phòng CSRF/DNS-rebinding).
- **Bắt link tự động an toàn**: tạm dừng lượt tải trên trình duyệt → chuyển sang HDM → nếu HDM nhận thì hủy bản tải của trình duyệt; nếu HDM tắt/từ chối thì trình duyệt tiếp tục tải bình thường.
- **Nút "Tải video với HDM"** gắn ngoài trình phát video, kèm menu chọn chất lượng; tắt/mở tức thì trong popup, không cần tải lại trang.
- **Ghi nhớ link đã tải**: media đã giao cho HDM không bị bắt lại khi mở lại trang (so khớp theo origin + đường dẫn vì CDN đổi token mỗi phiên).
- Menu chuột phải: "Tải liên kết này với HDM", "Tải đa phương tiện (Video/Audio) với HDM".


---

## 📂 Cấu trúc Thư mục Dự án

```
H2M Download Manager/
├── hdm/
│   ├── __init__.py           # Khai báo __version__ (nguồn phiên bản cho bộ cài)
│   ├── app.py                # Điểm vào PySide6, IPC một phiên bản, chế độ --autostart
│   ├── core/                 # Lõi động cơ tải & xử lý logic
│   │   ├── config.py         # Quản lý cấu hình & chuẩn hóa thư mục lưu
│   │   ├── models.py         # DownloadTask, Chunk, TaskStatus, đường dẫn .hdm_tmp
│   │   ├── engine.py         # Động cơ tải (httpx + asyncio) và cầu nối yt-dlp
│   │   ├── manager.py        # Hàng đợi, giới hạn đồng thời, giữ tên tệp không trùng
│   │   ├── sparse_file.py    # NTFS Sparse file, pre-allocation, kiểm tra dung lượng
│   │   └── server.py         # HTTP server cục bộ nhận link từ extension
│   ├── gui/                  # Giao diện Desktop PySide6
│   │   ├── main_window.py    # Cửa sổ chính (Sidebar, Table, Toolbar, Statusbar)
│   │   ├── chunk_widget.py   # Widget vẽ bản đồ phân đoạn (Chunk Map)
│   │   ├── add_dialog.py     # Hộp thoại thêm link & kiểm tra link
│   │   ├── detail_dialog.py  # Hộp thoại chi tiết tiến trình & Chunk Map
│   │   ├── settings_dialog.py# Cài đặt số luồng, cổng server, thư mục, autostart
│   │   ├── extension_dialog.py# Hướng dẫn cài tiện ích trình duyệt
│   │   ├── icons.py          # Bộ sinh biểu tượng vector High-DPI
│   │   └── style.py          # Hệ thống QSS Dark & Light mode
│   └── utils/                # Tiện ích bổ trợ
│       ├── browsers.py       # Phát hiện trình duyệt đã cài trên Windows
│       ├── formatters.py     # Định dạng dung lượng, tốc độ, thời gian ETA
│       ├── i18n.py           # Chuỗi giao diện Việt/Anh
│       ├── secrets.py        # Mã hóa/giải mã mật khẩu bằng Windows DPAPI
│       ├── site_auth.py      # Khớp host và tìm thông tin đăng nhập theo site
│       ├── category.py       # Phân loại tệp tin theo đuôi mở rộng
│       └── system.py         # Explorer, AppData, thư mục Downloads, autostart
├── extension/                # Tiện ích mở rộng Chromium (Manifest V3)
│   ├── manifest.json
│   ├── background.js         # Service worker: bắt link, ghi nhớ link đã tải
│   ├── content.js            # Quét video & gắn nút "Tải video với HDM"
│   ├── content.css
│   ├── main_world.js         # Cầu nối MAIN-world đọc playlist blob:
│   ├── popup.html, popup.js, popup.css # Giao diện popup tiện ích
│   └── icons/                # Bộ biểu tượng 16, 32, 48, 128 px
├── installer/HDM.iss         # Kịch bản Inno Setup
├── tests/                    # Kiểm thử động cơ & tiện ích
├── app.ico                   # Biểu tượng ứng dụng Windows
├── build_nuitka.py           # Đóng gói Nuitka standalone (khuyến nghị)
├── build_installer.py        # Tạo bộ cài Inno Setup từ dist/HDM
├── build_extension.py        # Sinh bản tiện ích Chromium/Firefox (kèm zip)
├── build_exe.py              # Đóng gói nhanh bằng PyInstaller
├── requirements.txt          # Danh sách thư viện phụ thuộc
├── main.py                   # Điểm chạy nhanh ứng dụng
└── README.md
```

---

## 🛠 Hướng dẫn Cài đặt & Chạy Ứng dụng

### 1. Cài đặt Thư viện Phụ thuộc
Đảm bảo bạn đã cài đặt Python 3.11 trở lên trên Windows. Mở PowerShell trong thư mục dự án:
```powershell
pip install -r requirements.txt
```

### 2. Khởi chạy Ứng dụng
```powershell
python main.py
```

---

## 🌐 Hướng dẫn Cài đặt Tiện ích Trình duyệt

### Cài từ HDM (khuyến nghị)

HDM tự mở hộp thoại hướng dẫn này mỗi lần khởi động cho tới khi bạn tick **Không hiện lại** rồi bấm **OK** (lựa chọn được lưu vào cấu hình). Có thể mở lại bất cứ lúc nào từ **Công cụ → Cài đặt tiện ích trình duyệt…**

Trong HDM vào **Công cụ → Cài đặt tiện ích trình duyệt…**:

1. HDM tự phát hiện các trình duyệt đã cài (Chrome, Edge, Cốc Cốc, Brave, Vivaldi, Chromium, Firefox).
2. Chọn trình duyệt đang dùng. HDM copy tiện ích vào `%APPDATA%\HDM\extension` (đường dẫn cố định để ID tiện ích không đổi khi cập nhật app) và hiện hướng dẫn từng bước kèm đường dẫn thư mục.
3. Bấm **Mở Chrome/Edge/…** để mở trình duyệt (địa chỉ trang quản lý tiện ích được sao chép sẵn), rồi bấm **Mở thư mục** hoặc **Sao chép** đường dẫn và làm theo hướng dẫn:
   - **Chromium** (Chrome, Edge, Cốc Cốc, Brave, Vivaldi, Chromium): bật **Chế độ dành cho nhà phát triển** → **Tải tiện ích chưa đóng gói** → chọn thư mục ở trên.
   - **Firefox**: mở `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on…** → chọn `manifest.json` trong thư mục đó.

> Chrome từ bản 156, Cốc Cốc và Firefox đều chặn cài tiện ích cục bộ không cần thao tác, nên các bước trên là mức tự động tối đa mà trình duyệt cho phép. Firefox chỉ giữ tiện ích tạm thời tới khi đóng trình duyệt; muốn cố định cần bản đã ký trên AMO.

### Chromium (Chrome / Edge / Cốc Cốc / Brave) — thủ công

1. Mở trình duyệt và truy cập trang quản lý tiện ích:
   - **Google Chrome**: `chrome://extensions`
   - **Microsoft Edge**: `edge://extensions`
   - **Cốc Cốc**: `coccoc://extensions`
   - **Brave**: `brave://extensions`
2. Bật công tắc **Chế độ dành cho nhà phát triển (Developer mode)** ở góc trên bên phải.
3. Bấm vào nút **Tải tiện ích đã giải nén (Load unpacked)**.
4. Điều hướng và chọn thư mục `extension` trong mã nguồn dự án (bản cài đặt: thư mục `extension` cạnh `HDM.exe`).
5. Ghim biểu tượng HDM lên thanh công cụ của trình duyệt. Tiện ích sẽ tự động đồng bộ liên kết với HDM Desktop qua cổng `127.0.0.1:9618`.

### Firefox (128 trở lên)

Firefox không hỗ trợ `background.service_worker` của Manifest V3 và cần Gecko ID, nên dùng bản build riêng được sinh từ cùng mã nguồn:

```powershell
python build_extension.py firefox
```

1. Mở `about:debugging#/runtime/this-firefox`.
2. Bấm **Load Temporary Add-on…** và chọn `dist/extension-firefox/manifest.json`.
3. Để cài lâu dài, nộp `dist/HDM-extension-firefox.zip` lên [addons.mozilla.org](https://addons.mozilla.org/developers/) để ký (hoặc dùng Firefox Developer Edition/ESR với `xpinstall.signatures.required = false`).

Lưu ý: từ Firefox 127, quyền truy cập trang (`<all_urls>`) được hiển thị trong hộp thoại cài đặt và cấp ngay khi cài; nếu người dùng thu hồi trong `about:addons` → **Permissions**, tiện ích sẽ không bắt được luồng phát.

`python build_extension.py` (không tham số) sinh cả hai bản kèm file zip để phát hành lên Chrome Web Store / Edge Add-ons / AMO.

---

## 📦 Hướng dẫn Đóng gói Bộ cài (Nuitka + Inno Setup)

Bản phát hành dùng **Nuitka** biên dịch Python sang C (không kèm `.py`/`.pyc`, khó dịch ngược hơn PyInstaller) và chạy dạng **standalone** — mở app tức thì, không giải nén ra thư mục tạm như `--onefile`:

```powershell
python build_nuitka.py        # lần đầu 30–60 phút (biên dịch C toàn bộ)
python build_installer.py     # đóng gói bằng Inno Setup
```

Kết quả:
```
dist/HDM/HDM.exe                  # thư mục standalone, mở cực nhanh
dist/HDM/extension/               # tiện ích cho Chromium
dist/HDM/extension-firefox/       # tiện ích cho Firefox 128+
dist/HDM_Setup_v1.0.1.exe         # bộ cài duy nhất, có icon Desktop
```

Yêu cầu: MSVC (Visual Studio Build Tools) hoặc để Nuitka tự tải MinGW64; [Inno Setup 6](https://jrsoftware.org/isdl.php) cho bước tạo bộ cài. Bộ cài mặc định cài theo từng người dùng (`%LOCALAPPDATA%\Programs\HDM`, không cần UAC) và tạo lối tắt Desktop + Start Menu.

Vẫn có thể dùng PyInstaller nếu cần build nhanh để test nội bộ:

```powershell
python build_exe.py
```

Lưu ý: Nuitka biên dịch mã Python sang mã máy nên khó dịch ngược hơn nhiều, nhưng không phải “bảo vệ 100%” — chuỗi, tài nguyên nhúng và mã JavaScript của extension vẫn có thể đọc được. Ngoài ra, build Nuitka lần đầu cần tải Qt/yt-dlp nên dung lượng `dist/HDM` lớn hơn bản PyInstaller.

---

## ⚖ So sánh Kiến trúc: Trình tải Thông thường vs H2M Download Manager

| Tiêu chí | Trình tải Truyền thống | H2M Download Manager (HDM) |
|---|---|---|
| **Tech Stack** | Đồng bộ, đơn luồng hoặc threading GIL-bound | **PySide6 (Qt6) + `httpx` + `asyncio` bất đồng bộ hoàn toàn** |
| **Độ mượt mà GUI** | Dễ bị đơ/khựng (Not Responding) khi I/O cao | **Mượt mà 60 FPS**, tách biệt hoàn toàn Event Loop mạng và UI Thread |
| **Chia luồng tải** | Chia cố định hoặc tự tăng luồng, dễ nghẽn ở luồng cuối và vượt cấu hình | **Số đoạn đúng bằng số kết nối (1–32)**, worker cố định — không bao giờ vượt cấu hình, kể cả khi resume |
| **Ghi tệp** | Ghi nhiều file tạm vụn vặt rồi ghép nối ở 100% | **NTFS Sparse File + Async Batch Writer**, ghi seek trực tiếp, không tốn thời gian ghép tệp |
| **Tệp tạm** | Rải rác cạnh tệp đích, dễ sót lại khi lỗi | **Một thư mục ẩn `.hdm_tmp`**, đổi tên nguyên tử khi xong, tự di trú định dạng cũ |
| **Video streaming** | Không hỗ trợ HLS/DASH hoặc cần phần mềm ngoài | **yt-dlp tích hợp**, nhận playlist `blob:` từ trình duyệt, ghép FFmpeg, MP3 |
| **Bản đồ luồng** | Chỉ có 1 thanh % chung chung | **Interactive Chunk Map Widget** trực quan hóa từng phân đoạn theo thời gian thực |
| **Giao tiếp Trình duyệt** | Cần phần mềm bên thứ 3 hoặc cài đặt phức tạp | **Async REST API nội bộ**, tự động bắt link an toàn |

---

## ⚠ Hạn chế Đã biết (v1.0.1)

- **Chưa tự động đăng nhập form** (chỉ hỗ trợ HTTP Basic theo host) và chưa import cookie hàng loạt; proxy HTTP/HTTPS/SOCKS đã có.
- **Chưa có nhiều hàng đợi ưu tiên**; chỉ có một hàng đợi FIFO với giới hạn `max_concurrent_tasks` (hẹn giờ tải theo khung giờ trong ngày đã có).
- **Số đoạn cố định**: tệp nhỏ hơn `min_chunk_size` chỉ dùng 1 kết nối; đoạn cuối chậm có thể làm giảm tốc độ tổng khi máy chủ phân phối không đều.
- **Chưa có tải hàng loạt (batch), FTP/FTPS, site grabber, quét virus, xem trước media.**
- **Chỉ tiếng Việt và tiếng Anh.**
- **Bộ cài chưa ký số**, nên Windows SmartScreen có thể cảnh báo lần chạy đầu; extension Firefox cần ký trên AMO để cài lâu dài.
- **Chưa có API token** cho HTTP server cục bộ — server chỉ lọc theo `Origin` của extension và chỉ lắng nghe trên `127.0.0.1`.

---
*© 2026 H2M Team. Phát triển với tiêu chuẩn mã nguồn sạch và hiệu năng tối ưu.*
