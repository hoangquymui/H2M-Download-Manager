"""Settings Configuration Dialog for HDM.
Refined modern horizontal navigation tabs with responsive pages.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hdm.core.config import Config, ConfigManager
from hdm.gui.style import apply_theme, normalize_theme
from hdm.utils.category import CATEGORY_CONFIG_SPECS, DEFAULT_CATEGORY_EXTENSIONS
from hdm.utils.i18n import normalize_language, set_language, tr


class SettingsDialog(QDialog):
    """Configuration dialog for adjusting HDM parameters with top horizontal navigation."""

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.config = config_manager.config
        self._original_theme = normalize_theme(self.config.theme)
        self._original_lang = normalize_language(self.config.language)
        self.category_inputs: Dict[str, QLineEdit] = {}
        self.folder_inputs: Dict[str, QLineEdit] = {}

        self.setWindowTitle(tr("settings_dialog_title"))
        self.setMinimumWidth(720)
        self.setMinimumHeight(600)
        self.resize(800, 840)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        # 1. Top Horizontal Navigation Bar
        nav_frame = QFrame(self)
        nav_frame.setObjectName("settings_nav_bar")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(6)

        self.nav_btn_group = QButtonGroup(self)
        tab_specs = [
            (0, tr("settings_tab_storage")),
            (1, tr("settings_tab_browser")),
            (2, tr("settings_tab_appearance")),
        ]
        self.nav_buttons = []
        for idx, title in tab_specs:
            btn = QPushButton(title, nav_frame)
            btn.setObjectName(f"nav_tab_{idx}")
            btn.setProperty("class", "nav_tab_btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if idx == 0:
                btn.setChecked(True)
            self.nav_btn_group.addButton(btn, idx)
            nav_layout.addWidget(btn, 1)
            self.nav_buttons.append(btn)

        layout.addWidget(nav_frame)

        # 2. Stacked Pages
        self.stacked_pages = QStackedWidget(self)
        self.stacked_pages.setObjectName("settings_stack")
        self.stacked_pages.addWidget(self._build_storage_page())
        self.stacked_pages.addWidget(self._build_browser_page())
        self.stacked_pages.addWidget(self._build_appearance_page())
        self.nav_btn_group.idClicked.connect(self.stacked_pages.setCurrentIndex)
        layout.addWidget(self.stacked_pages, 1)

        layout.addSpacing(4)

        # 3. Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton(tr("settings_btn_cancel"), self)
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton(tr("settings_btn_save"), self)
        btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _build_storage_page(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setObjectName("storage_scroll_container")
        container.setStyleSheet("#storage_scroll_container { background: transparent; }")
        page_layout = QVBoxLayout(container)
        page_layout.setContentsMargins(2, 2, 6, 2)
        page_layout.setSpacing(10)

        # 1. Main Storage GroupBox
        grp_storage = QGroupBox(tr("settings_grp_storage"), container)
        grid_storage = QGridLayout(grp_storage)
        grid_storage.setSpacing(8)

        grid_storage.addWidget(QLabel(tr("settings_default_dir")), 0, 0)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_input = QLineEdit(grp_storage)
        self.dir_input.setText(self.config.default_save_dir)
        dir_row.addWidget(self.dir_input)

        btn_browse = QPushButton(tr("settings_btn_browse"), grp_storage)
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setFixedWidth(75)
        btn_browse.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(btn_browse)
        grid_storage.addLayout(dir_row, 0, 1, 1, 3)

        grid_storage.addWidget(QLabel(tr("settings_connections")), 1, 0)
        self.conn_spin = QSpinBox(grp_storage)
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(self.config.default_connections)
        grid_storage.addWidget(self.conn_spin, 1, 1)

        grid_storage.addWidget(QLabel(tr("settings_max_concurrent")), 1, 2)
        self.max_tasks_spin = QSpinBox(grp_storage)
        self.max_tasks_spin.setRange(1, 10)
        self.max_tasks_spin.setValue(self.config.max_concurrent_tasks)
        grid_storage.addWidget(self.max_tasks_spin, 1, 3)

        self.chk_categorize = QCheckBox(tr("settings_chk_categorize"), grp_storage)
        self.chk_categorize.setChecked(self.config.auto_categorize)
        grid_storage.addWidget(self.chk_categorize, 2, 0, 1, 4)

        self.chk_autostart = QCheckBox(tr("settings_chk_autostart"), grp_storage)
        self.chk_autostart.setChecked(self.config.auto_start)
        grid_storage.addWidget(self.chk_autostart, 3, 0, 1, 4)

        self.chk_start_with_windows = QCheckBox(tr("settings_chk_start_with_windows"), grp_storage)
        self.chk_start_with_windows.setChecked(self.config.start_with_windows)
        grid_storage.addWidget(self.chk_start_with_windows, 4, 0, 1, 4)

        page_layout.addWidget(grp_storage)

        # 2. Category & File Extensions GroupBox
        grp_categories = QGroupBox(tr("settings_grp_categories"), container)
        cat_layout = QVBoxLayout(grp_categories)
        cat_layout.setSpacing(6)
        cat_layout.setContentsMargins(12, 10, 12, 10)

        lbl_cat_hint = QLabel(tr("settings_categories_hint"), grp_categories)
        lbl_cat_hint.setWordWrap(True)
        lbl_cat_hint.setStyleSheet("color: #64748b; font-size: 11px; margin-bottom: 2px;")
        cat_layout.addWidget(lbl_cat_hint)

        grid_cats = QGridLayout()
        grid_cats.setSpacing(6)
        grid_cats.setColumnStretch(0, 0)
        grid_cats.setColumnStretch(1, 0)
        grid_cats.setColumnStretch(2, 1)

        # Table Header Row
        hdr_type = QLabel(tr("settings_cat_col_type"), grp_categories)
        hdr_type.setStyleSheet("font-weight: 700; font-size: 12px; min-width: 95px; color: #94a3b8;")
        grid_cats.addWidget(hdr_type, 0, 0)

        hdr_folder = QLabel(tr("settings_cat_col_folder"), grp_categories)
        hdr_folder.setStyleSheet("font-weight: 700; font-size: 12px; min-width: 125px; color: #94a3b8;")
        grid_cats.addWidget(hdr_folder, 0, 1)

        hdr_ext = QLabel(tr("settings_cat_col_ext"), grp_categories)
        hdr_ext.setStyleSheet("font-weight: 700; font-size: 12px; color: #94a3b8;")
        grid_cats.addWidget(hdr_ext, 0, 2)

        self.category_inputs.clear()
        self.folder_inputs.clear()
        is_vi = normalize_language(self.config.language) == "vi"

        for row_idx, spec in enumerate(CATEGORY_CONFIG_SPECS, start=1):
            key = str(spec["key"])
            cat_name = str(spec["name_vi"] if is_vi else spec["name_en"])
            default_folder = str(spec["default_folder"])
            default_ext = str(spec["default"])

            # 1. Col: Loại
            lbl_type = QLabel(cat_name, grp_categories)
            lbl_type.setStyleSheet("font-weight: 600; font-size: 12px; min-width: 95px;")
            grid_cats.addWidget(lbl_type, row_idx, 0)

            # 2. Col: Tên thư mục (editable QLineEdit)
            edit_folder = QLineEdit(grp_categories)
            edit_folder.setMinimumWidth(110)
            edit_folder.setMaximumWidth(150)
            current_folder = (self.config.category_folders or {}).get(key, "")
            if not current_folder and key == "Music":
                current_folder = (self.config.category_folders or {}).get("Audio", "")
            if not current_folder and key == "Pictures":
                current_folder = (self.config.category_folders or {}).get("Images", "")
            if not current_folder and key == "Other":
                current_folder = (self.config.category_folders or {}).get("Others", "")
            if not current_folder:
                current_folder = default_folder
            edit_folder.setText(current_folder)
            edit_folder.setPlaceholderText(default_folder)
            grid_cats.addWidget(edit_folder, row_idx, 1)
            self.folder_inputs[key] = edit_folder

            # 3. Col: Các đuôi tệp (editable QLineEdit)
            edit_ext = QLineEdit(grp_categories)
            current_ext = (self.config.category_extensions or {}).get(key)
            if current_ext is None and key == "Music":
                current_ext = (self.config.category_extensions or {}).get("Audio")
            if current_ext is None and key == "Pictures":
                current_ext = (self.config.category_extensions or {}).get("Images")
            if current_ext is None and key == "Other":
                current_ext = (self.config.category_extensions or {}).get("Others")
            if current_ext is None:
                current_ext = default_ext
            edit_ext.setText(current_ext)
            edit_ext.setPlaceholderText(default_ext)
            grid_cats.addWidget(edit_ext, row_idx, 2)
            self.category_inputs[key] = edit_ext

        cat_layout.addLayout(grid_cats)

        # Reset button row
        reset_row = QHBoxLayout()
        reset_row.addStretch()
        btn_reset = QPushButton(tr("settings_btn_reset_categories"), grp_categories)
        btn_reset.setObjectName("btn_secondary")
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.clicked.connect(self._on_reset_categories_clicked)
        reset_row.addWidget(btn_reset)
        cat_layout.addLayout(reset_row)

        page_layout.addWidget(grp_categories)
        page_layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _build_browser_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 6, 4, 6)
        page_layout.setSpacing(12)

        grp_browser = QGroupBox(tr("settings_grp_browser"), page)
        grid_browser = QGridLayout(grp_browser)
        grid_browser.setSpacing(10)

        grid_browser.addWidget(QLabel(tr("settings_port")), 0, 0)
        self.port_spin = QSpinBox(grp_browser)
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.config.server_port)
        grid_browser.addWidget(self.port_spin, 0, 1)

        self.chk_server = QCheckBox(tr("settings_chk_server"), grp_browser)
        self.chk_server.setChecked(self.config.server_enabled)
        grid_browser.addWidget(self.chk_server, 1, 0, 1, 2)

        self.chk_confirm_download = QCheckBox(tr("settings_chk_confirm_download"), grp_browser)
        self.chk_confirm_download.setChecked(getattr(self.config, "show_download_dialog", True))
        grid_browser.addWidget(self.chk_confirm_download, 2, 0, 1, 2)

        page_layout.addWidget(grp_browser)

        # Informative box for browser extension setup
        info_box = QFrame(page)
        info_box.setObjectName("browser_info_box")
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_title = QLabel("💡 Hướng dẫn tích hợp tiện ích trình duyệt:", info_box)
        info_title.setStyleSheet("font-weight: 700;")
        info_desc = QLabel(
            "Tiện ích mở rộng trên Chrome, Edge, Cốc Cốc, Brave sẽ tự động gửi liên kết tải về qua cổng nội bộ "
            f"HTTP (mặc định: {self.config.server_port}). Nếu đổi cổng, vui lòng mở tiện ích trên trình duyệt "
            "để cập nhật lại cổng kết nối tương ứng.",
            info_box,
        )
        info_desc.setWordWrap(True)
        info_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        info_layout.addWidget(info_title)
        info_layout.addWidget(info_desc)
        page_layout.addWidget(info_box)

        page_layout.addStretch()
        return page

    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 6, 4, 6)
        page_layout.setSpacing(12)

        grp_appearance = QGroupBox(tr("settings_grp_appearance"), page)
        grid_appearance = QGridLayout(grp_appearance)
        grid_appearance.setSpacing(10)

        # Language dropdown
        grid_appearance.addWidget(QLabel(tr("settings_language")), 0, 0)
        self.lang_combo = QComboBox(grp_appearance)
        self.lang_combo.addItem("Tiếng Việt (Vietnamese)", "vi")
        self.lang_combo.addItem("English", "en")
        current_lang = normalize_language(self.config.language)
        lang_idx = self.lang_combo.findData(current_lang)
        self.lang_combo.setCurrentIndex(lang_idx if lang_idx >= 0 else 0)
        grid_appearance.addWidget(self.lang_combo, 0, 1)

        # Theme dropdown
        grid_appearance.addWidget(QLabel(tr("settings_theme")), 1, 0)
        self.theme_combo = QComboBox(grp_appearance)
        self.theme_combo.addItem(tr("settings_theme_dark"), "dark")
        self.theme_combo.addItem(tr("settings_theme_light"), "light")
        index = self.theme_combo.findData(self._original_theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_preview)
        grid_appearance.addWidget(self.theme_combo, 1, 1)

        lbl_hint = QLabel(tr("settings_theme_hint"), grp_appearance)
        lbl_hint.setObjectName("settings_hint")
        lbl_hint.setWordWrap(True)
        grid_appearance.addWidget(lbl_hint, 2, 0, 1, 2)

        page_layout.addWidget(grp_appearance)
        page_layout.addStretch()
        return page

    def _on_browse_clicked(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, tr("settings_browse_dialog_title"), self.dir_input.text())
        if chosen:
            self.dir_input.setText(chosen)

    def _on_theme_preview(self, _index: int = 0) -> None:
        """Live-preview the selected theme before the settings are saved."""
        apply_theme(QApplication.instance(), self.theme_combo.currentData())

    def reject(self) -> None:
        """Restore the previous theme and language when the dialog is dismissed."""
        apply_theme(QApplication.instance(), self._original_theme)
        set_language(self._original_lang)
        super().reject()

    def _on_reset_categories_clicked(self) -> None:
        """Reset all category folder names and extensions to their defaults."""
        for spec in CATEGORY_CONFIG_SPECS:
            key = str(spec["key"])
            if key in self.category_inputs:
                self.category_inputs[key].setText(str(spec["default"]))
            if key in self.folder_inputs:
                self.folder_inputs[key].setText(str(spec["default_folder"]))

    def _on_save_clicked(self) -> None:
        self.config.default_save_dir = self.dir_input.text().strip()
        self.config.default_connections = self.conn_spin.value()
        self.config.max_concurrent_tasks = self.max_tasks_spin.value()
        self.config.server_port = self.port_spin.value()
        self.config.auto_categorize = self.chk_categorize.isChecked()
        self.config.server_enabled = self.chk_server.isChecked()
        self.config.show_download_dialog = self.chk_confirm_download.isChecked()
        self.config.auto_start = self.chk_autostart.isChecked()
        self.config.start_with_windows = self.chk_start_with_windows.isChecked()
        self.config.theme = normalize_theme(self.theme_combo.currentData())
        self.config.language = normalize_language(self.lang_combo.currentData())

        # Save customized category extensions
        custom_cats: Dict[str, str] = {}
        for key, input_field in self.category_inputs.items():
            val = input_field.text().strip()
            custom_cats[key] = val
        self.config.category_extensions = custom_cats

        # Save customized category folders
        custom_folders: Dict[str, str] = {}
        for key, input_field in self.folder_inputs.items():
            folder_val = input_field.text().strip()
            if folder_val:
                custom_folders[key] = folder_val
        self.config.category_folders = custom_folders

        from hdm.utils.category import set_custom_category_extensions, set_custom_category_folders
        set_custom_category_extensions(self.config.category_extensions)
        set_custom_category_folders(self.config.category_folders)

        set_language(self.config.language)
        self.config_manager.save(self.config)
        self.accept()
