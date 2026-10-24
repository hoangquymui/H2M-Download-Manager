"""Settings Configuration Dialog for HDM.
Refined modern grouped layout with card sections and language switcher.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QWidget,
)

from hdm.core.config import Config, ConfigManager
from hdm.gui.style import apply_theme, normalize_theme
from hdm.utils.i18n import normalize_language, set_language, tr


class SettingsDialog(QDialog):
    """Configuration dialog for adjusting HDM parameters."""

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.config = config_manager.config
        self._original_theme = normalize_theme(self.config.theme)
        self._original_lang = normalize_language(self.config.language)

        self.setWindowTitle(tr("settings_dialog_title"))
        self.setMinimumWidth(560)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. Download & Storage Group
        grp_storage = QGroupBox(tr("settings_grp_storage"), self)
        grid_storage = QGridLayout(grp_storage)
        grid_storage.setSpacing(10)

        grid_storage.addWidget(QLabel(tr("settings_default_dir")), 0, 0)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_input = QLineEdit(self)
        self.dir_input.setText(self.config.default_save_dir)
        dir_row.addWidget(self.dir_input)

        btn_browse = QPushButton(tr("settings_btn_browse"), self)
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setFixedWidth(75)
        btn_browse.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(btn_browse)
        grid_storage.addLayout(dir_row, 0, 1)

        grid_storage.addWidget(QLabel(tr("settings_connections")), 1, 0)
        self.conn_spin = QSpinBox(self)
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(self.config.default_connections)
        grid_storage.addWidget(self.conn_spin, 1, 1)

        grid_storage.addWidget(QLabel(tr("settings_max_concurrent")), 2, 0)
        self.max_tasks_spin = QSpinBox(self)
        self.max_tasks_spin.setRange(1, 10)
        self.max_tasks_spin.setValue(self.config.max_concurrent_tasks)
        grid_storage.addWidget(self.max_tasks_spin, 2, 1)

        self.chk_categorize = QCheckBox(tr("settings_chk_categorize"), self)
        self.chk_categorize.setChecked(self.config.auto_categorize)
        grid_storage.addWidget(self.chk_categorize, 3, 0, 1, 2)

        self.chk_autostart = QCheckBox(tr("settings_chk_autostart"), self)
        self.chk_autostart.setChecked(self.config.auto_start)
        grid_storage.addWidget(self.chk_autostart, 4, 0, 1, 2)

        self.chk_start_with_windows = QCheckBox(tr("settings_chk_start_with_windows"), self)
        self.chk_start_with_windows.setChecked(self.config.start_with_windows)
        grid_storage.addWidget(self.chk_start_with_windows, 5, 0, 1, 2)

        layout.addWidget(grp_storage)

        # 2. Browser Integration Group
        grp_browser = QGroupBox(tr("settings_grp_browser"), self)
        grid_browser = QGridLayout(grp_browser)
        grid_browser.setSpacing(10)

        grid_browser.addWidget(QLabel(tr("settings_port")), 0, 0)
        self.port_spin = QSpinBox(self)
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.config.server_port)
        grid_browser.addWidget(self.port_spin, 0, 1)

        self.chk_server = QCheckBox(tr("settings_chk_server"), self)
        self.chk_server.setChecked(self.config.server_enabled)
        grid_browser.addWidget(self.chk_server, 1, 0, 1, 2)

        layout.addWidget(grp_browser)

        # 3. Appearance & Language Group
        grp_appearance = QGroupBox(tr("settings_grp_appearance"), self)
        grid_appearance = QGridLayout(grp_appearance)
        grid_appearance.setSpacing(10)

        # Language dropdown
        grid_appearance.addWidget(QLabel(tr("settings_language")), 0, 0)
        self.lang_combo = QComboBox(self)
        self.lang_combo.addItem("Tiếng Việt (Vietnamese)", "vi")
        self.lang_combo.addItem("English", "en")
        current_lang = normalize_language(self.config.language)
        lang_idx = self.lang_combo.findData(current_lang)
        self.lang_combo.setCurrentIndex(lang_idx if lang_idx >= 0 else 0)
        grid_appearance.addWidget(self.lang_combo, 0, 1)

        # Theme dropdown
        grid_appearance.addWidget(QLabel(tr("settings_theme")), 1, 0)
        self.theme_combo = QComboBox(self)
        self.theme_combo.addItem(tr("settings_theme_dark"), "dark")
        self.theme_combo.addItem(tr("settings_theme_light"), "light")
        index = self.theme_combo.findData(self._original_theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_preview)
        grid_appearance.addWidget(self.theme_combo, 1, 1)

        lbl_hint = QLabel(tr("settings_theme_hint"), self)
        lbl_hint.setObjectName("settings_hint")
        lbl_hint.setWordWrap(True)
        grid_appearance.addWidget(lbl_hint, 2, 0, 1, 2)

        layout.addWidget(grp_appearance)

        layout.addSpacing(6)

        # 4. Action buttons
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
        self.config.auto_start = self.chk_autostart.isChecked()
        self.config.start_with_windows = self.chk_start_with_windows.isChecked()
        self.config.theme = normalize_theme(self.theme_combo.currentData())
        self.config.language = normalize_language(self.lang_combo.currentData())

        set_language(self.config.language)
        self.config_manager.save(self.config)
        self.accept()
