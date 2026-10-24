"""Download Confirmation Modal Dialog for HDM (IDM-style).
Pops up when a download link is captured from browser extension, command-line, or 'Add URL'.
Provides real-time file probe (size, resume capability, free disk space), category detection,
and three clear actions: [Start Download], [Download Later], and [Cancel].
"""

from __future__ import annotations

import os
from typing import Dict, Optional

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
    QComboBox,
    QMessageBox,
    QFrame,
    QWidget,
)

from hdm.core.config import Config
from hdm.core.engine import is_streaming_url
from hdm.core.sparse_file import check_free_space
from hdm.gui.icons import get_icon
from hdm.gui.style import get_palette
from hdm.utils.category import FileCategory, get_category_for_filename, get_category_subfolder
from hdm.utils.formatters import extract_filename_from_url, format_bytes
from hdm.utils.i18n import get_category_display, tr


class ProbeWorker(QThread):
    """Background thread to query URL metadata without freezing the modal."""
    finished_signal = Signal(str, int, bool)  # filename, total_bytes, supports_range
    error_signal = Signal(str)

    def __init__(
        self,
        url: str,
        user_agent: str,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__()
        self.url = url
        self.user_agent = user_agent
        self.custom_headers = custom_headers or {}

    def run(self) -> None:
        if is_streaming_url(self.url):
            try:
                import yt_dlp
                from hdm.utils.formatters import clean_filename

                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "nocheckcertificate": True,
                    "noplaylist": True,
                }
                if self.custom_headers:
                    probe_headers = dict(self.custom_headers)
                    probe_headers.pop("Cookie", None)
                    probe_headers.pop("cookie", None)
                    if probe_headers:
                        ydl_opts["http_headers"] = probe_headers
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                    title = info.get("title", "")
                    clean_t = clean_filename(title) if title else "video"
                    ext = info.get("ext", "mp4")
                    if ext in ("webm", "mkv", "unknown_video"):
                        ext = "mp4"
                    filename = f"{clean_t}.{ext}"
                    total_bytes = info.get("filesize") or info.get("filesize_approx") or -1
                    self.finished_signal.emit(filename, total_bytes, True)
                    return
            except Exception as e:
                # Fallback to standard HTTP probe if yt-dlp probe fails
                pass

        try:
            headers = {"User-Agent": self.user_agent}
            headers.update(self.custom_headers)
            with httpx.Client(follow_redirects=True, timeout=12.0) as client:
                resp = client.head(self.url, headers=headers)
                if resp.status_code >= 400:
                    self.error_signal.emit(f"HTTP {resp.status_code}")
                    return

                if resp.status_code not in (200, 206):
                    # Fallback to GET with Range 0-0
                    range_headers = dict(headers)
                    range_headers["Range"] = "bytes=0-0"
                    resp = client.get(self.url, headers=range_headers)
                    if resp.status_code >= 400:
                        self.error_signal.emit(f"HTTP {resp.status_code}")
                        return

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


class DownloadConfirmDialog(QDialog):
    """IDM-Style Modal Dialog to confirm or customize a download task."""

    def __init__(
        self,
        config: Config,
        initial_url: str = "",
        initial_filename: str = "",
        custom_headers: Optional[Dict[str, str]] = None,
        is_captured: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.initial_url = initial_url
        self.initial_filename = initial_filename
        self.custom_headers = custom_headers or {}
        self.is_captured = is_captured

        # Action selected: 'start_now', 'download_later', or 'cancel'
        self.selected_action = "start_now"
        self.probe_worker: Optional[ProbeWorker] = None
        self._last_probed_url: str = ""

        # Window settings
        title = tr("confirm_dialog_title") if (is_captured or initial_url) else tr("add_dialog_title")
        self.setWindowTitle(title)
        self.setMinimumWidth(620)
        self.setMaximumWidth(760)
        self.setModal(True)

        if is_captured:
            # Ensure modal stays on top of external browser window
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._init_ui()

        # Pre-fill data if provided
        if is_streaming_url(self.initial_url):
            idx = self.cat_combo.findData(FileCategory.VIDEO.value)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)

        if self.initial_filename:
            self.filename_input.setText(self.initial_filename)
            self._sync_category_from_filename(self.initial_filename)

        if self.initial_url:
            self.url_input.setText(self.initial_url)
            self._on_probe_clicked()

    def _init_ui(self) -> None:
        colors = get_palette()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        # 1. Header Banner
        header_frame = QFrame(self)
        header_frame.setObjectName("modal_header")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(12)

        self.icon_label = QLabel(header_frame)
        self.icon_label.setPixmap(get_icon("download", colors["accent"], size=30).pixmap(30, 30))
        header_layout.addWidget(self.icon_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel(tr("confirm_header_title"), header_frame)
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {colors['text']};")
        title_col.addWidget(title_lbl)

        sub_lbl = QLabel(tr("confirm_header_desc"), header_frame)
        sub_lbl.setStyleSheet(f"font-size: 11px; color: {colors['text_muted']};")
        title_col.addWidget(sub_lbl)

        header_layout.addLayout(title_col)
        header_layout.addStretch()
        layout.addWidget(header_frame)

        # 2. URL Section
        url_label = QLabel(tr("add_url_label"), self)
        url_label.setObjectName("section_label")
        layout.addWidget(url_label)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText(tr("add_url_placeholder"))
        self.url_input.textChanged.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)

        self.btn_probe = QPushButton(tr("add_btn_check"), self)
        self.btn_probe.setObjectName("btn_secondary")
        self.btn_probe.setMinimumWidth(110)
        self.btn_probe.clicked.connect(self._on_probe_clicked)
        url_row.addWidget(self.btn_probe)
        layout.addLayout(url_row)

        # 3. Probe Info Box (Real-time File Metadata)
        self.info_box = QFrame(self)
        self.info_box.setVisible(False)
        self.info_layout = QHBoxLayout(self.info_box)
        self.info_layout.setContentsMargins(12, 9, 12, 9)
        self.info_label = QLabel("", self.info_box)
        self.info_label.setWordWrap(True)
        self.info_layout.addWidget(self.info_label)
        layout.addWidget(self.info_box)

        # 4. Target File Parameters Card
        card = QFrame(self)
        card.setObjectName("form_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        # Filename
        card_layout.addWidget(QLabel(tr("add_file_name"), self))
        self.filename_input = QLineEdit(self)
        self.filename_input.setPlaceholderText("...")
        self.filename_input.textChanged.connect(self._on_filename_changed)
        card_layout.addWidget(self.filename_input)

        # Save Directory
        card_layout.addWidget(QLabel(tr("add_save_to"), self))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_input = QLineEdit(self)
        self.dir_input.setText(self.config.default_save_dir)
        dir_row.addWidget(self.dir_input)

        btn_browse = QPushButton(tr("add_btn_browse"), self)
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(btn_browse)
        card_layout.addLayout(dir_row)

        # Category & Connections Row
        opt_grid = QGridLayout()
        opt_grid.setHorizontalSpacing(14)
        opt_grid.setVerticalSpacing(4)

        opt_grid.addWidget(QLabel(tr("add_category"), self), 0, 0)
        self.cat_combo = QComboBox(self)
        for cat in FileCategory:
            if cat != FileCategory.ALL:
                self.cat_combo.addItem(get_category_display(cat.value), cat.value)
        self.cat_combo.currentIndexChanged.connect(self._on_category_selected)
        opt_grid.addWidget(self.cat_combo, 1, 0)

        opt_grid.addWidget(QLabel(tr("add_connections"), self), 0, 1)
        self.conn_spin = QSpinBox(self)
        self.conn_spin.setRange(1, 32)
        self.conn_spin.setValue(self.config.default_connections)
        opt_grid.addWidget(self.conn_spin, 1, 1)

        card_layout.addLayout(opt_grid)
        layout.addWidget(card)

        layout.addSpacing(6)

        # 5. IDM Action Buttons Trio: [Cancel]  ...  [Download Later] [Start Download]
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton(f"✕  {tr('confirm_btn_cancel')}", self)
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        btn_row.addStretch()

        self.btn_download_later = QPushButton(f"⏸  {tr('confirm_btn_download_later')}", self)
        self.btn_download_later.setObjectName("btn_secondary")
        self.btn_download_later.setToolTip("Thêm vào danh sách tải ở trạng thái Tạm dừng (tải sau)")
        self.btn_download_later.clicked.connect(self._on_download_later)
        btn_row.addWidget(self.btn_download_later)

        self.btn_download_now = QPushButton(f"⬇  {tr('confirm_btn_start_now')}", self)
        self.btn_download_now.setDefault(True)
        self.btn_download_now.setToolTip("Bắt đầu tải tệp ngay lập tức (Nhấn Enter)")
        self.btn_download_now.clicked.connect(self._on_download_now)
        btn_row.addWidget(self.btn_download_now)

        layout.addLayout(btn_row)

    def _sync_category_from_filename(self, filename: str) -> None:
        cat = get_category_for_filename(filename)
        idx = self.cat_combo.findData(cat.value)
        if idx >= 0 and idx != self.cat_combo.currentIndex():
            self.cat_combo.blockSignals(True)
            self.cat_combo.setCurrentIndex(idx)
            self.cat_combo.blockSignals(False)

        # If auto-categorize is enabled, update save folder
        if self.config.auto_categorize:
            sub = get_category_subfolder(cat, self.config.default_save_dir)
            self.dir_input.setText(sub)

    def _on_url_changed(self, text: str) -> None:
        url = text.strip()
        if url and not self.filename_input.text():
            fn = extract_filename_from_url(url)
            self.filename_input.setText(fn)
            self._sync_category_from_filename(fn)

    def _on_filename_changed(self, text: str) -> None:
        fn = text.strip()
        if fn:
            self._sync_category_from_filename(fn)

    def _on_category_selected(self) -> None:
        cat_val = self.cat_combo.currentData()
        if self.config.auto_categorize and cat_val:
            try:
                cat = FileCategory(cat_val)
                sub = get_category_subfolder(cat, self.config.default_save_dir)
                self.dir_input.setText(sub)
            except Exception:
                pass

    def _on_probe_clicked(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return

        self._last_probed_url = url
        self.btn_probe.setEnabled(False)
        self.btn_probe.setText(tr("add_btn_checking"))
        self.info_box.setVisible(True)
        colors = get_palette()
        self.info_box.setStyleSheet(
            f"background-color: {colors['accent_soft']};"
            f" border: 1px solid {colors['accent_border']}; border-radius: 6px;"
        )
        self.info_label.setText(f"⏳ {tr('add_btn_checking')}")
        self.info_label.setStyleSheet(f"color: {colors['info']}; font-weight: 500;")

        self.probe_worker = ProbeWorker(url, self.config.user_agent, self.custom_headers)
        self.probe_worker.finished_signal.connect(self._on_probe_finished)
        self.probe_worker.error_signal.connect(self._on_probe_error)
        self.probe_worker.start()

    def _on_probe_finished(self, filename: str, total_bytes: int, supports_range: bool) -> None:
        self.btn_probe.setEnabled(True)
        self.btn_probe.setText(tr("add_btn_check"))

        curr_text = self.filename_input.text().strip()
        is_generic = not curr_text or curr_text in ("watch", "watch.html", "index.html", "download", "videoplayback")
        if filename and (is_generic or is_streaming_url(self.url_input.text().strip())):
            self.filename_input.setText(filename)
            self._sync_category_from_filename(filename)

        size_text = format_bytes(total_bytes) if total_bytes > 0 else "Không rõ kích thước"
        range_text = tr("add_range_yes") if supports_range else tr("add_range_no")

        has_space, free_bytes, _ = check_free_space(self.dir_input.text(), total_bytes)
        space_str = tr("add_free_space", space=format_bytes(free_bytes))

        self.info_box.setVisible(True)
        colors = get_palette()
        if not has_space and total_bytes > 0:
            self.info_box.setStyleSheet(
                f"background-color: {colors['danger_bg']};"
                f" border: 1px solid {colors['danger_border']}; border-radius: 6px;"
            )
            self.info_label.setText(
                f"📦 Dung lượng: {size_text}  •  {range_text}\n"
                f"⚠️ {space_str} (Không đủ dung lượng tải!)"
            )
            self.info_label.setStyleSheet(
                f"color: {colors['danger']}; font-weight: 700; font-size: 11px;"
            )
        else:
            self.info_box.setStyleSheet(
                f"background-color: {colors['success_bg']};"
                f" border: 1px solid {colors['success_border']}; border-radius: 6px;"
            )
            self.info_label.setText(f"✓ {size_text}  |  ⚡ {range_text}  |  📁 {space_str}")
            self.info_label.setStyleSheet(
                f"color: {colors['success']}; font-weight: 600; font-size: 11px;"
            )

    def _on_probe_error(self, err_msg: str) -> None:
        self.btn_probe.setEnabled(True)
        self.btn_probe.setText(tr("add_btn_check"))
        self.info_box.setVisible(True)
        colors = get_palette()
        self.info_box.setStyleSheet(
            f"background-color: {colors['warning_bg']};"
            f" border: 1px solid {colors['warning_border']}; border-radius: 6px;"
        )
        self.info_label.setText(f"⚠️ {err_msg}")
        self.info_label.setStyleSheet(f"color: {colors['warning']}; font-size: 11px;")

    def _on_browse_clicked(self) -> None:
        chosen_dir = QFileDialog.getExistingDirectory(
            self,
            tr("add_save_to"),
            self.dir_input.text(),
        )
        if chosen_dir:
            self.dir_input.setText(chosen_dir)

    def _validate_inputs(self) -> bool:
        url = self.url_input.text().strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            QMessageBox.warning(self, tr("table_status"), tr("add_err_invalid_url"))
            return False

        save_dir = self.dir_input.text().strip()
        if not save_dir:
            QMessageBox.warning(self, tr("table_status"), tr("add_save_to"))
            return False
        return True

    def _on_download_now(self) -> None:
        if not self._validate_inputs():
            return
        self.selected_action = "start_now"
        self.accept()

    def _on_download_later(self) -> None:
        if not self._validate_inputs():
            return
        self.selected_action = "download_later"
        self.accept()

    def get_result_data(self) -> dict:
        """Return the collected download options."""
        return {
            "url": self.url_input.text().strip(),
            "filename": self.filename_input.text().strip(),
            "save_dir": self.dir_input.text().strip(),
            "category": self.cat_combo.currentData(),
            "connections": self.conn_spin.value(),
            "headers": self.custom_headers,
            "auto_start": (self.selected_action == "start_now"),
            "action": self.selected_action,
        }


# Backwards compatibility alias
AddDownloadDialog = DownloadConfirmDialog
