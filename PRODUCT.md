# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Người dùng chính**: Người dùng hệ điều hành Windows thường xuyên tải phim, video streaming, tệp tin nén dung lượng lớn, tài liệu và bộ cài phần mềm qua các trình duyệt web phổ biến (Google Chrome, Microsoft Edge, Cốc Cốc, Brave, Vivaldi, Firefox).
- **Nhu cầu cốt lõi**:
  - Tăng tốc độ tải tối đa thông qua cơ chế chia nhỏ đa luồng (1–32 kết nối).
  - Tự động bắt link tải tệp và video trực tiếp từ trình duyệt mà không cần sao chép URL thủ công.
  - Tạm dừng và tiếp tục (Pause & Resume) an toàn, tuyệt đối không bị hỏng tệp khi mạng chập chờn.
  - Giao diện trực quan, hiện đại, hỗ trợ Dark/Light mode, không quảng cáo và không bloatware.

## Product Purpose

- **Mục đích**: Là trình quản lý và tăng tốc tải xuống đa luồng hiệu năng cao, hiện đại trên Windows, được xây dựng độc lập nhằm mang đến giải pháp thay thế tối ưu cho các phần mềm truyền thống như Internet Download Manager (IDM).
- **Thành công có nghĩa là**:
  - Tận dụng tối đa băng thông mạng với độ ổn định cao.
  - Tiết kiệm tài nguyên máy tính và bảo vệ tuổi thọ ổ đĩa (SSD/NVMe) nhờ ghi trực tiếp vào đĩa NTFS không sinh file rác tạm thời.
  - Bắt link thông minh, chính xác trên mọi trang web và trình phát video/stream (HLS, DASH, YouTube).
  - Trải nghiệm người dùng mượt mà, phản hồi tức thì và không gây gián đoạn công việc của người dùng.

## Positioning

- **Điểm khác biệt cốt lõi**:
  - **Zero-Copy Direct File Writing (NTFS Sparse File)**: Khác với IDM hay các trình tải khác thường tải từng file tạm rời rạc (`part1.tmp`, `part2.tmp`) rồi mất thời gian dài để ghép file ở 99%–100%, HDM kích hoạt thuộc tính Sparse File trên NTFS, ghi trực tiếp dữ liệu vào vị trí byte đích trong bộ đệm bất đồng bộ, triệt tiêu thời gian ghép file và phân mảnh đĩa.
  - **Kiến trúc bất đồng bộ hiện đại**: Xây dựng hoàn toàn trên nền tảng Python 3.11+, `asyncio` và `httpx` (hỗ trợ HTTP/2), cho phép xử lý hàng ngàn I/O requests mà không nghẽn giao diện.
  - **Tích hợp sẵn bộ giải mã video stream mạnh mẽ**: Tích hợp trực tiếp `yt-dlp` và `FFmpeg`, tự động bắt các luồng phát phức tạp (HLS `.m3u8`, DASH `.mpd`) và hỗ trợ trích xuất MP3 (128–320 kbps) hoặc ghép video MP4 tự động.

## Operating Context

- **Môi trường hoạt động**:
  - Hệ điều hành: Windows 10 / Windows 11 (64-bit).
  - Ứng dụng Desktop chính: Ứng dụng native viết bằng PySide6 (Qt6), khởi chạy nhanh, hỗ trợ Dark & Light theme, tích hợp khay hệ thống (System Tray).
  - Tiện ích mở rộng (Browser Companion Extension): Manifest V3 chạy trên các trình duyệt Chromium và Firefox, kết nối với ứng dụng Desktop qua HTTP server nội bộ tại `http://127.0.0.1:9618` (bảo vệ Origin chống tấn công CSRF / DNS-rebinding).
- **Quy trình làm việc (Workflows)**:
  - Bắt link tự động khi tải file trên trình duyệt hoặc click icon tải ngoài khung phát video.
  - Hiển thị hộp thoại xác nhận tải kiểu IDM (kiểm tra dung lượng ổ đĩa trống, xem trước kích thước, chọn thư mục lưu và chất lượng).
  - Theo dõi tiến độ thời gian thực trên cửa sổ chính với Bản đồ phân đoạn trực quan (Interactive Dynamic Chunk Map).
  - Tự động phân loại tệp tải về vào các thư mục con chuyên biệt hoặc hẹn giờ tải trong khung giờ đêm/ngoài giờ cao điểm.

## Capabilities and Constraints

- **Chức năng đã xác nhận**:
  - Tải song song từ 1 đến 32 luồng kết nối HTTP/HTTPS Range (RFC 9110), kích hoạt HTTP/2 khi máy chủ hỗ trợ.
  - Bắt link streaming thông minh từ browser extension, nút tải video luôn được neo cố định bên ngoài ô phát video của mọi trang web và iframe.
  - Khung giờ tải tự động (Download Scheduler) với khả năng tạm dừng và tự tiếp tục thông minh ngoài khung giờ.
  - Tự động kiểm tra dung lượng ổ đĩa trống trước khi phân bổ file, cảnh báo nếu không đủ chỗ trống.
  - Tự động tránh trùng tên tệp bằng cách tự đánh số hậu tố `(1)`, `(2)` khi trong thư mục đã có tệp cùng tên hoặc tệp đang tải dở.
  - Hỗ trợ Proxy (HTTP, HTTPS, SOCKS4, SOCKS5) và quản lý thông tin xác thực trang web (HTTP Basic Auth) bảo mật bằng Windows DPAPI.
  - Toàn bộ dữ liệu tạm gom vào thư mục ẩn duy nhất `.hdm_tmp` tại thư mục lưu để giữ ổ đĩa luôn gọn gàng.
- **Ràng buộc kỹ thuật bền vững**:
  - Số worker tải song song không bao giờ vượt quá tham số `num_connections` đã cấu hình.
  - Kiểm tra đối chiếu ETag khi resume để đảm bảo tính toàn vẹn dữ liệu.
  - Nút tải tiện ích mở rộng luôn neo ngoài khung video trên trang chủ `window.top`, không được chèn vào bên trong khung phát video hoặc che khuất thanh điều khiển.

## Brand Commitments

- **Tên sản phẩm**: H2M Download Manager (tên viết tắt: HDM).
- **Nhận diện thương hiệu**:
  - Biểu tượng ứng dụng: Icon vector chất lượng cao hình mũi tên tải xuống đa luồng trên nền xanh lam chuyển sắc (`app.ico`).
  - Giao diện người dùng: Thiết kế hiện đại theo phong cách Slate tinh tế, sạch sẽ, phẳng và nhất quán giữa 2 chế độ Sáng / Tối.
- **Tính cách & Giọng điệu**: Chuyên nghiệp, gọn gàng, tôn trọng quyền riêng tư (không thu thập dữ liệu cá nhân, không hiển thị quảng cáo).

## Evidence on Hand

- **Mã nguồn Desktop**: Cấu trúc module rõ ràng trong gói `hdm/` (`core/`, `gui/`, `utils/`) và điểm vào `main.py`.
- **Mã nguồn Extension**: Đầy đủ trong thư mục `extension/` (`manifest.json`, `background.js`, `content.js`, `popup.html`, `popup.js`, `content.css`).
- **Bộ đóng gói & Cài đặt**: `build_nuitka.py`, `build_installer.py`, `build_exe.py`, kịch bản Inno Setup `installer/HDM.iss`.
- **Tài liệu & Kiểm thử**: `README.md` chi tiết và bộ kiểm thử tự động `tests/test_core.py`, `tests/test_engine.py`, `tests/test_browsers.py` đạt 100% passed.

## Product Principles

1. **Hiệu năng & Tối ưu hóa triệt để**: Không bao giờ để phần mềm trở thành nút thắt cổ chai; tối ưu băng thông mạng và I/O ổ đĩa đến từng byte dữ liệu.
2. **Bảo vệ thiết bị & Phần cứng**: Tận dụng NTFS Sparse File và ghi tuần tự bất đồng bộ để tránh phân mảnh và kéo dài tuổi thọ ổ SSD/NVMe.
3. **Tiện dụng & Không xâm lấn**: Tích hợp sâu vào trình duyệt để việc tải xuống diễn ra tự nhiên trong 1 cú click, nhưng luôn tôn trọng không gian hiển thị của nội dung (không che video, không pop-up rác).
4. **Đáng tin cậy & Toàn vẹn dữ liệu**: Luôn bảo vệ an toàn cho dữ liệu người dùng; kiểm tra dung lượng ổ đĩa, đối chiếu ETag khi resume, không ghi đè tệp cũ khi chưa xác nhận.

## Accessibility & Inclusion

- Tương phản màu sắc đáp ứng tiêu chuẩn WCAG AA cho cả 2 theme Dark và Light.
- Hệ thống phím tắt đầy đủ cho người dùng bàn phím (`Ctrl+N` thêm URL, `Ctrl+T` đổi giao diện, `Delete` xóa tệp, `Enter` tải ngay).
- Hỗ trợ đa ngôn ngữ hoàn chỉnh: Tiếng Việt và Tiếng Anh (English).
