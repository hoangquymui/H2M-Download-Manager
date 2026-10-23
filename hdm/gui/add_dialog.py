"""Add Download Dialog for HDM.
Allows entering URLs, selecting target paths, custom connections, and auto-probing file info.
Modern card-based layout with real-time feedback.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QFrame,
    QWidget,
)

from hdm.core.config import Config
from hdm.core.sparse_file import check_free_space
from hdm.gui.style import get_palette
from hdm.utils.category import FileCategory, get_category_for_filename
from hdm.utils.formatters import extract_filename_from_url, format_bytes


class ProbeWorker(QThread):
    """Background thread to query URL metadata without freezing the dialog."""
    finished_signal = Signal(str, int, bool)  # filename, total_bytes, supports_range
    error_signal = Signal(str)

    def __init__(self, url: str, user_agent: str) -> None:
        super().__init__()
        self.url = url
        self.user_agent = user_agent

    def run(self) -> None:
        try:
            headers = {"User-Agent": self.user_agent}
            with httpx.Client(follow_redirects=True, timeout=12.0) as client:
                resp = client.head(self.url, headers=headers)
                if resp.status_code not in (200, 206):
                    # Fallback to GET with Range 0-0
                    headers["Range"] = "bytes=0-0"
                    resp = client.get(self.url, headers=headers)

                total_bytes = -1
                cl = resp.headers.get("content-length")
                if cl:
                    try:
                        total_bytes = int(cl)
                    except ValueError:
                        pass

                supports_range = (
                    resp.headers.get("accept-ranges", "").lower() == "bytes" or
                    resp.status_code == 206
                )
                cd = resp.headers.get("content-disposition", "")
                filename = extract_filename_from_url(str(resp.url), cd)

                self.finished_signal.emit(filename, total_bytes, supports_range)
        except Exception as e:
            self.error_signal.emit(str(e))


class AddDownloadDialog(QDialog):
    """Dialog for creating new download task."""

    def __init__(self, config: Config, initial_url: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.initial_url = initial_url
        self.probe_worker: Optional[ProbeWorker] = None

        self.setWindowTitle("Thêm liên kết tải mới — HDM")
        self.setMinimumWidth(580)
        self.setMaximumWidth(760)
        self.setModal(True)

        self._init_ui()
        if self.initial_url:
            self.url_input.setText(self.initial_url)
            self._on_probe_clicked()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. URL Section
        url_label = QLabel("Địa chỉ tải xuống (URL):", self)
        url_label.setObjectName("section_label")
        layout.addWidget(url_label)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Dán liên kết tải xuống tại đây (http:// hoặc https://)...")
        self.url_input.textChanged.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)

        self.btn_probe = QPushButton("Kiểm tra link", self)
        self.btn_probe.setObjectName("btn_secondary")
        self.btn_probe.setMinimumWidth(135)
        self.btn_probe.clicked.connect(self._on_probe_clicked)
        url_row.addWidget(self.btn_probe)
        layout.addLayout(url_row)

        # 2. Probe Info Box
        self.info_box = QFrame(self)
        self.info_box.setVisible(False)
        self.info_layout = QHBoxLayout(self.info_box)
        self.info_layout.setContentsMargins(12, 8, 12, 8)
        self.info_label = QLabel("", self.info_box)
        self.info_label.setWordWrap(True)
        self.info_layout.addWidget(self.info_label)
        layout.addWidget(self.info_box)

        # 3. Target File Parameters Card
        card = QFrame(self)
        card.setObjectName("form_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        # Filename
        card_layout.addWidget(QLabel("Tên tệp lưu vào máy:", self))
        self.filename_input = QLineEdit(self)
        self.filename_input.setPlaceholderText("Tên tệp...")
        card_layout.addWidget(self.filename_input)

        # Save Directory
        card_layout.addWidget(QLabel("Thư mục lưu:", self))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_input = QLineEdit(self)
        self.dir_input.setText(self.config.default_save_dir)
        dir_row.addWidget(self.dir_input)

        btn_browse = QPushButton("Chọn...", self)
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(btn_browse)
        card_layout.addLayout(dir_row)

        # Options Row: Category & Connections
        opt_grid = QGridLayout()
        opt_grid.setHorizontalSpacing(14)
        opt_grid.setVerticalSpacing(4)

        opt_grid.addWidget(QLabel("Phân loại:", self), 0, 0)
        self.cat_combo = QComboBox(self)
        for cat in FileCategory:
            if cat != FileCategory.ALL:
                self.cat_combo.addItem(cat.value)
        opt_grid.addWidget(self.cat_combo, 1, 0)

        opt_grid.addWidget(QLabel("Số luồng tải:", self), 0, 1)
        self.conn_spin = QSpinBox(self)
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(self.config.default_connections)
        opt_grid.addWidget(self.conn_spin, 1, 1)

        card_layout.addLayout(opt_grid)
        layout.addWidget(card)

        # 4. Checkbox
        self.chk_auto_start = QCheckBox("Bắt đầu tải ngay lập tức sau khi thêm", self)
        self.chk_auto_start.setChecked(self.config.auto_start)
        layout.addWidget(self.chk_auto_start)

        layout.addSpacing(6)

        # 5. Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Hủy bỏ", self)
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self.btn_download = QPushButton("⬇ Bắt đầu tải", self)
        self.btn_download.clicked.connect(self._on_accept_clicked)
        btn_row.addWidget(self.btn_download)

        layout.addLayout(btn_row)

    def _on_url_changed(self, text: str) -> None:
        url = text.strip()
        if url and not self.filename_input.text():
            fn = extract_filename_from_url(url)
            self.filename_input.setText(fn)
            cat = get_category_for_filename(fn)
            idx = self.cat_combo.findText(cat.value)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)

    def _on_probe_clicked(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return

        self.btn_probe.setEnabled(False)
        self.btn_probe.setText("Đang kiểm tra...")
        self.info_box.setVisible(True)
        colors = get_palette()
        self.info_box.setStyleSheet(
            f"background-color: {colors['accent_soft']};"
            f" border: 1px solid {colors['accent_border']}; border-radius: 6px;"
        )
        self.info_label.setText("⏳ Đang truy vấn máy chủ từ xa...")
        self.info_label.setStyleSheet(f"color: {colors['info']}; font-weight: 500;")

        self.probe_worker = ProbeWorker(url, self.config.user_agent)
        self.probe_worker.finished_signal.connect(self._on_probe_finished)
        self.probe_worker.error_signal.connect(self._on_probe_error)
        self.probe_worker.start()

    def _on_probe_finished(self, filename: str, total_bytes: int, supports_range: bool) -> None:
        self.btn_probe.setEnabled(True)
        self.btn_probe.setText("Kiểm tra link")

        if filename:
            self.filename_input.setText(filename)
            cat = get_category_for_filename(filename)
            idx = self.cat_combo.findText(cat.value)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)

        size_text = format_bytes(total_bytes) if total_bytes > 0 else "Không rõ kích thước"
        range_text = "Hỗ trợ đa luồng & Tiếp tục tải (Range 206)" if supports_range else "Chỉ hỗ trợ tải 1 luồng"

        has_space, free_bytes, _ = check_free_space(self.dir_input.text(), total_bytes)
        space_str = f"Trống {format_bytes(free_bytes)}"

        self.info_box.setVisible(True)
        colors = get_palette()
        if not has_space and total_bytes > 0:
            self.info_box.setStyleSheet(
                f"background-color: {colors['danger_bg']};"
                f" border: 1px solid {colors['danger_border']}; border-radius: 6px;"
            )
            self.info_label.setText(
                f"📦 Dung lượng: {size_text}  •  {range_text}\n"
                f"⚠️ CẢNH BÁO: Ổ đĩa lưu không đủ dung lượng ({space_str}). Hãy đổi sang thư mục trên ổ khác (như D:)!"
            )
            self.info_label.setStyleSheet(
                f"color: {colors['danger']}; font-weight: 700; font-size: 11px;"
            )
        else:
            self.info_box.setStyleSheet(
                f"background-color: {colors['success_bg']};"
                f" border: 1px solid {colors['success_border']}; border-radius: 6px;"
            )
            self.info_label.setText(f"✓ Dung lượng: {size_text}  |  ⚡ {range_text}  |  📁 {space_str}")
            self.info_label.setStyleSheet(
                f"color: {colors['success']}; font-weight: 600; font-size: 11px;"
            )

    def _on_probe_error(self, err_msg: str) -> None:
        self.btn_probe.setEnabled(True)
        self.btn_probe.setText("Kiểm tra link")
        self.info_box.setVisible(True)
        colors = get_palette()
        self.info_box.setStyleSheet(
            f"background-color: {colors['warning_bg']};"
            f" border: 1px solid {colors['warning_border']}; border-radius: 6px;"
        )
        self.info_label.setText(f"⚠️ Chưa lấy được chi tiết tệp: {err_msg}")
        self.info_label.setStyleSheet(f"color: {colors['warning']}; font-size: 11px;")

    def _on_browse_clicked(self) -> None:
        chosen_dir = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục lưu tệp",
            self.dir_input.text(),
        )
        if chosen_dir:
            self.dir_input.setText(chosen_dir)

    def _on_accept_clicked(self) -> None:
        url = self.url_input.text().strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập đường dẫn URL hợp lệ (http:// hoặc https://).")
            return

        save_dir = self.dir_input.text().strip()
        if not save_dir:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn thư mục lưu tệp.")
            return

        self.accept()

    def get_result_data(self) -> dict:
        """Return the collected download options."""
        return {
            "url": self.url_input.text().strip(),
            "filename": self.filename_input.text().strip(),
            "save_dir": self.dir_input.text().strip(),
            "connections": self.conn_spin.value(),
            "auto_start": self.chk_auto_start.isChecked(),
        }
