# H2M Download Manager (HDM)

**H2M Download Manager (HDM)** là trình quản lý tải xuống chuyên nghiệp, đa luồng hiệu năng cao được xây dựng hoàn toàn bằng **Python 3.11+**, **PySide6 (Qt6)** và nền tảng bất đồng bộ **asyncio + httpx**.

Ứng dụng sở hữu thuật toán chia đoạn động thông minh (**Dynamic Segmentation / Work Stealing**) tương tự cơ chế của Internet Download Manager (IDM), công nghệ ghi tệp trực tiếp **NTFS Sparse File** không tạo tệp tạm vụn vặt, giao diện Desktop hiện đại hỗ trợ cả Dark Mode và Light Mode, cùng tiện ích mở rộng tự động bắt link cho các trình duyệt Chromium (Chrome, Edge, Cốc Cốc, Brave).

---

## 🚀 Tính năng Nổi bật

### 1. Thuật toán Chia đoạn Động (Dynamic Segmentation & Work Stealing)
- **Tải đa luồng song song**: Hỗ trợ từ **1 đến 32 luồng** tải đồng thời qua giao thức HTTP/HTTPS Range (RFC 9110).
- **Cơ chế Đánh cắp Công việc (Work Stealing)**:
  - Khi một luồng hoàn thành dải byte của mình sớm (do mạng nhanh hoặc máy chủ phản hồi tốt), luồng đó không tắt mà tự động tìm phân đoạn đang chạy có dung lượng còn lại lớn nhất.
  - Tự động cắt đôi phân đoạn đó (`split_point = current_pos + remaining / 2`) và nhận nửa sau để tiếp tục tải song song.
  - Loại bỏ hoàn toàn hiện tượng 1 luồng cuối bị nghẽn (tail latency) làm kéo dài thời gian hoàn thành.
- **Zero-Copy Direct File Writing (NTFS Sparse File)**:
  - Kích hoạt thuộc tính **Sparse File** (`FSCTL_SET_SPARSE` trên Windows NTFS) và mở tệp ở chế độ `r+b`.
  - Các luồng ghi trực tiếp vào vị trí byte đích thông qua `seek()`.
  - **Không chia thành các file tạm vụn vặt (`part1.tmp`, `part2.tmp`)**, loại bỏ hoàn toàn giai đoạn ghép tệp ở 100%, tiết kiệm tài nguyên I/O và bảo vệ tuổi thọ ổ SSD/NVMe.

### 2. Tạm dừng & Tiếp tục Tải (Pause & Resume an toàn)
- Tự động lưu bản đồ phân đoạn (Chunk State) vào tệp siêu dữ liệu `.hdm_meta`.
- Cho phép Pause / Resume linh hoạt kể cả khi mạng gặp sự cố hoặc khởi động lại ứng dụng.

### 3. Giao diện Người dùng Hiện đại (PySide6 Desktop GUI)
- **Hỗ trợ Giao diện Tối & Sáng (Dark & Light Mode)**: Thiết kế chuẩn phong cách Slate hiện đại, độ tương phản text chuẩn WCAG, chuyển đổi mượt mà không sai lệch vị trí.
- **Bản đồ Phân đoạn Trực quan (Interactive Chunk Map Widget)**:
  - Hiển thị thanh tiến trình đồ họa chia theo từng luồng tải trực quan theo thời gian thực.
  - Xem chi tiết từng luồng: ID luồng, phạm vi byte, dung lượng đã tải, tốc độ tức thời và trạng thái.
- **Tự động Phân loại Danh mục (Smart Categorization)**:
  - Tự động nhận diện và phân loại: 📦 Nén, 💻 Phần mềm, 🎬 Video, 🎵 Âm nhạc, 📄 Tài liệu, 🖼 Hình ảnh, 📂 Khác.
  - Tùy chọn tự động phân luồng lưu vào các thư mục con tương ứng.
- **Tích hợp Khay Hệ thống (System Tray)**: Thu nhỏ xuống khay đồng hồ, hiển thị thông báo khi tải hoàn tất.

### 4. Tích hợp Trình duyệt (Chrome / Edge / Cốc Cốc / Brave / Firefox)
- Tiện ích mở rộng **Manifest V3** giao tiếp với máy chủ HTTP cục bộ chạy nền tại `http://127.0.0.1:9618`.
- **Bắt link tự động an toàn**: Tạm dừng lượt tải trên trình duyệt -> Chuyển sang HDM -> Nếu HDM nhận thì hủy trên trình duyệt; nếu HDM chưa bật thì trình duyệt tiếp tục tải bình thường không làm gián đoạn người dùng.
- Menu chuột phải tiện lợi: "Tải liên kết này với HDM", "Tải đa phương tiện (Video/Audio) với HDM".

---

## 📂 Cấu trúc Thư mục Dự án

```
H2M Download Manager/
├── hdm/
│   ├── __init__.py
│   ├── app.py                # Điểm vào chính ứng dụng PySide6 & asyncio coordinator
│   ├── core/                 # Lõi động cơ tải & xử lý logic
│   │   ├── __init__.py
│   │   ├── config.py         # Quản lý cấu hình & lưu trữ cài đặt
│   │   ├── models.py         # Data models (DownloadTask, Chunk, TaskStatus)
│   │   ├── engine.py         # Lõi tải Dynamic Segmentation (httpx + asyncio)
│   │   ├── manager.py        # Hàng đợi, giới hạn đồng thời, điều phối tác vụ
│   │   ├── sparse_file.py    # Windows NTFS Sparse file & pre-allocation
│   │   └── server.py         # Máy chủ HTTP cục bộ nhận link từ Extension
│   ├── gui/                  # Giao diện người dùng Desktop PySide6
│   │   ├── __init__.py
│   │   ├── main_window.py    # Cửa sổ chính (Sidebar, Table, Toolbar, Statusbar)
│   │   ├── chunk_widget.py   # Widget vẽ bản đồ phân đoạn (Chunk Map) trực quan
│   │   ├── add_dialog.py     # Hộp thoại thêm liên kết tải & kiểm tra link
│   │   ├── detail_dialog.py  # Hộp thoại chi tiết tiến trình & Chunk Map
│   │   ├── settings_dialog.py# Hộp thoại cài đặt số luồng, cổng server, thư mục
│   │   ├── icons.py          # Bộ sinh biểu tượng vector High-DPI khử răng cưa
│   │   └── style.py          # Hệ thống giao diện QSS Dark & Light mode
│   └── utils/                # Tiện ích bổ trợ
│       ├── __init__.py
│       ├── formatters.py     # Định dạng dung lượng, tốc độ, thời gian ETA
│       ├── category.py       # Phân loại tệp tin theo đuôi mở rộng
│       └── system.py         # Tương tác hệ điều hành Windows Explorer, AppData
├── extension/                # Tiện ích mở rộng Chromium (Manifest V3)
│   ├── manifest.json
│   ├── background.js         # Service worker bắt link tải
│   ├── popup.html, popup.js, popup.css # Giao diện popup tiện ích
│   └── icons/                # Bộ biểu tượng 16, 32, 48, 128 px
├── app.ico                   # Biểu tượng ứng dụng Windows
├── build_exe.py              # Script đóng gói ra file .exe độc lập (PyInstaller)
├── build_extension.py        # Sinh bản tiện ích cho Chromium và Firefox (kèm zip)
├── requirements.txt          # Danh sách thư viện phụ thuộc
├── main.py                   # Điểm chạy nhanh ứng dụng
└── README.md
```

---

## 🛠 Hướng dẫn Cài đặt & Chạy Ứng dụng

### 1. Cài đặt Thư viện Phụ thuộc
Đảm bảo bạn đã cài đặt Python 3.10 trở lên trên Windows. Mở PowerShell trong thư mục dự án:
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
dist/HDM/extension/               # tiện ích cho Chrome / Edge / Cốc Cốc / Brave
dist/HDM/extension-firefox/       # tiện ích cho Firefox 128+
dist/HDM_Setup_v1.0.0.exe         # bộ cài duy nhất, có icon Desktop
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
| **Chia luồng tải** | Chia cố định ban đầu, dễ bị nghẽn ở luồng cuối | **Dynamic Work Stealing** liên tục chia đôi đoạn lớn nhất cho luồng rảnh |
| **Ghi tệp** | Ghi nhiều file tạm vụn vặt rồi ghép nối ở 100% | **NTFS Sparse File + Random-Access Direct Seek**, không tốn thời gian ghép tệp |
| **Bản đồ luồng** | Chỉ có 1 thanh % chung chung | **Interactive Chunk Map Widget** trực quan hóa từng phân đoạn theo thời gian thực |
| **Giao tiếp Trình duyệt** | Cần phần mềm bên thứ 3 hoặc cài đặt phức tạp | **Async REST API nội bộ**, tự động bắt link an toàn |

---
*© 2026 H2M Team. Phát triển với tiêu chuẩn mã nguồn sạch và hiệu năng tối ưu.*
