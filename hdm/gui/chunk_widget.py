"""Interactive Chunk Map visualizer widget for HDM.
Renders real-time dynamic segment allocations and chunk progress bars in modern IDM style.
Refined with animated write heads, top glass highlights, and WCAG-compliant status badges.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QBrush, QLinearGradient, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
)

from hdm.core.models import DownloadTask
from hdm.gui.style import get_palette
from hdm.utils.formatters import format_bytes, format_speed
from hdm.utils.i18n import tr


class ChunkProgressBar(QWidget):
    """Custom paint widget rendering the modern visual segmented byte-map."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task: Optional[DownloadTask] = None
        self.setFixedHeight(44)
        self.setMinimumWidth(260)

    def set_task(self, task: Optional[DownloadTask]) -> None:
        self.task = task
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self.rect()
        w = float(rect.width())
        h = float(rect.height())
        colors = get_palette()

        # 1. Outer background card with 8px radius
        painter.setPen(QPen(QColor(colors["progress_border"]), 1))
        painter.setBrush(QBrush(QColor(colors["progress_bg"])))
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), 8, 8)

        if not self.task or not self.task.chunks or self.task.total_bytes <= 0:
            # Single-stream or unknown size fallback
            if self.task and self.task.progress_percent > 0:
                prog_w = (self.task.progress_percent / 100.0) * (w - 2.0)
                grad = QLinearGradient(1, 1, prog_w, h - 2)
                grad.setColorAt(0.0, QColor(colors["progress_from"]))
                grad.setColorAt(1.0, QColor(colors["progress_to"]))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(grad))
                painter.drawRoundedRect(QRectF(1, 1, prog_w, h - 2), 7, 7)
            return

        total_bytes = self.task.total_bytes

        # Clip inside the rounded rect
        painter.setClipRect(QRectF(1.0, 1.0, w - 2.0, h - 2.0))

        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)

        for chunk in self.task.chunks:
            x_start = (chunk.start_byte / total_bytes) * w
            x_end = ((chunk.end_byte + 1) / total_bytes) * w
            chunk_width = max(1.0, x_end - x_start)

            # 1. Background of chunk (undownloaded byte range)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(colors["chunk_bg"])))
            painter.drawRect(QRectF(x_start, 1, chunk_width, h - 2))

            # 2. Downloaded portion
            if chunk.downloaded_bytes > 0:
                downloaded_w = (chunk.downloaded_bytes / chunk.total_bytes) * chunk_width
                if chunk.status == "completed":
                    grad = QLinearGradient(x_start, 0, x_start + downloaded_w, 0)
                    grad.setColorAt(0.0, QColor(colors["chunk_done_from"]))
                    grad.setColorAt(1.0, QColor(colors["chunk_done_to"]))
                else:
                    grad = QLinearGradient(x_start, 0, x_start + downloaded_w, 0)
                    grad.setColorAt(0.0, QColor(colors["chunk_active_from"]))
                    grad.setColorAt(1.0, QColor(colors["chunk_active_to"]))

                painter.setBrush(QBrush(grad))
                painter.drawRect(QRectF(x_start, 1, downloaded_w, h - 2))

                # Active write head needle & glow (if thread is actively streaming)
                if chunk.status != "completed" and downloaded_w < chunk_width:
                    head_x = x_start + downloaded_w
                    # Glow needle
                    painter.setPen(QPen(QColor(255, 255, 255, 220), 2.0))
                    painter.drawLine(int(head_x), 2, int(head_x), int(h - 3))

            # 3. Delimiter line between chunks
            painter.setPen(QPen(QColor(colors["chunk_divider"]), 1.5))
            painter.drawLine(int(x_start), 1, int(x_start), int(h - 2))

            # 4. Thread label if chunk is wide enough
            if chunk_width > 44:
                label_color = colors["chunk_text"] if chunk.downloaded_bytes > 0 else colors["text_faint"]
                painter.setPen(QPen(QColor(label_color)))
                if chunk_width > 75:
                    lbl = f"#{chunk.chunk_id} ({chunk.progress_percent:.0f}%)"
                else:
                    lbl = f"#{chunk.chunk_id}"
                painter.drawText(
                    QRectF(x_start + 6, 1, chunk_width - 12, h - 2),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    lbl
                )

        # 5. Top subtle glass highlight across the bar
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1.0))
        painter.drawLine(3, 2, int(w - 3), 2)


class ChunkMapWidget(QWidget):
    """Complete chunk inspection panel including segmented bar and chunk details table."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task: Optional[DownloadTask] = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Segmented Progress Bar
        self.chunk_bar = ChunkProgressBar(self)
        layout.addWidget(self.chunk_bar)

        # Legend / Explanation Label
        legend_row = QHBoxLayout()
        legend_row.setSpacing(14)

        lbl_comp = QLabel(tr("detail_legend_done"), self)
        lbl_comp.setObjectName("legend_done")
        legend_row.addWidget(lbl_comp)

        lbl_down = QLabel(tr("detail_legend_active"), self)
        lbl_down.setObjectName("legend_active")
        legend_row.addWidget(lbl_down)

        lbl_pend = QLabel(tr("detail_legend_pending"), self)
        lbl_pend.setObjectName("legend_pending")
        legend_row.addWidget(lbl_pend)

        lbl_info = QLabel(tr("detail_legend_hint"), self)
        lbl_info.setObjectName("legend_hint")
        legend_row.addWidget(lbl_info)
        legend_row.addStretch()

        layout.addLayout(legend_row)

        # Table showing individual chunk details
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            tr("chunk_col_thread"),
            tr("chunk_col_range"),
            tr("chunk_col_size"),
            tr("chunk_col_downloaded"),
            tr("chunk_col_progress"),
            tr("chunk_col_status"),
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

    def set_task(self, task: Optional[DownloadTask]) -> None:
        self.task = task
        self.chunk_bar.set_task(task)
        self.update_table()

    def update_table(self) -> None:
        if not self.task or not self.task.chunks:
            self.table.setRowCount(0)
            return

        chunks = self.task.chunks
        self.table.setRowCount(len(chunks))

        bold_font = QFont()
        bold_font.setBold(True)

        colors = get_palette()

        for row, c in enumerate(chunks):
            # Luồng # (chỉ hiển thị số hiệu luồng #1, #2...)
            item_id = QTableWidgetItem(f"#{c.chunk_id}")
            item_id.setTextAlignment(Qt.AlignCenter)
            item_id.setFont(bold_font)
            self.table.setItem(row, 0, item_id)

            # Phạm vi byte
            range_str = f"{c.start_byte:,} — {c.end_byte:,}"
            self.table.setItem(row, 1, QTableWidgetItem(range_str))

            # Dung lượng
            item_tot = QTableWidgetItem(format_bytes(c.total_bytes))
            item_tot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, item_tot)

            # Đã tải
            item_down = QTableWidgetItem(format_bytes(c.downloaded_bytes))
            item_down.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, item_down)

            # Tiến độ
            item_pct = QTableWidgetItem(f"{c.progress_percent:.1f}%")
            item_pct.setTextAlignment(Qt.AlignCenter)
            item_pct.setFont(bold_font)
            self.table.setItem(row, 4, item_pct)

            # Trạng thái (tốc độ nằm dưới chữ Đang tải, không dùng icon)
            if c.status == "completed":
                st = tr("chunk_st_completed")
                color = colors["success"]
            elif c.status == "downloading":
                if c.speed > 0:
                    st = f"{tr('chunk_st_downloading')}\n({format_speed(c.speed)})"
                else:
                    st = tr("chunk_st_downloading")
                color = colors["info"]
            elif c.status == "failed":
                st = tr("chunk_st_retry")
                color = colors["danger"]
            else:
                st = tr("chunk_st_waiting")
                color = colors["muted"]

            item_status = QTableWidgetItem(st)
            item_status.setTextAlignment(Qt.AlignCenter)
            item_status.setForeground(QColor(color))
            item_status.setFont(bold_font)
            self.table.setItem(row, 5, item_status)
