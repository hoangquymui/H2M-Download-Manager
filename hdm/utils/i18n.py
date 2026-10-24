"""Internationalization (i18n) module for H2M Download Manager (HDM).
Supports runtime switching between Vietnamese (vi) and English (en).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Supported language codes
LANG_VI = "vi"
LANG_EN = "en"

SUPPORTED_LANGUAGES: Dict[str, str] = {
    LANG_VI: "Tiếng Việt (Vietnamese)",
    LANG_EN: "English",
}

_CURRENT_LANGUAGE: str = LANG_VI

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    LANG_VI: {
        # App & Window
        "app_title": "H2M Download Manager",
        "app_subtitle": "DOWNLOAD MANAGER",
        "app_version_footer": "H2M Download Manager v1.0",

        # Menus
        "menu_file": "Tệp",
        "menu_add_url": "Thêm liên kết tải...",
        "menu_exit": "Thoát",
        "menu_tasks": "Tác vụ",
        "menu_resume_all": "Tiếp tục tất cả",
        "menu_pause_all": "Tạm dừng tất cả",
        "menu_clear_completed": "Xóa tất cả đã hoàn thành",
        "menu_tools": "Công cụ",
        "menu_settings": "Cài đặt",
        "menu_open_downloads": "Mở thư mục tải về",
        "menu_install_extension": "Cài đặt tiện ích trình duyệt...",
        "menu_help": "Trợ giúp",
        "menu_about": "Giới thiệu H2M",

        # Toolbar
        "toolbar_add_url": "Thêm URL",
        "toolbar_add_tip": "Thêm liên kết tải mới (Ctrl+N)",
        "toolbar_resume": "Tiếp tục",
        "toolbar_resume_tip": "Tiếp tục tải tác vụ đang chọn",
        "toolbar_pause": "Tạm dừng",
        "toolbar_pause_tip": "Tạm dừng tác vụ đang chọn",
        "toolbar_delete": "Xóa",
        "toolbar_delete_tip": "Xóa tác vụ và xóa luôn tệp khỏi ổ đĩa (Del)",
        "toolbar_folder": "Thư mục",
        "toolbar_folder_tip": "Mở thư mục lưu tệp tải về",
        "toolbar_settings": "Cài đặt",
        "toolbar_settings_tip": "Mở cài đặt ứng dụng",
        "toolbar_search_placeholder": "🔍 Tìm kiếm tệp...",
        "toolbar_theme_light_tip": "Chuyển sang giao diện Sáng (Ctrl+T)",
        "toolbar_theme_dark_tip": "Chuyển sang giao diện Tối (Ctrl+T)",

        # Sidebar Headers & Status Filters
        "sidebar_header_status": "TRẠNG THÁI",
        "sidebar_all": "Tất cả lượt tải",
        "sidebar_status_downloading": "Đang tải",
        "sidebar_status_completed": "Đã hoàn thành",
        "sidebar_status_paused": "Đã tạm dừng",
        "sidebar_status_error": "Lỗi / Thất bại",

        # Sidebar Category Filters
        "sidebar_header_category": "DANH MỤC TỆP",
        "cat_compressed": "Nén",
        "cat_programs": "Phần mềm",
        "cat_video": "Video",
        "cat_audio": "Âm nhạc",
        "cat_docs": "Tài liệu",
        "cat_images": "Hình ảnh",
        "cat_others": "Khác",

        # Page Header & Stats
        "page_all_title": "Tất cả lượt tải",
        "page_search_results": "{count} kết quả cho “{query}” • {total} tệp tổng cộng",
        "page_files_summary": "{count} tệp trong danh sách • {total} tệp tổng cộng",
        "page_badge_downloading": "● {count} đang tải",

        # Downloads Table Headers
        "table_filename": "Tên tệp",
        "table_category": "Danh mục",
        "table_size": "Dung lượng",
        "table_progress": "Tiến độ",
        "table_speed": "Tốc độ",
        "table_eta": "Còn lại (ETA)",
        "table_status": "Trạng thái",
        "table_date_added": "Ngày thêm",

        # Empty State
        "empty_state_text": "📥  Chưa có lượt tải nào\n\nNhấn “➕ Thêm URL” hoặc gửi liên kết từ tiện ích trình duyệt để bắt đầu.",

        # Status Bar
        "status_server_ready": "🟢 Tiện ích trình duyệt: Sẵn sàng (Port {port})",
        "status_server_disabled": "🔴 Tiện ích trình duyệt: Đã tắt",
        "status_speed": "⬇ Tốc độ: {speed}",
        "status_tasks_count": "{count} tác vụ",

        # System Tray & Close
        "tray_tooltip": "H2M Download Manager",
        "tray_open": "Mở giao diện H2M",
        "tray_pause_all": "Tạm dừng tất cả",
        "tray_resume_all": "Tiếp tục tất cả",
        "tray_exit": "Thoát hoàn toàn",
        "tray_balloon_title": "H2M Download Manager",
        "tray_balloon_msg": "Ứng dụng vẫn đang chạy ngầm trong khay hệ thống.\nNhấp chuột vào biểu tượng khay để mở lại.",

        # Table Context Menu
        "ctx_open_file": "Mở tệp",
        "ctx_open_folder": "Mở thư mục chứa",
        "ctx_view_details": "Xem chi tiết luồng tải...",
        "ctx_resume": "Tiếp tục tải",
        "ctx_pause": "Tạm dừng",
        "ctx_copy_link": "Sao chép liên kết",
        "ctx_delete": "Xóa khỏi danh sách & ổ đĩa",

        # Task Status Values
        "status_val_queued": "Hàng đợi",
        "status_val_connecting": "Đang kết nối",
        "status_val_downloading": "Đang tải",
        "status_val_paused": "Tạm dừng",
        "status_val_completed": "Hoàn thành",
        "status_val_error": "Lỗi",
        "status_val_cancelled": "Đã hủy",

        # Delete Confirmation
        "confirm_delete_title": "Xác nhận xóa tệp",
        "confirm_delete_msg": "Bạn có chắc chắn muốn xóa tác vụ:\n“{filename}”\n\nThao tác này sẽ xóa vĩnh viễn tệp khỏi ổ đĩa!",
        "btn_delete_confirm": "Xóa vĩnh viễn",
        "btn_cancel": "Hủy bỏ",

        # Add Download Dialog
        "add_dialog_title": "Thêm liên kết tải mới — H2M",
        "add_url_label": "Liên kết tải (URL):",
        "add_url_placeholder": "Dán liên kết tải tệp tại đây (http:// hoặc https://)...",
        "add_btn_check": "Kiểm tra",
        "add_btn_checking": "Đang kiểm tra...",
        "add_file_name": "Tên tệp lưu:",
        "add_save_to": "Thư mục lưu:",
        "add_btn_browse": "Chọn...",
        "add_category": "Danh mục tệp:",
        "add_connections": "Số luồng tải:",
        "add_chk_autostart": "Tự động tải ngay sau khi thêm",
        "add_btn_start": "Bắt đầu tải",
        "add_btn_close": "Đóng",
        "add_range_yes": "Hỗ trợ tải đa luồng (Range: Có)",
        "add_range_no": "Không hỗ trợ tải đa luồng (Range: Không)",
        "add_free_space": "Dung lượng trống ổ đĩa: {space}",
        "add_err_no_url": "Vui lòng nhập đường dẫn liên kết tải (URL)!",
        "add_err_invalid_url": "Đường dẫn không hợp lệ. Vui lòng nhập URL bắt đầu bằng http:// hoặc https://",

        # Download Detail Dialog & Chunk Widget
        "detail_dialog_title": "Chi tiết tải xuống — {filename}",
        "detail_lbl_filename": "Tên tệp:",
        "detail_lbl_status": "Trạng thái:",
        "detail_lbl_url": "Liên kết:",
        "detail_lbl_size": "Dung lượng:",
        "detail_lbl_speed": "Tốc độ tải:",
        "detail_remaining": "Còn lại: {eta}",
        "detail_chunk_map_title": "Bản đồ phân đoạn luồng tải (Dynamic Chunk Map):",
        "detail_legend_done": "🟢 Hoàn tất",
        "detail_legend_active": "🔵 Đang tải",
        "detail_legend_pending": "⚪ Chưa tải",
        "detail_legend_hint": "— Dynamic Segmentation tự động chia đôi phân đoạn cho luồng nhàn rỗi",
        "detail_btn_open_file": "Mở tệp",
        "detail_btn_open_dir": "Mở thư mục",
        "detail_btn_close": "Đóng",
        "chunk_col_thread": "Luồng",
        "chunk_col_range": "Phạm vi",
        "chunk_col_size": "Dung lượng",
        "chunk_col_downloaded": "Đã tải",
        "chunk_col_progress": "Tiến độ",
        "chunk_col_status": "Trạng thái",
        "chunk_st_completed": "Hoàn tất",
        "chunk_st_downloading": "Đang tải",
        "chunk_st_retry": "Thử lại",
        "chunk_st_waiting": "Chờ",

        # Settings Dialog
        "settings_dialog_title": "Cài đặt hệ thống — H2M",
        "settings_grp_storage": "📁 Tải xuống && Lưu trữ",
        "settings_default_dir": "Thư mục mặc định:",
        "settings_btn_browse": "Chọn...",
        "settings_connections": "Số luồng tải mỗi tệp:",
        "settings_max_concurrent": "Số tệp tải đồng thời tối đa:",
        "settings_chk_categorize": "Tự động chia thư mục con theo danh mục (Video, Nén, Phần mềm...)",
        "settings_chk_autostart": "Tự động tải ngay khi thêm liên kết",
        "settings_chk_start_with_windows": "Khởi động cùng Windows khi bật máy",
        "settings_grp_browser": "🌐 Tích hợp Trình duyệt && Kết nối",
        "settings_port": "Cổng kết nối nội bộ (HTTP):",
        "settings_chk_server": "Bật dịch vụ nhận link tự động từ Extension (Chrome, Edge, Cốc Cốc, Brave)",
        "settings_grp_appearance": "🎨 Giao diện && Ngôn ngữ",
        "settings_language": "Ngôn ngữ hiển thị (Language):",
        "settings_theme": "Chủ đề màu sắc:",
        "settings_theme_dark": "🌙  Tối (Dark) — dịu mắt cho ban đêm",
        "settings_theme_light": "☀  Sáng (Light) — rõ nét cho ban ngày",
        "settings_theme_hint": "Mẹo: nhấn Ctrl+T ở cửa sổ chính để chuyển nhanh Sáng / Tối.",
        "settings_btn_cancel": "Hủy bỏ",
        "settings_btn_save": "Lưu cài đặt",
        "settings_browse_dialog_title": "Chọn thư mục tải về mặc định",

        # About Dialog
        "about_title": "Giới thiệu — H2M Download Manager",
        "about_text": "<h2>H2M Download Manager v1.0</h2><p>Trình quản lý tải file đa luồng hiệu năng cao bằng Python & Qt6.</p><p>© 2026 H2M Team. Bản quyền thuộc về tác giả.</p>",
    },

    LANG_EN: {
        # App & Window
        "app_title": "H2M Download Manager",
        "app_subtitle": "DOWNLOAD MANAGER",
        "app_version_footer": "H2M Download Manager v1.0",

        # Menus
        "menu_file": "File",
        "menu_add_url": "Add URL...",
        "menu_exit": "Exit",
        "menu_tasks": "Tasks",
        "menu_resume_all": "Resume All",
        "menu_pause_all": "Pause All",
        "menu_clear_completed": "Clear Completed Tasks",
        "menu_tools": "Tools",
        "menu_settings": "Settings",
        "menu_open_downloads": "Open Downloads Folder",
        "menu_install_extension": "Install Browser Extension...",
        "menu_help": "Help",
        "menu_about": "About H2M",

        # Toolbar
        "toolbar_add_url": "Add URL",
        "toolbar_add_tip": "Add new download link (Ctrl+N)",
        "toolbar_resume": "Resume",
        "toolbar_resume_tip": "Resume selected download",
        "toolbar_pause": "Pause",
        "toolbar_pause_tip": "Pause selected download",
        "toolbar_delete": "Delete",
        "toolbar_delete_tip": "Delete download and remove file from disk (Del)",
        "toolbar_folder": "Folder",
        "toolbar_folder_tip": "Open download folder",
        "toolbar_settings": "Settings",
        "toolbar_settings_tip": "Open application settings",
        "toolbar_search_placeholder": "🔍 Search downloads...",
        "toolbar_theme_light_tip": "Switch to Light Mode (Ctrl+T)",
        "toolbar_theme_dark_tip": "Switch to Dark Mode (Ctrl+T)",

        # Sidebar Headers & Status Filters
        "sidebar_header_status": "STATUS",
        "sidebar_all": "All Downloads",
        "sidebar_status_downloading": "Downloading",
        "sidebar_status_completed": "Completed",
        "sidebar_status_paused": "Paused",
        "sidebar_status_error": "Error / Failed",

        # Sidebar Category Filters
        "sidebar_header_category": "CATEGORIES",
        "cat_compressed": "Compressed",
        "cat_programs": "Programs",
        "cat_video": "Video",
        "cat_audio": "Music",
        "cat_docs": "Documents",
        "cat_images": "Images",
        "cat_others": "Others",

        # Page Header & Stats
        "page_all_title": "All Downloads",
        "page_search_results": "{count} results for “{query}” • {total} files total",
        "page_files_summary": "{count} files in list • {total} files total",
        "page_badge_downloading": "● {count} downloading",

        # Downloads Table Headers
        "table_filename": "File Name",
        "table_category": "Category",
        "table_size": "Size",
        "table_progress": "Progress",
        "table_speed": "Speed",
        "table_eta": "Remaining (ETA)",
        "table_status": "Status",
        "table_date_added": "Date Added",

        # Empty State
        "empty_state_text": "📥  No downloads yet\n\nClick “➕ Add URL” or send links from browser extension to start.",

        # Status Bar
        "status_server_ready": "🟢 Browser Extension: Ready (Port {port})",
        "status_server_disabled": "🔴 Browser Extension: Disabled",
        "status_speed": "⬇ Speed: {speed}",
        "status_tasks_count": "{count} tasks",

        # System Tray & Close
        "tray_tooltip": "H2M Download Manager",
        "tray_open": "Open H2M Window",
        "tray_pause_all": "Pause All",
        "tray_resume_all": "Resume All",
        "tray_exit": "Exit Completely",
        "tray_balloon_title": "H2M Download Manager",
        "tray_balloon_msg": "Application is running in the background.\nClick the tray icon to restore the window.",

        # Table Context Menu
        "ctx_open_file": "Open File",
        "ctx_open_folder": "Open Containing Folder",
        "ctx_view_details": "View Download Details...",
        "ctx_resume": "Resume Download",
        "ctx_pause": "Pause",
        "ctx_copy_link": "Copy Download Link",
        "ctx_delete": "Delete Task & File",

        # Task Status Values
        "status_val_queued": "Queued",
        "status_val_connecting": "Connecting",
        "status_val_downloading": "Downloading",
        "status_val_paused": "Paused",
        "status_val_completed": "Completed",
        "status_val_error": "Error",
        "status_val_cancelled": "Cancelled",

        # Delete Confirmation
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_msg": "Are you sure you want to delete task:\n“{filename}”\n\nThis will permanently delete the file from your disk!",
        "btn_delete_confirm": "Delete Permanently",
        "btn_cancel": "Cancel",

        # Add Download Dialog
        "add_dialog_title": "Add Download Link — H2M",
        "add_url_label": "Download URL:",
        "add_url_placeholder": "Paste file download link here (http:// or https://)...",
        "add_btn_check": "Check URL",
        "add_btn_checking": "Checking...",
        "add_file_name": "Save as filename:",
        "add_save_to": "Save folder:",
        "add_btn_browse": "Browse...",
        "add_category": "File category:",
        "add_connections": "Connections:",
        "add_chk_autostart": "Start download immediately after adding",
        "add_btn_start": "Start Download",
        "add_btn_close": "Close",
        "add_range_yes": "Multi-connection supported (Range: Yes)",
        "add_range_no": "Multi-connection not supported (Range: No)",
        "add_free_space": "Available disk space: {space}",
        "add_err_no_url": "Please enter a valid download URL!",
        "add_err_invalid_url": "Invalid URL. Please enter an address starting with http:// or https://",

        # Download Detail Dialog & Chunk Widget
        "detail_dialog_title": "Download Details — {filename}",
        "detail_lbl_filename": "File name:",
        "detail_lbl_status": "Status:",
        "detail_lbl_url": "URL:",
        "detail_lbl_size": "Size:",
        "detail_lbl_speed": "Download speed:",
        "detail_remaining": "Remaining: {eta}",
        "detail_chunk_map_title": "Thread Chunk Progress Map (Dynamic Chunk Map):",
        "detail_legend_done": "🟢 Completed",
        "detail_legend_active": "🔵 Downloading",
        "detail_legend_pending": "⚪ Pending",
        "detail_legend_hint": "— Dynamic Segmentation automatically splits segments for idle threads",
        "detail_btn_open_file": "Open File",
        "detail_btn_open_dir": "Open Folder",
        "detail_btn_close": "Close",
        "chunk_col_thread": "Thread",
        "chunk_col_range": "Range",
        "chunk_col_size": "Size",
        "chunk_col_downloaded": "Downloaded",
        "chunk_col_progress": "Progress",
        "chunk_col_status": "Status",
        "chunk_st_completed": "Completed",
        "chunk_st_downloading": "Downloading",
        "chunk_st_retry": "Retry",
        "chunk_st_waiting": "Waiting",

        # Settings Dialog
        "settings_dialog_title": "Preferences — H2M",
        "settings_grp_storage": "📁 Download && Storage",
        "settings_default_dir": "Default download folder:",
        "settings_btn_browse": "Browse...",
        "settings_connections": "Connections per download:",
        "settings_max_concurrent": "Max concurrent downloads:",
        "settings_chk_categorize": "Organize into category folders (Video, Compressed, Programs...)",
        "settings_chk_autostart": "Start downloads automatically when added",
        "settings_chk_start_with_windows": "Start HDM automatically with Windows",
        "settings_grp_browser": "🌐 Browser Integration && Connection",
        "settings_port": "Internal HTTP port:",
        "settings_chk_server": "Enable browser extension integration (Chrome, Edge, Cốc Cốc, Brave)",
        "settings_grp_appearance": "🎨 Appearance && Language",
        "settings_language": "Display Language:",
        "settings_theme": "Color Theme:",
        "settings_theme_dark": "🌙  Dark — easy on the eyes",
        "settings_theme_light": "☀  Light — crisp daylight contrast",
        "settings_theme_hint": "Tip: Press Ctrl+T on the main window to quickly toggle Dark/Light.",
        "settings_btn_cancel": "Cancel",
        "settings_btn_save": "Save Settings",
        "settings_browse_dialog_title": "Choose default download directory",

        # About Dialog
        "about_title": "About — H2M Download Manager",
        "about_text": "<h2>H2M Download Manager v1.0</h2><p>High-performance multi-connection download manager built with Python & Qt6.</p><p>© 2026 H2M Team. All rights reserved.</p>",
    },
}


def normalize_language(lang: Optional[str]) -> str:
    """Normalize language code to supported values."""
    if not lang:
        return LANG_VI
    lang_lower = str(lang).strip().lower()
    if lang_lower in (LANG_EN, "english", "en_us", "en-us", "en_gb", "en-gb"):
        return LANG_EN
    return LANG_VI


def set_language(lang: str) -> str:
    """Set the active language code."""
    global _CURRENT_LANGUAGE
    _CURRENT_LANGUAGE = normalize_language(lang)
    return _CURRENT_LANGUAGE


def get_language() -> str:
    """Get the active language code."""
    return _CURRENT_LANGUAGE


def tr(key: str, **kwargs: Any) -> str:
    """Translate a message key into current language with optional formatting."""
    lang = get_language()
    dict_lang = TRANSLATIONS.get(lang, TRANSLATIONS[LANG_VI])
    text = dict_lang.get(key)
    if text is None:
        # Fallback to Vietnamese
        text = TRANSLATIONS[LANG_VI].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


CATEGORY_EMOJIS: Dict[str, str] = {
    "cat_compressed": "📦",
    "cat_programs": "💻",
    "cat_video": "🎬",
    "cat_audio": "🎵",
    "cat_docs": "📄",
    "cat_images": "🖼",
    "cat_others": "📂",
}


def get_status_display(status_val: Any) -> str:
    """Translate task status for table/badge display."""
    if hasattr(status_val, "value"):
        status_val = status_val.value
    mapping = {
        "Hàng đợi": "status_val_queued",
        "Đang kết nối": "status_val_connecting",
        "Đang tải": "status_val_downloading",
        "Tạm dừng": "status_val_paused",
        "Hoàn thành": "status_val_completed",
        "Lỗi": "status_val_error",
        "Đã hủy": "status_val_cancelled",
        # English equivalents just in case
        "Queued": "status_val_queued",
        "Connecting": "status_val_connecting",
        "Downloading": "status_val_downloading",
        "Paused": "status_val_paused",
        "Completed": "status_val_completed",
        "Error": "status_val_error",
        "Cancelled": "status_val_cancelled",
    }
    key = mapping.get(str(status_val))
    if key:
        return tr(key)
    return str(status_val)


def get_category_display(category: Any) -> str:
    """Translate category name with emoji for table/dialog display."""
    if hasattr(category, "value"):
        category = category.value
    mapping = {
        "Nén": "cat_compressed",
        "Phần mềm": "cat_programs",
        "Video": "cat_video",
        "Âm nhạc": "cat_audio",
        "Tài liệu": "cat_docs",
        "Hình ảnh": "cat_images",
        "Khác": "cat_others",
        "Compressed": "cat_compressed",
        "Programs": "cat_programs",
        "Video": "cat_video",
        "Audio": "cat_audio",
        "Documents": "cat_docs",
        "Images": "cat_images",
        "Others": "cat_others",
    }
    cat_str = str(category)
    key = mapping.get(cat_str)
    if key:
        emoji = CATEGORY_EMOJIS.get(key, "")
        return f"{emoji} {tr(key)}" if emoji else tr(key)
    return cat_str
