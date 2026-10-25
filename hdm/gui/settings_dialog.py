"""Settings Configuration Dialog for HDM.
Refined modern horizontal navigation tabs with responsive pages.
"""

from __future__ import annotations

from typing import Optional

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
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hdm.core.config import Config, ConfigManager
from hdm.gui.style import apply_theme, normalize_theme
from hdm.utils.i18n import normalize_language, set_language, tr


class SettingsDialog(QDialog):
    """Configuration dialog for adjusting HDM parameters with top horizontal navigation."""

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.config = config_manager.config
        self._original_theme = normalize_theme(self.config.theme)
        self._original_lang = normalize_language(self.config.language)

        self.setWindowTitle(tr("settings_dialog_title"))
        self.setMinimumWidth(660)
        self.setMinimumHeight(460)
        self.resize(660, 480)
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
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 6, 4, 6)
        page_layout.setSpacing(12)

        grp_storage = QGroupBox(tr("settings_grp_storage"), page)
        grid_storage = QGridLayout(grp_storage)
        grid_storage.setSpacing(10)

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
        grid_storage.addLayout(dir_row, 0, 1)

        grid_storage.addWidget(QLabel(tr("settings_connections")), 1, 0)
        self.conn_spin = QSpinBox(grp_storage)
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(self.config.default_connections)
        grid_storage.addWidget(self.conn_spin, 1, 1)

        grid_storage.addWidget(QLabel(tr("settings_max_concurrent")), 2, 0)
        self.max_tasks_spin = QSpinBox(grp_storage)
        self.max_tasks_spin.setRange(1, 10)
        self.max_tasks_spin.setValue(self.config.max_concurrent_tasks)
        grid_storage.addWidget(self.max_tasks_spin, 2, 1)

        self.chk_categorize = QCheckBox(tr("settings_chk_categorize"), grp_storage)
        self.chk_categorize.setChecked(self.config.auto_categorize)
        grid_storage.addWidget(self.chk_categorize, 3, 0, 1, 2)

        self.chk_autostart = QCheckBox(tr("settings_chk_autostart"), grp_storage)
        self.chk_autostart.setChecked(self.config.auto_start)
        grid_storage.addWidget(self.chk_autostart, 4, 0, 1, 2)

        self.chk_start_with_windows = QCheckBox(tr("settings_chk_start_with_windows"), grp_storage)
        self.chk_start_with_windows.setChecked(self.config.start_with_windows)
        grid_storage.addWidget(self.chk_start_with_windows, 5, 0, 1, 2)

        page_layout.addWidget(grp_storage)
        page_layout.addStretch()
        return page

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

        set_language(self.config.language)
        self.config_manager.save(self.config)
        self.accept()
