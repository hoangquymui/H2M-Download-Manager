"""Browser extension install dialog: pick a browser and follow the short guide."""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QFileInfo, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hdm.utils.browsers import Browser, detect_browsers, launch_browser, stage_extension
from hdm.utils.i18n import tr
from hdm.utils.system import open_folder


class ExtensionInstallDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, onboarding: bool = False) -> None:
        super().__init__(parent)
        self.browsers: List[Browser] = detect_browsers()
        self.extension_path = ""
        self._note_key = "ext_note"
        self.onboarding = onboarding

        self.setWindowTitle(tr("ext_dialog_title"))
        self.setModal(True)
        self.resize(780, 480)

        self._init_ui()
        self._populate_browsers()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(tr("ext_dialog_title"), self)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        subtitle_key = "ext_welcome_subtitle" if self.onboarding else "ext_dialog_subtitle"
        subtitle = QLabel(tr(subtitle_key), self)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("opacity: 0.75;")
        layout.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(QLabel(tr("ext_browser_label"), self))
        self.browser_list = QListWidget(self)
        self.browser_list.setObjectName("ext_list")
        self.browser_list.setIconSize(QSize(20, 20))
        self.browser_list.setMinimumWidth(240)
        self.browser_list.currentRowChanged.connect(self._on_browser_changed)
        left.addWidget(self.browser_list, 1)
        body.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        guide_title = QLabel(tr("ext_guide_title"), self)
        guide_title.setObjectName("ext_guide_title")
        right.addWidget(guide_title)

        self.guide_label = QLabel("", self)
        self.guide_label.setObjectName("ext_guide")
        self.guide_label.setWordWrap(True)
        self.guide_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.guide_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.guide_label)

        right.addSpacing(4)
        right.addWidget(QLabel(tr("ext_path_label"), self))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_edit = QLineEdit(self)
        self.path_edit.setObjectName("ext_path")
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit, 1)
        self.btn_copy = QPushButton(tr("ext_copy"), self)
        self.btn_copy.setObjectName("btn_secondary")
        self.btn_copy.clicked.connect(self._copy_path)
        path_row.addWidget(self.btn_copy)
        right.addLayout(path_row)
        right.addStretch(1)
        body.addLayout(right, 4)

        layout.addLayout(body, 1)

        self.hint_label = QLabel("", self)
        self.hint_label.setWordWrap(True)
        self.hint_label.setObjectName("ext_hint")
        layout.addWidget(self.hint_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        self.dont_show_cb: Optional[QCheckBox] = None
        self.btn_launch: Optional[QPushButton] = None
        if self.onboarding:
            self.dont_show_cb = QCheckBox(tr("ext_dont_show"), self)
            buttons.addWidget(self.dont_show_cb)
            buttons.addStretch()
            self.btn_ok = QPushButton(tr("ext_ok"), self)
            self.btn_ok.setDefault(True)
            self.btn_ok.clicked.connect(self.accept)
            buttons.addWidget(self.btn_ok)
        else:
            self.btn_folder = QPushButton(tr("ext_open_folder"), self)
            self.btn_folder.setObjectName("btn_secondary")
            self.btn_folder.clicked.connect(self._open_folder)
            buttons.addWidget(self.btn_folder)

            buttons.addStretch()

            self.btn_close = QPushButton(tr("ext_close"), self)
            self.btn_close.setObjectName("btn_secondary")
            self.btn_close.clicked.connect(self.reject)
            buttons.addWidget(self.btn_close)

            self.btn_launch = QPushButton(tr("ext_launch_browser"), self)
            self.btn_launch.setDefault(True)
            self.btn_launch.clicked.connect(self._launch_browser)
            buttons.addWidget(self.btn_launch)

        layout.addLayout(buttons)

    def _populate_browsers(self) -> None:
        provider = QFileIconProvider()
        self.browser_list.clear()
        for browser in self.browsers:
            item = QListWidgetItem(browser.name)
            icon = provider.icon(QFileInfo(browser.exe_path))
            if not icon.isNull():
                item.setIcon(icon)
            item.setData(Qt.UserRole, browser.key)
            self.browser_list.addItem(item)
        if not self.browsers:
            self.hint_label.setText(tr("ext_no_browser"))
            self.btn_copy.setEnabled(False)
            if self.btn_launch:
                self.btn_launch.setEnabled(False)
            if not self.onboarding:
                self.btn_folder.setEnabled(False)
            return
        self.browser_list.setCurrentRow(0)

    @property
    def dont_show_again(self) -> bool:
        return bool(self.dont_show_cb and self.dont_show_cb.isChecked())

    def _current_browser(self) -> Optional[Browser]:
        row = self.browser_list.currentRow()
        if row < 0 or row >= len(self.browsers):
            return None
        return self.browsers[row]

    def _on_browser_changed(self, _row: int) -> None:
        browser = self._current_browser()
        if not browser:
            return
        firefox = browser.kind == "firefox"
        try:
            self.extension_path = stage_extension("firefox" if firefox else "chromium")
        except OSError:
            self.extension_path = ""

        folder = self.extension_path
        guide_key = "ext_guide_firefox" if firefox else "ext_guide_chromium"
        self.guide_label.setText(tr(guide_key).format(page=browser.management_page))
        self.path_edit.setText(folder)
        self.path_edit.setCursorPosition(0)
        self.path_edit.setToolTip(folder)
        self._note_key = "ext_note_firefox" if firefox else "ext_note"
        self.hint_label.setText(tr(self._note_key))
        has_path = bool(folder and os.path.isdir(folder))
        self.btn_copy.setEnabled(has_path)
        if self.btn_launch:
            self.btn_launch.setText(tr("ext_launch").format(browser=browser.name))
            self.btn_launch.setEnabled(True)
            self.btn_folder.setEnabled(has_path)

    def _copy_path(self) -> None:
        if not self.extension_path:
            return
        QApplication.clipboard().setText(self.extension_path)
        self.hint_label.setText(tr("ext_copied"))
        QTimer.singleShot(1800, lambda: self.hint_label.setText(tr(self._note_key)))

    def _open_folder(self) -> None:
        if self.extension_path:
            open_folder(self.extension_path)

    def _launch_browser(self) -> None:
        browser = self._current_browser()
        if not browser:
            return
        try:
            launch_browser(browser)
        except OSError as exc:
            QMessageBox.warning(
                self,
                tr("ext_dialog_title"),
                tr("ext_launch_failed").format(browser=browser.name, error=exc),
            )
            return
        QApplication.clipboard().setText(browser.management_page)
        self.hint_label.setText(tr("ext_launch_copied").format(browser=browser.name))
        QTimer.singleShot(4000, lambda: self.hint_label.setText(tr(self._note_key)))
