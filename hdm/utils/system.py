"""System integration and OS helper utilities for HDM.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys


def is_windows() -> bool:
    """Check if the operating system is Windows."""
    return platform.system() == "Windows"


def get_default_downloads_folder() -> str:
    """Get the user's standard Downloads folder."""
    if is_windows():
        try:
            import winreg
            sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
                return str(winreg.QueryValueEx(key, downloads_guid)[0])
        except Exception:
            pass

    return os.path.join(os.path.expanduser("~"), "Downloads")


def get_app_data_folder() -> str:
    """Get persistent HDM data directory in AppData (Windows) or .config (Linux/macOS)."""
    if is_windows():
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "HDM")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = os.path.join(base, "hdm")

    os.makedirs(path, exist_ok=True)
    return path


def open_file_in_explorer(file_path: str) -> None:
    """Reveal the file in Windows Explorer or open its parent directory."""
    if not os.path.exists(file_path):
        return

    if is_windows():
        norm_path = os.path.normpath(file_path)
        subprocess.run(["explorer.exe", f"/select,{norm_path}"], check=False)
    elif platform.system() == "Darwin":
        subprocess.run(["open", "-R", file_path], check=False)
    else:
        subprocess.run(["xdg-open", os.path.dirname(file_path)], check=False)


def open_folder(folder_path: str) -> None:
    """Open folder in system file manager."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)

    if is_windows():
        os.startfile(folder_path)  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.run(["open", folder_path], check=False)
    else:
        subprocess.run(["xdg-open", folder_path], check=False)


def launch_file(file_path: str) -> None:
    """Execute or open a downloaded file with default associated program."""
    if not os.path.exists(file_path):
        return

    if is_windows():
        os.startfile(file_path)  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.run(["open", file_path], check=False)
    else:
        subprocess.run(["xdg-open", file_path], check=False)


def get_app_icon():
    """Find and load app icon with dynamic fallback to ensure an icon is always present."""
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QLinearGradient
    from PySide6.QtCore import Qt, QPointF

    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "app.ico"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.ico"),
        os.path.join(os.path.dirname(sys.executable), "app.ico"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "app.ico"),
        "app.ico",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            try:
                icon = QIcon(p)
                if not icon.isNull():
                    return icon
            except Exception:
                pass

    # Fallback: In-memory drawn icon
    size = 64
    img = QPixmap(size, size)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#3b82f6"))
    grad.setColorAt(1, QColor("#1d4ed8"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    painter.setPen(QPen(QColor("#ffffff"), max(2.0, size * 0.12), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    mid_x = size / 2.0
    top_y = size * 0.22
    bot_y = size * 0.62
    painter.drawLine(QPointF(mid_x, top_y), QPointF(mid_x, bot_y))
    head_w = size * 0.22
    head_h = size * 0.18
    painter.drawLine(QPointF(mid_x - head_w, bot_y - head_h), QPointF(mid_x, bot_y))
    painter.drawLine(QPointF(mid_x + head_w, bot_y - head_h), QPointF(mid_x, bot_y))
    tray_y = size * 0.78
    tray_margin = size * 0.24
    painter.drawLine(QPointF(tray_margin, tray_y), QPointF(size - tray_margin, tray_y))
    painter.end()

    return QIcon(img)

