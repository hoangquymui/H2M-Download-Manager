"""Utility functions for formatting data and string manipulations.
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
from typing import Optional


def format_bytes(size_bytes: int | float | None) -> str:
    """Format bytes into human-readable string (B, KB, MB, GB, TB)."""
    if size_bytes is None or size_bytes < 0:
        return "Không rõ"
    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[unit_index]}"


def format_speed(bytes_per_sec: float | None) -> str:
    """Format download speed in bytes/sec into KB/s or MB/s."""
    if bytes_per_sec is None or bytes_per_sec <= 0:
        return "0 KB/s"
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    if bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"


def format_eta(seconds: float | None) -> str:
    """Format Estimated Time of Arrival (ETA) in seconds into human-readable time."""
    if seconds is None or seconds < 0 or seconds > 86400 * 30:  # > 30 days or infinite
        return "Không xác định"
    if seconds == 0:
        return "0s"

    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {rem_secs}s"
    return f"{rem_secs}s"


def format_date(timestamp: float | None) -> str:
    """Format unix timestamp into local date string."""
    if not timestamp:
        return ""
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(timestamp))


def clean_filename(filename: str) -> str:
    """Remove illegal characters for Windows and Unix filesystems."""
    if not filename:
        return "download"

    # Replace forbidden Windows characters: < > : " / \ | ? * and control chars
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    cleaned = cleaned.strip('. ')

    # Reserved Windows device names
    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }
    stem, ext = os.path.splitext(cleaned)
    if stem.upper() in reserved_names:
        cleaned = f"_{cleaned}"

    return cleaned if cleaned else "download"


def extract_filename_from_url(url: str, content_disposition: Optional[str] = None) -> str:
    """Extract and decode appropriate filename from Content-Disposition header or URL."""
    # 1. Try parsing Content-Disposition header if available
    if content_disposition:
        # Match RFC 5987 / RFC 6266 utf-8''filename.ext
        match_utf8 = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", content_disposition, re.IGNORECASE)
        if match_utf8:
            try:
                candidate = urllib.parse.unquote(match_utf8.group(1).strip().strip('"\''))
                if candidate:
                    return clean_filename(candidate)
            except Exception:
                pass

        # Match standard filename="example.zip" or filename=example.zip
        match_std = re.search(r'filename\s*=\s*("([^"]+)"|([^;\s]+))', content_disposition, re.IGNORECASE)
        if match_std:
            candidate = match_std.group(2) or match_std.group(3)
            if candidate:
                candidate = urllib.parse.unquote(candidate.strip().strip('"\''))
                return clean_filename(candidate)

    # 2. Extract from URL pathname
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if path:
            basename = os.path.basename(path.rstrip('/'))
            if basename:
                decoded = urllib.parse.unquote(basename)
                cleaned = clean_filename(decoded)
                if cleaned and cleaned != "download":
                    return cleaned
    except Exception:
        pass

    return "download"
