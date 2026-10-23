"""Main Application Window for HDM (H2M Download Manager).
Features sidebar categories, dynamic task counters, live search, modern table view,
toolbar actions, light/dark theme switching, system tray, and smooth real-time
progress updates.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize
from PySide6.QtGui import QAction, QCursor, QKeySequence, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSystemTrayIcon,
)

from hdm.core.config import ConfigManager
from hdm.core.manager import DownloadQueueManager
from hdm.core.models import DownloadTask, TaskStatus
from hdm.gui.add_dialog import AddDownloadDialog
from hdm.gui.detail_dialog import DownloadDetailDialog
from hdm.gui.icons import get_icon
from hdm.gui.settings_dialog import SettingsDialog
from hdm.gui.style import apply_theme, current_theme, get_palette, normalize_theme
from hdm.utils.category import FileCategory
from hdm.utils.formatters import format_bytes, format_date, format_eta, format_speed
from hdm.utils.system import get_app_icon, launch_file, open_file_in_explorer, open_folder

CATEGORY_DISPLAY = {
    FileCategory.COMPRESSED.value: "📦 Nén",
    FileCategory.PROGRAMS.value: "💻 Phần mềm",
    FileCategory.VIDEO.value: "🎬 Video",
    FileCategory.AUDIO.value: "🎵 Âm nhạc",
    FileCategory.DOCUMENTS.value: "📄 Tài liệu",
    FileCategory.IMAGES.value: "🖼 Hình ảnh",
    FileCategory.OTHERS.value: "📂 Khác",
    "Compressed": "📦 Nén",
    "Programs": "💻 Phần mềm",
    "Video": "🎬 Video",
    "Audio": "🎵 Âm nhạc",
    "Documents": "📄 Tài liệu",
    "Images": "🖼 Hình ảnh",
    "Others": "📂 Khác",
}

STATUS_FILTERS = [
    ("all", "", "Tất cả lượt tải"),
    ("status_downloading", "⚡", "Đang tải"),
    ("status_completed", "✅", "Đã hoàn thành"),
    ("status_paused", "⏸", "Đã tạm dừng"),
    ("status_error", "❌", "Lỗi / Thất bại"),
]

CATEGORY_FILTERS = [
    ("cat_compressed", "📦", "Nén"),
    ("cat_programs", "💻", "Phần mềm"),
    ("cat_video", "🎬", "Video"),
    ("cat_audio", "🎵", "Âm nhạc"),
    ("cat_docs", "📄", "Tài liệu"),
    ("cat_images", "🖼", "Hình ảnh"),
    ("cat_others", "📂", "Khác"),
]

FILTER_TITLES: Dict[str, str] = {
    code: title for code, _emoji, title in STATUS_FILTERS + CATEGORY_FILTERS
}
FILTER_EMOJI: Dict[str, str] = {
    code: emoji for code, emoji, _title in STATUS_FILTERS + CATEGORY_FILTERS
}


def sidebar_label(code: str, count: Optional[int] = None) -> str:
    """Build the display text of a sidebar entry, optionally with a live counter."""
    emoji = FILTER_EMOJI.get(code, "")
    title = FILTER_TITLES.get(code, code)
    text = f"  {emoji} {title}" if emoji else f"  {title}"
    return f"{text} ({count})" if count is not None else text


def build_status_colors() -> Dict[TaskStatus, str]:
    """Status text colors matching the currently active theme."""
    p = get_palette()
    return {
        TaskStatus.COMPLETED: p["success"],
        TaskStatus.DOWNLOADING: p["info"],
        TaskStatus.CONNECTING: p["cyan"],
        TaskStatus.QUEUED: p["purple"],
        TaskStatus.PAUSED: p["warning"],
        TaskStatus.ERROR: p["danger"],
        TaskStatus.CANCELLED: p["muted"],
    }


class MainBridge(QObject):
    """Bridge for cross-thread signals into the Qt GUI thread."""
    task_added_signal = Signal(object)
    task_updated_signal = Signal(object)
    show_window_signal = Signal()


class MainWindow(QMainWindow):
    """HDM Desktop Main Window."""

    def __init__(self, manager: DownloadQueueManager, config_manager: ConfigManager) -> None:
        super().__init__()
        self.manager = manager
        self.config_manager = config_manager
        self.config = config_manager.config

        self.bridge = MainBridge()
        self.bridge.task_added_signal.connect(self._on_task_added_signal)
        self.bridge.task_updated_signal.connect(self._on_task_updated_signal)
        self.bridge.show_window_signal.connect(self.show_and_raise)

        # Connect manager callbacks to bridge
        self.manager.on_task_added = lambda t: self.bridge.task_added_signal.emit(t)
        self.manager.on_task_updated = lambda t: self.bridge.task_updated_signal.emit(t)

        self.current_filter_category: Optional[str] = None
        self.current_filter_status: Optional[TaskStatus] = None
        self.current_filter_code: str = "all"
        self.search_query: str = ""

        self.theme: str = current_theme()
        self.palette_colors: Dict[str, str] = get_palette(self.theme)
        self.status_colors: Dict[TaskStatus, str] = build_status_colors()

        self.setWindowTitle("H2M Download Manager")
        self.resize(1240, 760)
        self.setMinimumSize(1000, 600)

        self._init_ui()
        self._init_tray()

        # Ensure theme and stylesheet are polished onto all widgets from start
        self.set_theme(self.theme, persist=False)

        # Table update timer (500ms)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._refresh_table_data)
        self.update_timer.start(500)

        self._reload_table_full()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        main_layout.addWidget(splitter)

        # 1. Left sidebar panel (brand + filters + footer)
        splitter.addWidget(self._build_sidebar_panel())

        # 2. Main content area (page header + downloads table)
        splitter.addWidget(self._build_content_area())
        splitter.setSizes([236, 1004])

        # 3. Menu Bar & Tool Bar
        self._create_menus()
        self._create_toolbar()

        # 4. Status Bar
        self.status_bar = QStatusBar(self)
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)

        self.lbl_server_status = QLabel(
            f"🟢 Tiện ích trình duyệt: Sẵn sàng (Port {self.config.server_port})", self
        )
        self.lbl_server_status.setObjectName("status_server")

        self.lbl_speed_summary = QLabel("⬇ Tốc độ: 0 KB/s", self)
        self.lbl_speed_summary.setObjectName("status_speed")

        self.lbl_tasks_summary = QLabel("0 tác vụ", self)
        self.lbl_tasks_summary.setObjectName("status_tasks")

        self.status_bar.addWidget(self.lbl_server_status, 1)
        self.status_bar.addPermanentWidget(self.lbl_speed_summary)
        self.status_bar.addPermanentWidget(self.lbl_tasks_summary)

        self._update_page_header()

    def _build_sidebar_panel(self) -> QWidget:
        """Left column: brand block, filter list and version footer."""
        panel = QWidget(self)
        panel.setObjectName("sidebar_container")
        panel.setFixedWidth(236)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Brand header
        brand = QWidget(panel)
        brand.setObjectName("brand_bar")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(16, 13, 12, 13)
        brand_layout.setSpacing(10)

        logo = QLabel(brand)
        logo.setPixmap(get_app_icon().pixmap(30, 30))
        logo.setFixedSize(32, 32)
        brand_layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)

        lbl_title = QLabel("H2M", brand)
        lbl_title.setObjectName("brand_title")
        lbl_sub = QLabel("DOWNLOAD MANAGER", brand)
        lbl_sub.setObjectName("brand_sub")
        titles.addWidget(lbl_title)
        titles.addWidget(lbl_sub)

        brand_layout.addLayout(titles)
        brand_layout.addStretch()
        layout.addWidget(brand)

        # Filter list
        self.sidebar = QListWidget(panel)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFrameShape(QFrame.NoFrame)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._build_sidebar()
        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        layout.addWidget(self.sidebar, 1)

        footer = QLabel("H2M Download Manager v1.0", panel)
        footer.setObjectName("sidebar_footer")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

        return panel

    def _build_content_area(self) -> QWidget:
        """Right column: page header, downloads table card and empty state."""
        content = QWidget(self)
        content.setObjectName("content_area")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(10)

        # Page header
        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 2, 0)
        header_row.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)

        self.page_title = QLabel("Tất cả lượt tải", content)
        self.page_title.setObjectName("page_title")
        self.page_subtitle = QLabel("0 tệp trong danh sách", content)
        self.page_subtitle.setObjectName("page_subtitle")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)

        header_row.addLayout(title_box)
        header_row.addStretch()

        self.page_badge = QLabel("● 0 đang tải", content)
        self.page_badge.setObjectName("page_badge")
        header_row.addWidget(self.page_badge)
        layout.addLayout(header_row)

        # Table inside a rounded card
        card = QFrame(content)
        card.setObjectName("table_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(1, 1, 1, 1)
        card_layout.setSpacing(0)

        self.table = QTableWidget(card)
        self.table.setObjectName("download_table")
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Tên tệp", "Danh mục", "Dung lượng", "Tiến độ", "Tốc độ", "Còn lại (ETA)", "Trạng thái", "Ngày thêm"
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(70)

        for column, width in ((1, 112), (2, 100), (3, 190), (4, 104), (5, 108), (6, 106), (7, 126)):
            self.table.setColumnWidth(column, width)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_table_double_clicked)

        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)

        # Friendly empty state shown when no task matches the current filter
        self.empty_label = QLabel(
            "📥  Chưa có lượt tải nào\n\n"
            "Nhấn “➕ Thêm URL” hoặc gửi liên kết từ tiện ích trình duyệt để bắt đầu.",
            self.table.viewport(),
        )
        self.empty_label.setObjectName("empty_state")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.empty_label.hide()

        return content

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_empty_state()

    def _position_empty_state(self) -> None:
        """Keep the empty-state overlay centered inside the table viewport."""
        label = getattr(self, "empty_label", None)
        if label is not None:
            label.setGeometry(self.table.viewport().rect())

    def _build_sidebar(self) -> None:
        self.sidebar.clear()
        self._add_sidebar_header("TRẠNG THÁI")
        for code, _emoji, _title in STATUS_FILTERS:
            self._add_sidebar_item(code)

        self._add_sidebar_header("DANH MỤC TỆP")
        for code, _emoji, _title in CATEGORY_FILTERS:
            self._add_sidebar_item(code)

        self._update_sidebar_counts()
        self.sidebar.setCurrentRow(1)

    def _add_sidebar_header(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setData(Qt.UserRole, "header")
        font = item.font()
        font.setBold(True)
        font.setPointSize(9)
        item.setFont(font)
        self.sidebar.addItem(item)

    def _add_sidebar_item(self, code: str) -> None:
        item = QListWidgetItem(sidebar_label(code))
        item.setData(Qt.UserRole, code)
        item.setSizeHint(QSize(0, 34))
        self.sidebar.addItem(item)

    def _update_sidebar_counts(self) -> None:
        """Update live task counts shown next to each category and filter item."""
        all_tasks = list(self.manager.tasks.values())
        counts = {
            "all": len(all_tasks),
            "status_downloading": sum(1 for t in all_tasks if t.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING)),
            "status_completed": sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED),
            "status_paused": sum(1 for t in all_tasks if t.status == TaskStatus.PAUSED),
            "status_error": sum(1 for t in all_tasks if t.status == TaskStatus.ERROR),
            "cat_compressed": sum(1 for t in all_tasks if t.category in (FileCategory.COMPRESSED.value, "Compressed")),
            "cat_programs": sum(1 for t in all_tasks if t.category in (FileCategory.PROGRAMS.value, "Programs")),
            "cat_video": sum(1 for t in all_tasks if t.category in (FileCategory.VIDEO.value, "Video")),
            "cat_audio": sum(1 for t in all_tasks if t.category in (FileCategory.AUDIO.value, "Audio")),
            "cat_docs": sum(1 for t in all_tasks if t.category in (FileCategory.DOCUMENTS.value, "Documents")),
            "cat_images": sum(1 for t in all_tasks if t.category in (FileCategory.IMAGES.value, "Images")),
            "cat_others": sum(1 for t in all_tasks if t.category in (FileCategory.OTHERS.value, "Others")),
        }
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            code = item.data(Qt.UserRole)
            if code and code != "header" and code in counts:
                item.setText(sidebar_label(code, counts[code]))

        self._update_page_header()

    def _create_menus(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("Tệp")
        act_add = QAction("Thêm liên kết tải...", self)
        act_add.setShortcut(QKeySequence("Ctrl+N"))
        act_add.triggered.connect(self.show_add_dialog)
        file_menu.addAction(act_add)

        file_menu.addSeparator()
        act_exit = QAction("Thoát", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Tasks Menu
        tasks_menu = menubar.addMenu("Tác vụ")
        act_resume_all = QAction("Tiếp tục tất cả", self)
        act_resume_all.triggered.connect(self.manager.resume_all)
        tasks_menu.addAction(act_resume_all)

        act_pause_all = QAction("Tạm dừng tất cả", self)
        act_pause_all.triggered.connect(self.manager.pause_all)
        tasks_menu.addAction(act_pause_all)

        # Tools Menu
        tools_menu = menubar.addMenu("Công cụ")
        act_settings = QAction("Cài đặt...", self)
        act_settings.triggered.connect(self.show_settings_dialog)
        tools_menu.addAction(act_settings)

        self.act_toggle_theme = QAction("Chuyển Giao diện Sáng / Tối", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+T"))
        self.act_toggle_theme.setCheckable(False)
        self.act_toggle_theme.triggered.connect(self.toggle_theme)
        tools_menu.addAction(self.act_toggle_theme)

        act_ext = QAction("Thư mục Tiện ích trình duyệt (Extension)", self)
        act_ext.triggered.connect(self._open_extension_dir)
        tools_menu.addAction(act_ext)

        # Help Menu
        help_menu = menubar.addMenu("Trợ giúp")
        act_about = QAction("Giới thiệu HDM", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("MainToolbar", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # Primary Add Button with crisp vector icon
        self.btn_add_action = toolbar.addAction(get_icon("add", "#FFFFFF"), "Thêm URL")
        self.btn_add_action.setToolTip("Thêm liên kết tải mới (Ctrl+N)")
        self.btn_add_action.triggered.connect(self.show_add_dialog)
        btn_add_widget = toolbar.widgetForAction(self.btn_add_action)
        if btn_add_widget:
            btn_add_widget.setObjectName("btn_primary_add")

        toolbar.addSeparator()

        text_color = self.palette_colors.get("text", "#F1F5F9")

        self.btn_resume_action = toolbar.addAction(get_icon("resume", text_color), "Tiếp tục")
        self.btn_resume_action.setToolTip("Tiếp tục tải tác vụ đang chọn")
        self.btn_resume_action.triggered.connect(self._on_action_resume)

        self.btn_pause_action = toolbar.addAction(get_icon("pause", text_color), "Tạm dừng")
        self.btn_pause_action.setToolTip("Tạm dừng tác vụ đang chọn")
        self.btn_pause_action.triggered.connect(self._on_action_pause)

        self.btn_delete_action = toolbar.addAction(get_icon("delete", text_color), "Xóa")
        self.btn_delete_action.setShortcut(QKeySequence.Delete)
        self.btn_delete_action.setToolTip("Xóa tác vụ và xóa luôn tệp khỏi ổ đĩa (Del)")
        self.btn_delete_action.triggered.connect(self._on_action_delete)

        toolbar.addSeparator()

        self.btn_folder_action = toolbar.addAction(get_icon("folder", text_color), "Thư mục")
        self.btn_folder_action.setToolTip("Mở thư mục lưu tệp tải về")
        self.btn_folder_action.triggered.connect(self._on_action_open_folder)

        self.btn_settings_action = toolbar.addAction(get_icon("settings", text_color), "Cài đặt")
        self.btn_settings_action.setToolTip("Mở cài đặt ứng dụng")
        self.btn_settings_action.triggered.connect(self.show_settings_dialog)

        # Expanding spacer pushing search box to the right (transparent, no gray box!)
        spacer = QWidget(self)
        spacer.setObjectName("toolbar_spacer")
        spacer.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Search Box
        self.search_input = QLineEdit(self)
        self.search_input.setObjectName("search_input")
        self.search_input.setPlaceholderText("🔍 Tìm kiếm tệp...")
        self.search_input.setFixedWidth(230)
        self.search_input.setFixedHeight(30)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_input)

        # Theme toggle with vector sun/moon icon
        self.btn_theme = QToolButton(self)
        self.btn_theme.setObjectName("theme_toggle")
        self.btn_theme.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.setFixedSize(32, 30)
        self.btn_theme.clicked.connect(self.toggle_theme)
        toolbar.addWidget(self.btn_theme)
        self._sync_theme_button()

    # ------------------------------------------------------------------
    # Theme handling
    # ------------------------------------------------------------------
    def toggle_theme(self) -> None:
        """Switch between the dark and light appearance."""
        self.set_theme("light" if self.theme == "dark" else "dark")

    def set_theme(self, theme: str, persist: bool = True) -> None:
        """Apply *theme*, refresh theme-dependent widgets and persist the choice."""
        self.theme = apply_theme(QApplication.instance(), theme)
        self.palette_colors = get_palette(self.theme)
        self.status_colors = build_status_colors()

        self._sync_theme_button()
        self._reload_table_full()
        self._sync_empty_state()
        self._position_empty_state()

        if persist:
            self.config.theme = self.theme
            self.config_manager.save()

    def _sync_theme_button(self) -> None:
        """Update the toolbar toggle glyph/tooltip and icon colors for the active theme."""
        button = getattr(self, "btn_theme", None)
        if button is not None:
            going_light = self.theme == "dark"
            button.setIcon(get_icon("sun" if going_light else "moon", self.palette_colors["text"], size=18))
            button.setToolTip(
                "Chuyển sang giao diện Sáng (Ctrl+T)" if going_light
                else "Chuyển sang giao diện Tối (Ctrl+T)"
            )

        # Synchronize action icons to match active theme text color
        if hasattr(self, "btn_resume_action"):
            text_color = self.palette_colors.get("text", "#F1F5F9")
            self.btn_add_action.setIcon(get_icon("add", "#FFFFFF"))
            self.btn_resume_action.setIcon(get_icon("resume", text_color))
            self.btn_pause_action.setIcon(get_icon("pause", text_color))
            self.btn_delete_action.setIcon(get_icon("delete", text_color))
            self.btn_folder_action.setIcon(get_icon("folder", text_color))
            self.btn_settings_action.setIcon(get_icon("settings", text_color))

    def _update_page_header(self) -> None:
        """Keep the page title, subtitle and active-task badge in sync."""
        if not hasattr(self, "page_title"):
            return
        self.page_title.setText(FILTER_TITLES.get(self.current_filter_code, "Tất cả lượt tải"))

        visible = self.table.rowCount() if hasattr(self, "table") else 0
        total = len(self.manager.tasks)
        if self.search_query:
            self.page_subtitle.setText(
                f"{visible} kết quả cho “{self.search_query}” • {total} tệp tổng cộng"
            )
        else:
            self.page_subtitle.setText(f"{visible} tệp trong danh sách • {total} tệp tổng cộng")
        self.page_badge.setText(f"● {self.manager.get_active_count()} đang tải")

    def _sync_empty_state(self) -> None:
        """Show the friendly placeholder only when the table has no rows."""
        label = getattr(self, "empty_label", None)
        if label is None:
            return
        if self.table.rowCount() == 0:
            label.show()
            label.raise_()
            self._position_empty_state()
        else:
            label.hide()

    def _init_tray(self) -> None:
        icon = get_app_icon()
        self.setWindowIcon(icon)

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setIcon(icon)
            self.tray.setToolTip("HDM — H2M Download Manager")

            tray_menu = QMenu(self)
            act_show = tray_menu.addAction("Mở giao diện HDM")
            act_show.triggered.connect(self.show_and_raise)

            tray_menu.addSeparator()
            act_pause = tray_menu.addAction("Tạm dừng tất cả")
            act_pause.triggered.connect(self.manager.pause_all)

            act_resume = tray_menu.addAction("Tiếp tục tất cả")
            act_resume.triggered.connect(self.manager.resume_all)

            tray_menu.addSeparator()
            act_quit = tray_menu.addAction("Thoát hoàn toàn")
            act_quit.triggered.connect(QApplication.instance().quit)

            self.tray.setContextMenu(tray_menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_and_raise()

    def show_and_raise(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()
        self.raise_()

    def show_add_dialog(self, initial_url: str = "") -> None:
        dlg = AddDownloadDialog(self.config, initial_url=initial_url, parent=self)
        if dlg.exec():
            data = dlg.get_result_data()
            self.manager.add_task(
                url=data["url"],
                save_dir=data["save_dir"],
                filename=data["filename"],
                connections=data["connections"],
                auto_start=data["auto_start"],
            )

    def show_settings_dialog(self) -> None:
        dlg = SettingsDialog(self.config_manager, parent=self)
        dlg.exec()
        saved_theme = normalize_theme(self.config.theme)
        if saved_theme != self.theme:
            self.set_theme(saved_theme, persist=False)

    def _open_extension_dir(self) -> None:
        ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "extension"))
        if not os.path.exists(ext_dir):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ext_dir = os.path.join(base_dir, "extension")
        if os.path.exists(ext_dir):
            open_folder(ext_dir)
        else:
            QMessageBox.information(
                self,
                "Extension",
                f"Thư mục Tiện ích trình duyệt (Extension):\n{ext_dir}\n\nHãy vào chrome://extensions và chọn 'Load unpacked'."
            )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "Giới thiệu HDM",
            "<h3>HDM — H2M Download Manager</h3>"
            "<p>Trình quản lý tải file đa luồng tốc độ cao với thuật toán <b>Dynamic Segmentation</b>.</p>"
            "<ul>"
            "<li><b>Dynamic Work Stealing:</b> Chia động phân đoạn tải khi luồng hoàn thành sớm.</li>"
            "<li><b>Zero-Copy Direct File Writing:</b> NTFS Sparse File, ghi trực tiếp không cần ghép tệp.</li>"
            "<li><b>Browser Integration:</b> Tự động bắt link thông minh từ Chrome, Edge, Cốc Cốc.</li>"
            "<li><b>Chunk Map trực quan:</b> Hiển thị tiến trình từng luồng phân đoạn theo thời gian thực.</li>"
            "</ul>"
            "<p>© 2026 H2M Team. Mọi quyền được bảo lưu.</p>"
        )

    def _on_search_changed(self, text: str) -> None:
        self.search_query = text.strip().lower()
        self._reload_table_full()

    def _on_sidebar_changed(self, row: int) -> None:
        item = self.sidebar.item(row)
        if not item:
            return
        code = item.data(Qt.UserRole)
        if not code or code == "header":
            return

        self.current_filter_code = code
        self.current_filter_category = None
        self.current_filter_status = None

        if code == "all":
            pass
        elif code == "status_downloading":
            self.current_filter_status = TaskStatus.DOWNLOADING
        elif code == "status_completed":
            self.current_filter_status = TaskStatus.COMPLETED
        elif code == "status_paused":
            self.current_filter_status = TaskStatus.PAUSED
        elif code == "status_error":
            self.current_filter_status = TaskStatus.ERROR
        elif code == "cat_compressed":
            self.current_filter_category = FileCategory.COMPRESSED.value
        elif code == "cat_programs":
            self.current_filter_category = FileCategory.PROGRAMS.value
        elif code == "cat_video":
            self.current_filter_category = FileCategory.VIDEO.value
        elif code == "cat_audio":
            self.current_filter_category = FileCategory.AUDIO.value
        elif code == "cat_docs":
            self.current_filter_category = FileCategory.DOCUMENTS.value
        elif code == "cat_images":
            self.current_filter_category = FileCategory.IMAGES.value
        elif code == "cat_others":
            self.current_filter_category = FileCategory.OTHERS.value

        self._reload_table_full()

    def _get_filtered_tasks(self) -> List[DownloadTask]:
        tasks = list(self.manager.tasks.values())
        if self.current_filter_status is not None:
            tasks = [t for t in tasks if t.status == self.current_filter_status]
        if self.current_filter_category is not None:
            cat_val = self.current_filter_category
            tasks = [
                t for t in tasks
                if t.category == cat_val or
                   (cat_val == FileCategory.COMPRESSED.value and t.category == "Compressed") or
                   (cat_val == FileCategory.PROGRAMS.value and t.category == "Programs") or
                   (cat_val == FileCategory.VIDEO.value and t.category == "Video") or
                   (cat_val == FileCategory.AUDIO.value and t.category == "Audio") or
                   (cat_val == FileCategory.DOCUMENTS.value and t.category == "Documents") or
                   (cat_val == FileCategory.IMAGES.value and t.category == "Images") or
                   (cat_val == FileCategory.OTHERS.value and t.category == "Others")
            ]
        if self.search_query:
            tasks = [
                t for t in tasks
                if self.search_query in t.filename.lower() or self.search_query in t.url.lower()
            ]
        # Sort by creation date descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def _reload_table_full(self) -> None:
        tasks = self._get_filtered_tasks()
        self.table.setRowCount(len(tasks))

        colors = self.palette_colors
        bold_font = QFont()
        bold_font.setBold(True)

        for row, task in enumerate(tasks):
            # 0. Filename
            item_name = QTableWidgetItem(task.filename)
            item_name.setData(Qt.UserRole, task.id)
            item_name.setToolTip(f"{task.filename}\n{task.url}")
            self.table.setItem(row, 0, item_name)

            # 1. Category
            cat_display = CATEGORY_DISPLAY.get(task.category, task.category)
            self.table.setItem(row, 1, QTableWidgetItem(cat_display))

            # 2. Size
            size_str = format_bytes(task.total_bytes) if task.total_bytes > 0 else "Không rõ"
            item_size = QTableWidgetItem(size_str)
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, item_size)

            # 3. Progress Bar container (reused across reloads so that fast
            #    filter/theme switches never leak stale widgets over row 0)
            container = self.table.cellWidget(row, 3)
            if container is None:
                container = QWidget()
                layout_p = QHBoxLayout(container)
                layout_p.setContentsMargins(8, 8, 8, 8)
                pbar = QProgressBar(container)
                pbar.setRange(0, 100)
                pbar.setTextVisible(True)
                pbar.setFixedHeight(18)
                layout_p.addWidget(pbar)
                self.table.setCellWidget(row, 3, container)
            pbar = container.findChild(QProgressBar)
            if pbar is not None:
                pbar.setValue(int(task.progress_percent))
                pbar.setFormat(f"{task.progress_percent:.1f}%")

            # 4. Speed
            if task.status == TaskStatus.DOWNLOADING and task.speed > 0:
                item_speed = QTableWidgetItem(format_speed(task.speed))
                item_speed.setForeground(QColor(colors["cyan"]))
                item_speed.setFont(bold_font)
            else:
                item_speed = QTableWidgetItem("--")
                item_speed.setForeground(QColor(colors["text_faint"]))
            item_speed.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, item_speed)

            # 5. ETA
            eta_str = format_eta(task.eta) if task.status == TaskStatus.DOWNLOADING else "--"
            item_eta = QTableWidgetItem(eta_str)
            item_eta.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, item_eta)

            # 6. Status with color badge
            item_status = QTableWidgetItem(task.status.value)
            item_status.setTextAlignment(Qt.AlignCenter)
            item_status.setForeground(QColor(self.status_colors.get(task.status, colors["text"])))
            item_status.setFont(bold_font)
            self.table.setItem(row, 6, item_status)

            # 7. Date
            item_date = QTableWidgetItem(format_date(task.created_at))
            item_date.setTextAlignment(Qt.AlignCenter)
            item_date.setForeground(QColor(colors["muted"]))
            self.table.setItem(row, 7, item_date)

        self._update_sidebar_counts()
        self._sync_empty_state()

    def _refresh_table_data(self) -> None:
        """Poll and refresh row progress, speeds, and status bar."""
        total_speed = self.manager.get_total_speed()
        active_count = self.manager.get_active_count()
        total_count = len(self.manager.tasks)

        self.lbl_speed_summary.setText(f"⬇ Tốc độ: {format_speed(total_speed)}")
        self.lbl_tasks_summary.setText(f"📊 {active_count} đang tải / {total_count} tổng số")
        self._update_page_header()

        colors = self.palette_colors
        bold_font = QFont()
        bold_font.setBold(True)

        for row in range(self.table.rowCount()):
            item_name = self.table.item(row, 0)
            if not item_name:
                continue
            task_id = item_name.data(Qt.UserRole)
            task = self.manager.tasks.get(task_id)
            if not task:
                continue

            # Update progress bar
            container = self.table.cellWidget(row, 3)
            if container:
                pbar = container.findChild(QProgressBar)
                if pbar:
                    pbar.setValue(int(task.progress_percent))
                    pbar.setFormat(f"{task.progress_percent:.1f}%")

            # Update speed
            item_speed = self.table.item(row, 4)
            if item_speed:
                if task.status == TaskStatus.DOWNLOADING and task.speed > 0:
                    item_speed.setText(format_speed(task.speed))
                    item_speed.setForeground(QColor(colors["cyan"]))
                    item_speed.setFont(bold_font)
                else:
                    item_speed.setText("--")
                    item_speed.setForeground(QColor(colors["text_faint"]))

            # Update ETA
            item_eta = self.table.item(row, 5)
            if item_eta:
                eta_str = format_eta(task.eta) if task.status == TaskStatus.DOWNLOADING else "--"
                item_eta.setText(eta_str)

            # Update status
            item_status = self.table.item(row, 6)
            if item_status:
                item_status.setText(task.status.value)
                item_status.setForeground(QColor(self.status_colors.get(task.status, colors["text"])))
                item_status.setFont(bold_font)

    def _on_task_added_signal(self, task: DownloadTask) -> None:
        self._reload_table_full()

    def _on_task_updated_signal(self, task: DownloadTask) -> None:
        # Check if completed to show balloon notification
        if task.status == TaskStatus.COMPLETED and hasattr(self, "tray") and self.tray.isVisible():
            self.tray.showMessage(
                "HDM — Tải hoàn tất!",
                f"Tệp {task.filename} đã được tải về thành công.",
                QSystemTrayIcon.Information,
                3000
            )

    def _get_selected_task(self) -> Optional[DownloadTask]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        task_id = item.data(Qt.UserRole)
        return self.manager.tasks.get(task_id)

    def _on_table_double_clicked(self) -> None:
        task = self._get_selected_task()
        if task:
            dlg = DownloadDetailDialog(task, parent=self)
            dlg.exec()

    def _show_context_menu(self, pos) -> None:
        task = self._get_selected_task()
        if not task:
            return

        menu = QMenu(self)

        act_detail = menu.addAction("🔍 Xem chi tiết & Chunk Map...")
        act_detail.triggered.connect(lambda: DownloadDetailDialog(task, parent=self).exec())

        menu.addSeparator()

        if task.status in (TaskStatus.PAUSED, TaskStatus.ERROR, TaskStatus.CANCELLED):
            act_resume = menu.addAction("▶ Tiếp tục tải")
            act_resume.triggered.connect(lambda: self.manager.start_task(task.id))
        elif task.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING, TaskStatus.QUEUED):
            act_pause = menu.addAction("❚❚ Tạm dừng")
            act_pause.triggered.connect(lambda: self.manager.pause_task(task.id))

        if task.status == TaskStatus.COMPLETED:
            act_open_file = menu.addAction("Mở tệp")
            act_open_file.triggered.connect(lambda: launch_file(task.full_path))

        act_open_dir = menu.addAction("📁 Mở thư mục chứa")
        act_open_dir.triggered.connect(lambda: open_file_in_explorer(task.full_path))

        act_copy_url = menu.addAction("📋 Sao chép liên kết")
        act_copy_url.triggered.connect(lambda: QApplication.clipboard().setText(task.url))

        menu.addSeparator()

        act_del_file = menu.addAction("🗑 Xóa khỏi danh sách & Xóa tệp trên đĩa")
        act_del_file.triggered.connect(lambda: self._confirm_delete(task, delete_file=True))

        act_del = menu.addAction("Chỉ xóa khỏi danh sách (giữ tệp trên đĩa)")
        act_del.triggered.connect(lambda: self._confirm_delete(task, delete_file=False))

        menu.exec(QCursor.pos())

    def _confirm_delete(self, task: DownloadTask, delete_file: bool = True) -> None:
        if delete_file:
            msg = f"Bạn có chắc muốn xóa '{task.filename}' và toàn bộ tệp trong thư mục đang chứa?"
            title = "Xác nhận xóa tệp và tác vụ"
        else:
            msg = f"Bạn có chắc muốn xóa '{task.filename}' khỏi danh sách tải về (không xóa tệp trên đĩa)?"
            title = "Xác nhận xóa khỏi danh sách"

        res = QMessageBox.question(self, title, msg, QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.manager.delete_task(task.id, delete_file=delete_file)
            self._reload_table_full()

    def _on_action_resume(self) -> None:
        task = self._get_selected_task()
        if task:
            self.manager.start_task(task.id)

    def _on_action_pause(self) -> None:
        task = self._get_selected_task()
        if task:
            self.manager.pause_task(task.id)

    def _on_action_delete(self) -> None:
        task = self._get_selected_task()
        if task:
            self._confirm_delete(task, delete_file=True)

    def _on_action_open_folder(self) -> None:
        task = self._get_selected_task()
        if task:
            open_folder(task.save_dir)
        else:
            open_folder(self.config.default_save_dir)
