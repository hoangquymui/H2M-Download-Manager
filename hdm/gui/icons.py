"""Crisp, high-DPI vector icon generator for HDM.
Uses QPainter with antialiasing to generate pixel-perfect icons that never blur or pixelate.
"""

from __future__ import annotations

from typing import Dict, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


_ICON_CACHE: Dict[Tuple[str, str, int], QIcon] = {}


def get_icon(name: str, color_hex: str = "#60A5FA", size: int = 36) -> QIcon:
    """Generate or retrieve a cached high-DPI vector QIcon."""
    cache_key = (name, color_hex.lower(), size)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    # Render at 2x resolution for high-DPI crispness
    render_size = size * 2
    pixmap = QPixmap(render_size, render_size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    color = QColor(color_hex)
    pen = QPen(color)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)

    # Scale painter coordinate system to [0, 24] x [0, 24]
    scale_factor = render_size / 24.0
    painter.scale(scale_factor, scale_factor)

    if name == "add":
        pen.setWidthF(2.6)
        painter.setPen(pen)
        painter.drawLine(QPointF(12, 5), QPointF(12, 19))
        painter.drawLine(QPointF(5, 12), QPointF(19, 12))

    elif name == "resume":
        # Play triangle
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(color)
        path = QPainterPath()
        path.moveTo(8, 5.5)
        path.lineTo(19, 12)
        path.lineTo(8, 18.5)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "pause":
        # Two parallel rounded bars
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(6, 4.5, 3.8, 15), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(14.2, 4.5, 3.8, 15), 1.6, 1.6)

    elif name == "delete":
        # Sleek trash can
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        # Lid
        painter.drawLine(QPointF(4, 6), QPointF(20, 6))
        painter.drawLine(QPointF(9, 6), QPointF(9, 3.5))
        painter.drawLine(QPointF(9, 3.5), QPointF(15, 3.5))
        painter.drawLine(QPointF(15, 3.5), QPointF(15, 6))
        # Body
        path = QPainterPath()
        path.moveTo(6, 6)
        path.lineTo(7.2, 20)
        path.lineTo(16.8, 20)
        path.lineTo(18, 6)
        painter.drawPath(path)
        # Inner lines
        painter.drawLine(QPointF(10, 10), QPointF(10, 16))
        painter.drawLine(QPointF(14, 10), QPointF(14, 16))

    elif name == "folder":
        # Sleek folder outline
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(3, 19)
        path.lineTo(3, 6)
        path.lineTo(8.5, 6)
        path.lineTo(10.5, 8.5)
        path.lineTo(21, 8.5)
        path.lineTo(21, 19)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "download":
        # Arrow pointing down into tray
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(12, 4), QPointF(12, 14.5))
        # Arrowhead
        path = QPainterPath()
        path.moveTo(7, 10)
        path.lineTo(12, 15)
        path.lineTo(17, 10)
        painter.drawPath(path)
        # Base tray
        tray = QPainterPath()
        tray.moveTo(4, 15)
        tray.lineTo(4, 20)
        tray.lineTo(20, 20)
        tray.lineTo(20, 15)
        painter.drawPath(tray)

    elif name == "settings":
        # Sleek gear with 6 teeth
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(12, 12), 3.5, 3.5)
        # Outer ring with notches
        path = QPainterPath()
        import math
        outer_r = 8.5
        inner_r = 6.5
        for i in range(12):
            angle = i * (math.pi / 6)
            r = outer_r if (i % 2 == 0) else inner_r
            x = 12 + r * math.cos(angle)
            y = 12 + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "moon":
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(color)
        path = QPainterPath()
        path.moveTo(12, 3)
        path.cubicTo(6, 3, 3, 9, 3, 15)
        path.cubicTo(3, 19, 6, 21, 10, 21)
        path.cubicTo(8, 17, 9, 11, 15, 8)
        path.cubicTo(16, 7.5, 17, 7.5, 18, 7.5)
        path.cubicTo(17, 5, 14.5, 3, 12, 3)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "sun":
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(12, 12), 4, 4)
        import math
        for i in range(8):
            angle = i * (math.pi / 4)
            x1 = 12 + 6.5 * math.cos(angle)
            y1 = 12 + 6.5 * math.sin(angle)
            x2 = 12 + 9.5 * math.cos(angle)
            y2 = 12 + 9.5 * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    painter.end()

    # Create scalable QIcon with proper size
    icon = QIcon(pixmap)
    _ICON_CACHE[cache_key] = icon
    return icon
