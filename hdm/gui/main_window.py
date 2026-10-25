"""Main Application Window for HDM (H2M Download Manager).
Features sidebar categories, dynamic task counters, live search, modern table view,
toolbar actions, light/dark theme switching, system tray, and smooth real-time
progress updates.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QKeySequence, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QPushButton,
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

from hdm.utils.i18n import get_category_display, get_language, get_status_display, tr

STATUS_FILTER_SPECS = [
    ("all", ""),
    ("status_downloading", "⚡"),
    ("status_completed", "✅"),
    ("status_paused", "⏸"),
    ("status_error", "❌"),
]

CATEGORY_FILTER_SPECS = [
    ("cat_compressed", "📦"),
    ("cat_programs", "💻"),
    ("cat_video", "🎬"),
    ("cat_audio", "🎵"),
    ("cat_docs", "📄"),
    ("cat_images", "🖼"),
    ("cat_others", "📂"),
]

FILTER_KEY_MAP = {
    "all": "sidebar_all",
    "status_downloading": "sidebar_status_downloading",
    "status_completed": "sidebar_status_completed",
    "status_paused": "sidebar_status_paused",
    "status_error": "sidebar_status_error",
    "cat_compressed": "cat_compressed",
    "cat_programs": "cat_programs",
    "cat_video": "cat_video",
    "cat_audio": "cat_audio",
    "cat_docs": "cat_docs",
    "cat_images": "cat_images",
    "cat_others": "cat_others",
}

FILTER_EMOJIS = {code: emoji for code, emoji in STATUS_FILTER_SPECS + CATEGORY_FILTER_SPECS}


def get_filter_title(code: str) -> str:
    key = FILTER_KEY_MAP.get(code)
    return tr(key) if key else code


def sidebar_label(code: str, count: Optional[int] = None) -> str:
    """Build the display text of a sidebar entry, optionally with a live counter."""
    emoji = FILTER_EMOJIS.get(code, "")
    title = get_filter_title(code)
    text = f"  {emoji} {title}" if emoji else f"  {title}"
    return f"{text} ({count})" if count is not None else text


def build_status_colors() -> Dict[TaskStatus, str]:
    """Status text colors matching the currently active theme."""
    p = get_palette()
    return {
        TaskStatus.COMPLETED: p["success"],
        TaskStatus.DOWNLOADING: p["info"],
        TaskStatus.PROCESSING: p["warning"],
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
    download_requested_signal = Signal(dict)


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
        self.bridge.download_requested_signal.connect(self.show_confirm_download_dialog)

        # Connect manager callbacks to bridge
        self.manager.on_task_added = lambda t: self.bridge.task_added_signal.emit(t)
        self.manager.on_task_updated = lambda t: self.bridge.task_updated_signal.emit(t)

        self.current_filter_category: Optional[str] = None
        self.current_filter_status: Optional[TaskStatus] = None
        self.current_filter_code: str = "all"
        self.search_query: str = ""
        self.batch_mode_active: bool = False
        self._table_loading: bool = False

        self._active_confirm_dialog: Optional[AddDownloadDialog] = None
        self._pending_download_requests: List[Dict[str, Any]] = []

        self._force_quit: bool = False
        self._tray_notified: bool = False

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

        self.lbl_speed_summary = QLabel(tr("status_speed", speed="0 KB/s"), self)
        self.lbl_speed_summary.setObjectName("status_speed")

        self.lbl_tasks_summary = QLabel(tr("status_tasks_count", count=0), self)
        self.lbl_tasks_summary.setObjectName("status_tasks")

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
        self.lbl_sub = QLabel(tr("app_subtitle"), brand)
        self.lbl_sub.setObjectName("brand_sub")
        titles.addWidget(lbl_title)
        titles.addWidget(self.lbl_sub)

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

        self.lbl_footer = QLabel(tr("app_version_footer"), panel)
        self.lbl_footer.setObjectName("sidebar_footer")
        self.lbl_footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_footer)

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

        self.page_title = QLabel(get_filter_title(self.current_filter_code), content)
        self.page_title.setObjectName("page_title")
        self.page_subtitle = QLabel(tr("page_files_summary", count=0, total=0), content)
        self.page_subtitle.setObjectName("page_subtitle")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)

        header_row.addLayout(title_box)
        header_row.addStretch()

        self.page_badge = QLabel(tr("page_badge_downloading", count=0), content)
        self.page_badge.setObjectName("page_badge")
        header_row.addWidget(self.page_badge)
        layout.addLayout(header_row)

        # Batch delete action bar (hidden until user clicks 'Xoá nhiều' on toolbar)
        self.batch_bar = QFrame(content)
        self.batch_bar.setObjectName("batch_bar")
        batch_layout = QHBoxLayout(self.batch_bar)
        batch_layout.setContentsMargins(12, 6, 12, 6)
        batch_layout.setSpacing(12)

        self.chk_batch_all = QCheckBox(tr("batch_select_all"), self.batch_bar)
        self.chk_batch_all.toggled.connect(self._on_batch_select_all_toggled)
        batch_layout.addWidget(self.chk_batch_all)

        self.lbl_batch_count = QLabel(tr("batch_selected_count", count=0), self.batch_bar)
        self.lbl_batch_count.setObjectName("batch_count_label")
        batch_layout.addWidget(self.lbl_batch_count)

        batch_layout.addStretch()

        self.btn_batch_confirm = QPushButton(tr("batch_btn_confirm"), self.batch_bar)
        self.btn_batch_confirm.setObjectName("btn_batch_confirm")
        self.btn_batch_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_batch_confirm.clicked.connect(self._on_batch_confirm_delete)
        batch_layout.addWidget(self.btn_batch_confirm)

        self.btn_batch_delete_all = QPushButton(tr("batch_btn_all"), self.batch_bar)
        self.btn_batch_delete_all.setObjectName("btn_batch_all")
        self.btn_batch_delete_all.setCursor(Qt.PointingHandCursor)
        self.btn_batch_delete_all.clicked.connect(self._on_batch_delete_all)
        batch_layout.addWidget(self.btn_batch_delete_all)

        self.btn_batch_close = QPushButton(tr("batch_btn_close"), self.batch_bar)
        self.btn_batch_close.setObjectName("btn_batch_close")
        self.btn_batch_close.setCursor(Qt.PointingHandCursor)
        self.btn_batch_close.clicked.connect(self.exit_batch_delete_mode)
        batch_layout.addWidget(self.btn_batch_close)

        self.batch_bar.hide()
        layout.addWidget(self.batch_bar)

        # Table inside a rounded card
        card = QFrame(content)
        card.setObjectName("table_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(1, 1, 1, 1)
        card_layout.setSpacing(0)

        self.table = QTableWidget(card)
        self.table.setObjectName("download_table")
        self.table.setColumnCount(9)
        self._update_table_headers()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setCascadingSectionResizes(False)
        header.setStretchLastSection(False)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(36)

        for column, width in (
            (0, 42),
            (1, 260),
            (2, 112),
            (3, 100),
            (4, 190),
            (5, 104),
            (6, 108),
            (7, 106),
            (8, 126),
        ):
            self.table.setColumnWidth(column, width)

        self.table.setColumnHidden(0, True)

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
        self.table.itemChanged.connect(self._on_table_item_changed)

        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)

        # Friendly empty state shown when no task matches the current filter
        self.empty_label = QLabel(
            tr("empty_state_text"),
            self.table.viewport(),
        )
        self.empty_label.setObjectName("empty_state")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.empty_label.hide()

        return content

    def _update_table_headers(self) -> None:
        self.table.setHorizontalHeaderLabels([
            "☑",
            tr("table_filename"),
            tr("table_category"),
            tr("table_size"),
            tr("table_progress"),
            tr("table_speed"),
            tr("table_eta"),
            tr("table_status"),
            tr("table_date_added"),
        ])

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
        self._add_sidebar_header(tr("sidebar_header_status"))
        for code, _emoji in STATUS_FILTER_SPECS:
            self._add_sidebar_item(code)

        self._add_sidebar_header(tr("sidebar_header_category"))
        for code, _emoji in CATEGORY_FILTER_SPECS:
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
        self.menu_file = menubar.addMenu(tr("menu_file"))
        self.act_add = QAction(tr("menu_add_url"), self)
        self.act_add.setShortcut(QKeySequence("Ctrl+N"))
        self.act_add.triggered.connect(self.show_add_dialog)
        self.menu_file.addAction(self.act_add)

        self.menu_file.addSeparator()
        self.act_exit = QAction(tr("menu_exit"), self)
        self.act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_exit.triggered.connect(self.exit_app)
        self.menu_file.addAction(self.act_exit)

        # Tasks Menu
        self.menu_tasks = menubar.addMenu(tr("menu_tasks"))
        self.act_resume_all = QAction(tr("menu_resume_all"), self)
        self.act_resume_all.triggered.connect(self.manager.resume_all)
        self.menu_tasks.addAction(self.act_resume_all)

        self.act_pause_all = QAction(tr("menu_pause_all"), self)
        self.act_pause_all.triggered.connect(self.manager.pause_all)
        self.menu_tasks.addAction(self.act_pause_all)

        # Tools Menu
        self.menu_tools = menubar.addMenu(tr("menu_tools"))
        self.act_settings = QAction(tr("menu_settings"), self)
        self.act_settings.triggered.connect(self.show_settings_dialog)
        self.menu_tools.addAction(self.act_settings)

        self.act_toggle_theme = QAction("Chuyển Giao diện Sáng / Tối", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+T"))
        self.act_toggle_theme.setCheckable(False)
        self.act_toggle_theme.triggered.connect(self.toggle_theme)
        self.menu_tools.addAction(self.act_toggle_theme)

        self.act_ext = QAction(tr("menu_install_extension"), self)
        self.act_ext.triggered.connect(self._open_extension_dir)
        self.menu_tools.addAction(self.act_ext)

        # Help Menu
        self.menu_help = menubar.addMenu(tr("menu_help"))
        self.act_about = QAction(tr("menu_about"), self)
        self.act_about.triggered.connect(self._show_about)
        self.menu_help.addAction(self.act_about)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("MainToolbar", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # Primary Add Button with crisp vector icon
        self.btn_add_action = toolbar.addAction(get_icon("add", "#FFFFFF"), tr("toolbar_add_url"))
        self.btn_add_action.setToolTip(tr("toolbar_add_tip"))
        self.btn_add_action.triggered.connect(self.show_add_dialog)
        btn_add_widget = toolbar.widgetForAction(self.btn_add_action)
        if btn_add_widget:
            btn_add_widget.setObjectName("btn_primary_add")

        toolbar.addSeparator()

        text_color = self.palette_colors.get("text", "#F1F5F9")

        self.btn_resume_action = toolbar.addAction(get_icon("resume", text_color), tr("toolbar_resume"))
        self.btn_resume_action.setToolTip(tr("toolbar_resume_tip"))
        self.btn_resume_action.triggered.connect(self._on_action_resume)

        self.btn_pause_action = toolbar.addAction(get_icon("pause", text_color), tr("toolbar_pause"))
        self.btn_pause_action.setToolTip(tr("toolbar_pause_tip"))
        self.btn_pause_action.triggered.connect(self._on_action_pause)

        self.btn_delete_action = toolbar.addAction(get_icon("delete", text_color), tr("toolbar_delete"))
        self.btn_delete_action.setShortcut(QKeySequence.Delete)
        self.btn_delete_action.setToolTip(tr("toolbar_delete_tip"))
        self.btn_delete_action.triggered.connect(self._on_action_delete)

        self.btn_batch_delete_action = toolbar.addAction(get_icon("batch_delete", text_color), tr("toolbar_batch_delete"))
        self.btn_batch_delete_action.setToolTip(tr("toolbar_batch_delete"))
        self.btn_batch_delete_action.triggered.connect(self.toggle_batch_delete_mode)

        toolbar.addSeparator()

        self.btn_folder_action = toolbar.addAction(get_icon("folder", text_color), tr("toolbar_folder"))
        self.btn_folder_action.setToolTip(tr("toolbar_folder_tip"))
        self.btn_folder_action.triggered.connect(self._on_action_open_folder)

        self.btn_settings_action = toolbar.addAction(get_icon("settings", text_color), tr("toolbar_settings"))
        self.btn_settings_action.setToolTip(tr("toolbar_settings_tip"))
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
        self.search_input.setPlaceholderText(tr("toolbar_search_placeholder"))
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
                tr("toolbar_theme_light_tip") if going_light
                else tr("toolbar_theme_dark_tip")
            )

        # Synchronize action icons to match active theme text color
        if hasattr(self, "btn_resume_action"):
            text_color = self.palette_colors.get("text", "#F1F5F9")
            self.btn_add_action.setIcon(get_icon("add", "#FFFFFF"))
            self.btn_resume_action.setIcon(get_icon("resume", text_color))
            self.btn_pause_action.setIcon(get_icon("pause", text_color))
            self.btn_delete_action.setIcon(get_icon("delete", text_color))
            if hasattr(self, "btn_batch_delete_action"):
                self.btn_batch_delete_action.setIcon(get_icon("batch_delete", text_color))
            self.btn_folder_action.setIcon(get_icon("folder", text_color))
            self.btn_settings_action.setIcon(get_icon("settings", text_color))

    def _update_page_header(self) -> None:
        """Keep the page title, subtitle and active-task badge in sync."""
        if not hasattr(self, "page_title"):
            return
        self.page_title.setText(get_filter_title(self.current_filter_code))

        visible = self.table.rowCount() if hasattr(self, "table") else 0
        total = len(self.manager.tasks)
        if self.search_query:
            self.page_subtitle.setText(
                tr("page_search_results", count=visible, query=self.search_query, total=total)
            )
        else:
            self.page_subtitle.setText(tr("page_files_summary", count=visible, total=total))
        self.page_badge.setText(tr("page_badge_downloading", count=self.manager.get_active_count()))

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
            self.tray.setToolTip(tr("tray_tooltip"))

            self.tray_menu = QMenu(self)
            self.act_tray_show = self.tray_menu.addAction(tr("tray_open"))
            self.act_tray_show.triggered.connect(self.show_and_raise)

            self.tray_menu.addSeparator()
            self.act_tray_pause = self.tray_menu.addAction(tr("tray_pause_all"))
            self.act_tray_pause.triggered.connect(self.manager.pause_all)

            self.act_tray_resume = self.tray_menu.addAction(tr("tray_resume_all"))
            self.act_tray_resume.triggered.connect(self.manager.resume_all)

            self.tray_menu.addSeparator()
            self.act_tray_quit = self.tray_menu.addAction(tr("tray_exit"))
            self.act_tray_quit.triggered.connect(self.exit_app)

            self.tray.setContextMenu(self.tray_menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_and_raise()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Minimize to system tray when the user clicks 'X', keeping downloads active."""
        if self._force_quit:
            if hasattr(self, "tray") and self.tray:
                self.tray.hide()
            event.accept()
            return

        if QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            if not self._tray_notified and hasattr(self, "tray") and self.tray:
                self._tray_notified = True
                self.tray.showMessage(
                    tr("tray_balloon_title"),
                    tr("tray_balloon_msg"),
                    QSystemTrayIcon.Information,
                    2500,
                )
        else:
            event.accept()

    def exit_app(self) -> None:
        """Completely exit the application and terminate background processes."""
        self._force_quit = True
        if hasattr(self, "tray") and self.tray:
            self.tray.hide()
        self.close()
        QApplication.instance().quit()

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.raise_()
        self.activateWindow()

    def show_add_dialog(self, initial_url: Any = "") -> None:
        """Open the IDM-style download confirmation dialog.
        Auto-reads clipboard if no URL is explicitly provided.
        """
        url = initial_url if isinstance(initial_url, str) else ""
        if not url:
            clip = QApplication.clipboard().text().strip()
            if clip.startswith("http://") or clip.startswith("https://"):
                url = clip

        self.show_confirm_download_dialog({"url": url, "is_captured": False})

    def show_confirm_download_dialog(self, data: dict) -> None:
        """Display IDM-style download confirmation modal with file probe and actions."""
        url = data.get("url", "")
        filename = data.get("filename", "")
        headers = data.get("headers", {})
        is_captured = data.get("is_captured", True)
        quality = data.get("quality", "")

        # If a dialog is already showing:
        if self._active_confirm_dialog and self._active_confirm_dialog.isVisible():
            # If same URL, raise and don't spawn duplicate
            if getattr(self._active_confirm_dialog, "initial_url", "") == url:
                self._active_confirm_dialog.raise_()
                self._active_confirm_dialog.activateWindow()
                return
            # Otherwise queue the request to avoid nested modal event loops
            self._pending_download_requests.append(data)
            return

        self.show_and_raise()

        dlg = AddDownloadDialog(
            config=self.config,
            initial_url=url,
            initial_filename=filename,
            custom_headers=headers,
            is_captured=is_captured,
            initial_quality=quality,
            parent=self,
        )
        self._active_confirm_dialog = dlg
        try:
            if dlg.exec():
                res = dlg.get_result_data()
                self.manager.add_task(
                    url=res["url"],
                    save_dir=res["save_dir"],
                    filename=res["filename"],
                    headers=res.get("headers"),
                    connections=res["connections"],
                    auto_start=res["auto_start"],
                    quality=res.get("quality", ""),
                    category=res.get("category"),
                )
                self.show_and_raise()
        finally:
            self._active_confirm_dialog = None
            if self._pending_download_requests:
                next_req = self._pending_download_requests.pop(0)
                QTimer.singleShot(50, lambda: self.show_confirm_download_dialog(next_req))

    def show_settings_dialog(self) -> None:
        old_lang = get_language()
        dlg = SettingsDialog(self.config_manager, parent=self)
        if dlg.exec():
            saved_theme = normalize_theme(self.config.theme)
            if saved_theme != self.theme:
                self.set_theme(saved_theme, persist=False)
            if get_language() != old_lang:
                self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Dynamically re-apply localized strings across all windows and controls."""
        self.setWindowTitle(tr("app_title"))
        if hasattr(self, "lbl_sub"):
            self.lbl_sub.setText(tr("app_subtitle"))
        if hasattr(self, "lbl_footer"):
            self.lbl_footer.setText(tr("app_version_footer"))

        # Menus
        if hasattr(self, "menu_file"):
            self.menu_file.setTitle(tr("menu_file"))
            self.act_add.setText(tr("menu_add_url"))
            self.act_exit.setText(tr("menu_exit"))
        if hasattr(self, "menu_tasks"):
            self.menu_tasks.setTitle(tr("menu_tasks"))
            self.act_resume_all.setText(tr("menu_resume_all"))
            self.act_pause_all.setText(tr("menu_pause_all"))
        if hasattr(self, "menu_tools"):
            self.menu_tools.setTitle(tr("menu_tools"))
            self.act_settings.setText(tr("menu_settings"))
            self.act_ext.setText(tr("menu_install_extension"))
        if hasattr(self, "menu_help"):
            self.menu_help.setTitle(tr("menu_help"))
            self.act_about.setText(tr("menu_about"))

        # Toolbar
        if hasattr(self, "btn_add_action"):
            self.btn_add_action.setText(tr("toolbar_add_url"))
            self.btn_add_action.setToolTip(tr("toolbar_add_tip"))
            self.btn_resume_action.setText(tr("toolbar_resume"))
            self.btn_resume_action.setToolTip(tr("toolbar_resume_tip"))
            self.btn_pause_action.setText(tr("toolbar_pause"))
            self.btn_pause_action.setToolTip(tr("toolbar_pause_tip"))
            self.btn_delete_action.setText(tr("toolbar_delete"))
            self.btn_delete_action.setToolTip(tr("toolbar_delete_tip"))
            if hasattr(self, "btn_batch_delete_action"):
                self.btn_batch_delete_action.setText(tr("toolbar_batch_delete"))
                self.btn_batch_delete_action.setToolTip(tr("toolbar_batch_delete"))
            self.btn_folder_action.setText(tr("toolbar_folder"))
            self.btn_folder_action.setToolTip(tr("toolbar_folder_tip"))
            self.btn_settings_action.setText(tr("toolbar_settings"))
            self.btn_settings_action.setToolTip(tr("toolbar_settings_tip"))
            self.search_input.setPlaceholderText(tr("toolbar_search_placeholder"))
            self._sync_theme_button()

        if hasattr(self, "chk_batch_all"):
            self.chk_batch_all.setText(tr("batch_select_all"))
            self.btn_batch_confirm.setText(tr("batch_btn_confirm"))
            self.btn_batch_delete_all.setText(tr("batch_btn_all"))
            self.btn_batch_close.setText(tr("batch_btn_close"))
            self._update_batch_count()

        # Table & Sidebar
        if hasattr(self, "table"):
            self._update_table_headers()
        if hasattr(self, "sidebar"):
            current_code = self.current_filter_code
            self._build_sidebar()
            for i in range(self.sidebar.count()):
                item = self.sidebar.item(i)
                if item and item.data(Qt.UserRole) == current_code:
                    self.sidebar.setCurrentRow(i)
                    break

        if hasattr(self, "empty_label"):
            self.empty_label.setText(tr("empty_state_text"))

        if hasattr(self, "tray") and self.tray:
            self.tray.setToolTip(tr("tray_tooltip"))
            if hasattr(self, "act_tray_show"):
                self.act_tray_show.setText(tr("tray_open"))
                self.act_tray_pause.setText(tr("tray_pause_all"))
                self.act_tray_resume.setText(tr("tray_resume_all"))
                self.act_tray_quit.setText(tr("tray_exit"))

        self._refresh_table_data()
        self._reload_table_full()

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
            tr("about_title"),
            tr("about_text"),
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
        self._table_loading = True
        try:
            tasks = self._get_filtered_tasks()
            self.table.setRowCount(len(tasks))

            colors = self.palette_colors
            bold_font = QFont()
            bold_font.setBold(True)

            for row, task in enumerate(tasks):
                # 0. Checkbox for batch actions
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                chk_item.setCheckState(Qt.Unchecked)
                chk_item.setData(Qt.UserRole, task.id)
                chk_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 0, chk_item)

                # 1. Filename
                item_name = QTableWidgetItem(task.filename)
                item_name.setData(Qt.UserRole, task.id)
                item_name.setToolTip(f"{task.filename}\n{task.url}")
                self.table.setItem(row, 1, item_name)

                # 2. Category
                cat_display = get_category_display(task.category)
                self.table.setItem(row, 2, QTableWidgetItem(cat_display))

                # 3. Size
                size_str = format_bytes(task.total_bytes) if task.total_bytes > 0 else "--"
                item_size = QTableWidgetItem(size_str)
                item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 3, item_size)

                # 4. Progress Bar container
                container = self.table.cellWidget(row, 4)
                if container is None:
                    container = QWidget()
                    layout_p = QHBoxLayout(container)
                    layout_p.setContentsMargins(8, 8, 8, 8)
                    pbar = QProgressBar(container)
                    pbar.setRange(0, 100)
                    pbar.setTextVisible(True)
                    pbar.setFixedHeight(18)
                    layout_p.addWidget(pbar)
                    self.table.setCellWidget(row, 4, container)
                pbar = container.findChild(QProgressBar)
                if pbar is not None:
                    pbar.setValue(int(task.progress_percent))
                    pbar.setFormat(f"{task.progress_percent:.1f}%")

                # 5. Speed
                if task.status == TaskStatus.DOWNLOADING and task.speed > 0:
                    item_speed = QTableWidgetItem(format_speed(task.speed))
                    item_speed.setForeground(QColor(colors["cyan"]))
                    item_speed.setFont(bold_font)
                elif task.status == TaskStatus.PROCESSING:
                    item_speed = QTableWidgetItem("Xử lý...")
                    item_speed.setForeground(QColor(colors["warning"]))
                    item_speed.setFont(bold_font)
                else:
                    item_speed = QTableWidgetItem("--")
                    item_speed.setForeground(QColor(colors["text_faint"]))
                item_speed.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 5, item_speed)

                # 6. ETA
                if task.status == TaskStatus.DOWNLOADING:
                    eta_str = format_eta(task.eta)
                elif task.status == TaskStatus.PROCESSING:
                    eta_str = "Chờ hoàn tất"
                else:
                    eta_str = "--"
                item_eta = QTableWidgetItem(eta_str)
                item_eta.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 6, item_eta)

                # 7. Status with color badge
                item_status = QTableWidgetItem(get_status_display(task.status))
                item_status.setTextAlignment(Qt.AlignCenter)
                item_status.setForeground(QColor(self.status_colors.get(task.status, colors["text"])))
                item_status.setFont(bold_font)
                self.table.setItem(row, 7, item_status)

                # 8. Date
                item_date = QTableWidgetItem(format_date(task.created_at))
                item_date.setTextAlignment(Qt.AlignCenter)
                item_date.setForeground(QColor(colors["muted"]))
                self.table.setItem(row, 8, item_date)
        finally:
            self._table_loading = False

        self._update_sidebar_counts()
        self._sync_empty_state()
        if getattr(self, "batch_mode_active", False):
            self._update_batch_count()

    def _refresh_table_data(self) -> None:
        """Poll and refresh row progress, speeds, and status bar."""
        total_speed = self.manager.get_total_speed()
        active_count = self.manager.get_active_count()
        total_count = len(self.manager.tasks)

        self.lbl_speed_summary.setText(tr("status_speed", speed=format_speed(total_speed)))
        self.lbl_tasks_summary.setText(f"📊 {active_count} {tr('sidebar_status_downloading').lower()} / {total_count}")
        self._update_page_header()

        colors = self.palette_colors
        bold_font = QFont()
        bold_font.setBold(True)

        for row in range(self.table.rowCount()):
            item_name = self.table.item(row, 1) or self.table.item(row, 0)
            if not item_name:
                continue
            task_id = item_name.data(Qt.UserRole)
            task = self.manager.tasks.get(task_id)
            if not task:
                continue

            # Update progress bar
            container = self.table.cellWidget(row, 4)
            if container:
                pbar = container.findChild(QProgressBar)
                if pbar:
                    pbar.setValue(int(task.progress_percent))
                    pbar.setFormat(f"{task.progress_percent:.1f}%")

            # Update speed
            item_speed = self.table.item(row, 5)
            if item_speed:
                if task.status == TaskStatus.DOWNLOADING and task.speed > 0:
                    item_speed.setText(format_speed(task.speed))
                    item_speed.setForeground(QColor(colors["cyan"]))
                    item_speed.setFont(bold_font)
                elif task.status == TaskStatus.PROCESSING:
                    item_speed.setText("Xử lý...")
                    item_speed.setForeground(QColor(colors["warning"]))
                    item_speed.setFont(bold_font)
                else:
                    item_speed.setText("--")
                    item_speed.setForeground(QColor(colors["text_faint"]))

            # Update ETA
            item_eta = self.table.item(row, 6)
            if item_eta:
                if task.status == TaskStatus.DOWNLOADING:
                    eta_str = format_eta(task.eta)
                elif task.status == TaskStatus.PROCESSING:
                    eta_str = "Chờ hoàn tất"
                else:
                    eta_str = "--"
                item_eta.setText(eta_str)

            # Update status
            item_status = self.table.item(row, 7)
            if item_status:
                item_status.setText(get_status_display(task.status))
                item_status.setForeground(QColor(self.status_colors.get(task.status, colors["text"])))
                item_status.setFont(bold_font)

    def _on_task_added_signal(self, task: DownloadTask) -> None:
        self._reload_table_full()

    def _on_task_updated_signal(self, task: DownloadTask) -> None:
        # Check if completed to show balloon notification
        if task.status == TaskStatus.COMPLETED and hasattr(self, "tray") and self.tray.isVisible():
            self.tray.showMessage(
                "HDM",
                f"{task.filename} ({tr('sidebar_status_completed').lower()})",
                QSystemTrayIcon.Information,
                3000
            )

    def _get_selected_task(self) -> Optional[DownloadTask]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1) or self.table.item(row, 0)
        if not item:
            return None
        task_id = item.data(Qt.UserRole)
        return self.manager.tasks.get(task_id)

    def _open_task_file(self, task: DownloadTask) -> None:
        """Open downloaded file; if missing on disk, prompt user to delete from list."""
        if not task.full_path or not os.path.exists(task.full_path):
            res = QMessageBox.question(
                self,
                tr("file_not_found_title"),
                tr("file_not_found_msg", filename=task.filename),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if res == QMessageBox.Yes:
                self.manager.delete_task(task.id, delete_file=False)
                self._reload_table_full()
            return

        try:
            launch_file(task.full_path)
        except Exception as e:
            QMessageBox.warning(self, "Lỗi mở tệp", f"Không thể mở tệp: {e}")

    def _on_table_double_clicked(self) -> None:
        task = self._get_selected_task()
        if not task:
            return
        if task.status == TaskStatus.COMPLETED:
            self._open_task_file(task)
        else:
            dlg = DownloadDetailDialog(task, parent=self)
            dlg.exec()

    def _show_context_menu(self, pos) -> None:
        task = self._get_selected_task()
        if not task:
            return

        menu = QMenu(self)

        act_detail = menu.addAction(f"🔍 {tr('ctx_view_details')}")
        act_detail.triggered.connect(lambda: DownloadDetailDialog(task, parent=self).exec())

        menu.addSeparator()

        if task.status in (TaskStatus.PAUSED, TaskStatus.ERROR, TaskStatus.CANCELLED):
            act_resume = menu.addAction(f"▶ {tr('ctx_resume')}")
            act_resume.triggered.connect(lambda: self.manager.start_task(task.id))
        elif task.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING, TaskStatus.QUEUED):
            act_pause = menu.addAction(f"❚❚ {tr('ctx_pause')}")
            act_pause.triggered.connect(lambda: self.manager.pause_task(task.id))

        if task.status == TaskStatus.COMPLETED:
            act_open_file = menu.addAction(tr("ctx_open_file"))
            act_open_file.triggered.connect(lambda: self._open_task_file(task))

        act_open_dir = menu.addAction(f"📁 {tr('ctx_open_folder')}")
        act_open_dir.triggered.connect(lambda: open_file_in_explorer(task.full_path))

        act_copy_url = menu.addAction(f"📋 {tr('ctx_copy_link')}")
        act_copy_url.triggered.connect(lambda: QApplication.clipboard().setText(task.url))

        menu.addSeparator()

        act_del_file = menu.addAction(f"🗑 {tr('ctx_delete')}")
        act_del_file.triggered.connect(lambda: self._confirm_delete(task, delete_file=True))

        menu.exec(QCursor.pos())

    def _confirm_delete(self, task: DownloadTask, delete_file: bool = True) -> None:
        msg = tr("confirm_delete_msg", filename=task.filename)
        title = tr("confirm_delete_title")

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

    # ------------------------------------------------------------------
    # Batch delete mode
    # ------------------------------------------------------------------
    def toggle_batch_delete_mode(self) -> None:
        """Toggle batch delete checkbox column and top action bar."""
        if self.batch_mode_active:
            self.exit_batch_delete_mode()
        else:
            self.enter_batch_delete_mode()

    def enter_batch_delete_mode(self) -> None:
        self.batch_mode_active = True
        self.table.setColumnHidden(0, False)
        self.batch_bar.show()
        self._uncheck_all_batch()
        self._update_batch_count()

    def exit_batch_delete_mode(self) -> None:
        self.batch_mode_active = False
        self.table.setColumnHidden(0, True)
        self.batch_bar.hide()
        self._uncheck_all_batch()

    def _uncheck_all_batch(self) -> None:
        self._table_loading = True
        try:
            self.chk_batch_all.setChecked(False)
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item:
                    item.setCheckState(Qt.Unchecked)
        finally:
            self._table_loading = False

    def _on_batch_select_all_toggled(self, checked: bool) -> None:
        if self._table_loading:
            return
        self._table_loading = True
        try:
            target_state = Qt.Checked if checked else Qt.Unchecked
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item:
                    item.setCheckState(target_state)
        finally:
            self._table_loading = False
        self._update_batch_count()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._table_loading or item.column() != 0:
            return
        self._update_batch_count()

    def _get_checked_task_ids(self) -> List[str]:
        task_ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                t_id = item.data(Qt.UserRole)
                if t_id:
                    task_ids.append(t_id)
        return task_ids

    def _update_batch_count(self) -> None:
        if not hasattr(self, "lbl_batch_count"):
            return
        count = len(self._get_checked_task_ids())
        self.lbl_batch_count.setText(tr("batch_selected_count", count=count))

    def _on_batch_confirm_delete(self) -> None:
        task_ids = self._get_checked_task_ids()
        if not task_ids:
            QMessageBox.information(
                self,
                tr("batch_no_selection_title"),
                tr("batch_no_selection_msg"),
            )
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("batch_confirm_title"))
        box.setText(tr("batch_confirm_msg", count=len(task_ids)))
        chk_del_files = QCheckBox(tr("batch_delete_files_chk"), box)
        chk_del_files.setChecked(True)
        box.setCheckBox(chk_del_files)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)

        if box.exec() == QMessageBox.Yes:
            delete_disk_files = chk_del_files.isChecked()
            for tid in task_ids:
                self.manager.delete_task(tid, delete_file=delete_disk_files)
            self._reload_table_full()
            self._update_batch_count()

    def _on_batch_delete_all(self) -> None:
        tasks = self._get_filtered_tasks()
        if not tasks:
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("batch_all_title"))
        box.setText(tr("batch_all_msg", count=len(tasks)))
        chk_del_files = QCheckBox(tr("batch_delete_files_chk"), box)
        chk_del_files.setChecked(True)
        box.setCheckBox(chk_del_files)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)

        if box.exec() == QMessageBox.Yes:
            delete_disk_files = chk_del_files.isChecked()
            for t in tasks:
                self.manager.delete_task(t.id, delete_file=delete_disk_files)
            self._reload_table_full()
            self._update_batch_count()
