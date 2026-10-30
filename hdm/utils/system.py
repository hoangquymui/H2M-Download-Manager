"""System integration and OS helper utilities for HDM.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys


AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_APP_NAME = "H2M Download Manager"


def is_windows() -> bool:
    """Check if the operating system is Windows."""
    return platform.system() == "Windows"


def get_autostart_command() -> str:
    """Return the quoted command string to launch HDM on Windows startup."""
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        return f'"{exe_path}" --autostart'
    else:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        main_py = os.path.join(root_dir, "main.py")
        if os.path.exists(main_py):
            return f'"{sys.executable}" "{main_py}" --autostart'
        return f'"{sys.executable}" "{sys.argv[0]}" --autostart'


def is_autostart_enabled() -> bool:
    """Check if HDM is configured to run on Windows startup in HKCU\\...\\Run."""
    if not is_windows():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, AUTOSTART_APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    """Enable or disable HDM auto-start with Windows in HKCU\\...\\Run.

    Returns whether the registry actually matches the requested state, so a
    blocked/rolled-back write is visible instead of silently keeping the old
    startup entry alive.
    """
    if not is_windows():
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            AUTOSTART_REG_KEY,
            0,
            winreg.KEY_READ | winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                cmd = get_autostart_command()
                winreg.SetValueEx(key, AUTOSTART_APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_APP_NAME)
                except FileNotFoundError:
                    pass
        return is_autostart_enabled() == enabled
    except Exception:
        return False


def _drive_available(path: str) -> bool:
    """True when the drive holding `path` exists (folders are created on demand)."""
    try:
        drive, _ = os.path.splitdrive(os.path.abspath(path))
    except (OSError, ValueError):
        return False
    return not drive or os.path.exists(drive + os.sep)


def get_default_downloads_folder() -> str:
    """Get the user's standard Downloads folder.

    ``User Shell Folders`` stores expandable values (``%USERPROFILE%\\Downloads``),
    so they must be expanded before use; a moved/removed drive falls back to the
    profile folder instead of pointing downloads at a drive that no longer exists.
    """
    if is_windows():
        import winreg
        downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        for sub_key in (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                    value = str(winreg.QueryValueEx(key, downloads_guid)[0]).strip()
                value = os.path.expandvars(value)
                if value and _drive_available(value):
                    return value
            except Exception:
                continue

    return os.path.join(os.path.expanduser("~"), "Downloads")


def resolve_download_dir(path: str) -> str:
    """Return `path` when it is usable, otherwise the system Downloads folder.

    Guards against an empty value and against a config copied from a machine
    whose download drive (``D:``, ``E:\\``) does not exist here.
    """
    value = os.path.expandvars(str(path or "").strip().strip('"'))
    if value and _drive_available(value):
        return value
    return get_default_downloads_folder()


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

