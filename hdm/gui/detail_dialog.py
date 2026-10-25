"""Download Progress Detail and Chunk Map Inspector Dialog.
Refined modern styling with card container, status chips, and real-time metrics.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QFrame,
    QWidget,
    QSizePolicy,
)

from hdm.core.models import DownloadTask, TaskStatus
from hdm.gui.chunk_widget import ChunkMapWidget
from hdm.gui.style import get_palette
from hdm.utils.formatters import format_bytes, format_eta, format_speed
from hdm.utils.i18n import get_status_display, tr
from hdm.utils.system import launch_file, open_folder


class DownloadDetailDialog(QDialog):
    """Dialog showing real-time task progress and visual chunk map."""

    def __init__(self, task: DownloadTask, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task = task

        self.setWindowTitle(tr("detail_dialog_title", filename=self.task.filename))
        self.resize(720, 490)
        self.setMinimumWidth(660)
        self.setMaximumWidth(800)

        self._init_ui()

        # Update timer (5 Hz)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_ui)
        self.timer.start(200)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. Header Information Card (compact, minimal whitespace)
        card = QFrame(self)
        card.setObjectName("info_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(4)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)

        # File
        grid.addWidget(QLabel(tr("detail_lbl_filename")), 0, 0)
        self.lbl_file = QLabel(self.task.filename)
        self.lbl_file.setObjectName("dialog_value_accent")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setMaximumWidth(380)
        grid.addWidget(self.lbl_file, 0, 1)

        # Status
        grid.addWidget(QLabel(tr("detail_lbl_status")), 0, 2)
        self.lbl_status = QLabel(get_status_display(self.task.status.value))
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        grid.addWidget(self.lbl_status, 0, 3, Qt.AlignLeft | Qt.AlignVCenter)

        # URL
        grid.addWidget(QLabel(tr("detail_lbl_url")), 1, 0)
        self.url_input = QLineEdit(self.task.url, self)
        self.url_input.setReadOnly(True)
        self.url_input.setToolTip(self.task.url)
        self.url_input.setObjectName("url_input")
        grid.addWidget(self.url_input, 1, 1, 1, 3)

        # Size & Downloaded
        grid.addWidget(QLabel(tr("detail_lbl_size")), 2, 0)
        self.lbl_size = QLabel("")
        self.lbl_size.setObjectName("dialog_value")
        grid.addWidget(self.lbl_size, 2, 1)

        # Speed & ETA
        grid.addWidget(QLabel(tr("detail_lbl_speed")), 2, 2)
        self.lbl_speed = QLabel("")
        self.lbl_speed.setObjectName("dialog_value_info")
        grid.addWidget(self.lbl_speed, 2, 3)

        card_layout.addLayout(grid)
        layout.addWidget(card)

        # 2. Main Overall Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # 3. Chunk Map Visualization Widget
        map_title = QLabel(tr("detail_chunk_map_title"), self)
        map_title.setObjectName("section_label")
        layout.addWidget(map_title)

        self.chunk_widget = ChunkMapWidget(self)
        self.chunk_widget.set_task(self.task)
        layout.addWidget(self.chunk_widget)

        # 4. Action Buttons Footer
        btn_row = QHBoxLayout()

        self.btn_open_file = QPushButton(tr("detail_btn_open_file"), self)
        self.btn_open_file.setObjectName("btn_secondary")
        self.btn_open_file.clicked.connect(lambda: launch_file(self.task.full_path))
        btn_row.addWidget(self.btn_open_file)

        self.btn_open_dir = QPushButton(tr("detail_btn_open_dir"), self)
        self.btn_open_dir.setObjectName("btn_secondary")
        self.btn_open_dir.clicked.connect(lambda: open_folder(self.task.save_dir))
        btn_row.addWidget(self.btn_open_dir)

        btn_row.addStretch()

        btn_close = QPushButton(tr("detail_btn_close"), self)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

        self._refresh_ui()

    def _refresh_ui(self) -> None:
        """Poll and refresh the dialog widgets."""
        self.lbl_status.setText(get_status_display(self.task.status.value))

        # Update status badge color (palette-aware for light/dark themes)
        colors = get_palette()
        badge = (
            "background-color: {bg}; color: {fg}; border: 1px solid {bd};"
            " border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
        )
        status_styles = {
            TaskStatus.COMPLETED: badge.format(
                bg=colors["success_bg"], fg=colors["success"], bd=colors["success_border"]
            ),
            TaskStatus.DOWNLOADING: badge.format(
                bg=colors["accent_soft"], fg=colors["info"], bd=colors["accent_border"]
            ),
            TaskStatus.PROCESSING: badge.format(
                bg=colors["warning_bg"], fg=colors["warning"], bd=colors["warning_border"]
            ),
            TaskStatus.CONNECTING: badge.format(
                bg=colors["accent_soft"], fg=colors["cyan"], bd=colors["accent_border"]
            ),
            TaskStatus.QUEUED: badge.format(
                bg=colors["accent_soft"], fg=colors["purple"], bd=colors["accent_border"]
            ),
            TaskStatus.PAUSED: badge.format(
                bg=colors["warning_bg"], fg=colors["warning"], bd=colors["warning_border"]
            ),
            TaskStatus.ERROR: badge.format(
                bg=colors["danger_bg"], fg=colors["danger"], bd=colors["danger_border"]
            ),
            TaskStatus.CANCELLED: badge.format(
                bg=colors["chip_bg"], fg=colors["muted"], bd=colors["button_border"]
            ),
        }
        self.lbl_status.setStyleSheet(
            status_styles.get(
                self.task.status,
                badge.format(
                    bg=colors["chip_bg"], fg=colors["text"], bd=colors["button_border"]
                ),
            )
        )

        # Size display
        down_str = format_bytes(self.task.downloaded_bytes)
        tot_str = format_bytes(self.task.total_bytes) if self.task.total_bytes > 0 else "Không rõ"
        self.lbl_size.setText(f"{down_str} / {tot_str} ({self.task.progress_percent:.1f}%)")

        # Speed and ETA
        if self.task.status == TaskStatus.DOWNLOADING and self.task.speed > 0:
            speed_str = format_speed(self.task.speed)
            eta_str = format_eta(self.task.eta)
            self.lbl_speed.setText(f"{speed_str}  ({tr('detail_remaining', eta=eta_str)})")
        elif self.task.status == TaskStatus.PROCESSING:
            self.lbl_speed.setText(self.task.error_message or "Đang xử lý / chuyển đổi tệp...")
        else:
            self.lbl_speed.setText("--")

        # Progress bar
        self.progress_bar.setValue(int(self.task.progress_percent))
        self.progress_bar.setFormat(f"{self.task.progress_percent:.1f}%")

        # Chunk Map
        self.chunk_widget.set_task(self.task)

        # Buttons enable
        is_done = self.task.status == TaskStatus.COMPLETED
        self.btn_open_file.setEnabled(is_done)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        super().closeEvent(event)
