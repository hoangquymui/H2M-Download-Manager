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


def get_unique_filename(save_dir: str, filename: str) -> str:
    """Return a non-conflicting filename in save_dir by appending ' (1)', ' (2)', etc. if needed."""
    cleaned = clean_filename(filename)
    if not save_dir or not os.path.isdir(save_dir):
        return cleaned

    full_path = os.path.join(save_dir, cleaned)
    part_path = f"{full_path}.hdm_part"
    if not os.path.exists(full_path) and not os.path.exists(part_path):
        return cleaned

    stem, ext = os.path.splitext(cleaned)
    # Strip trailing ' (N)' if already numbered so we increment cleanly
    stem = re.sub(r"\s*\(\d+\)$", "", stem)
    counter = 1
    while True:
        candidate = f"{stem} ({counter}){ext}"
        cand_full = os.path.join(save_dir, candidate)
        cand_part = f"{cand_full}.hdm_part"
        if not os.path.exists(cand_full) and not os.path.exists(cand_part):
            return candidate
        counter += 1


def _disposition_filename(content_disposition: str) -> str:
    """Extract the filename value from a Content-Disposition header string."""
    # RFC 5987 / RFC 6266: filename*=UTF-8''file.ext
    match_utf8 = re.search(
        r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", content_disposition, re.IGNORECASE
    )
    if match_utf8:
        try:
            candidate = urllib.parse.unquote(match_utf8.group(1).strip().strip('"\''))
            if candidate:
                return clean_filename(candidate)
        except Exception:
            pass

    match_std = re.search(
        r'filename\s*=\s*("([^"]+)"|([^;\s]+))', content_disposition, re.IGNORECASE
    )
    if match_std:
        candidate = match_std.group(2) or match_std.group(3)
        if candidate:
            candidate = urllib.parse.unquote(candidate.strip().strip('"\''))
            return clean_filename(candidate)
    return ""


def _has_extension(filename: str) -> bool:
    ext = os.path.splitext(filename or "")[1].lstrip(".")
    # A real extension is alphanumeric and contains a letter ("7z", "mp4"),
    # which rules out version tails such as ".1" or ".2407".
    return 1 < len(ext) <= 12 and ext.isalnum() and any(ch.isalpha() for ch in ext)


def extract_filename_from_url(url: str, content_disposition: Optional[str] = None) -> str:
    """Extract and decode appropriate filename from Content-Disposition header or URL.

    Signed CDN URLs often carry an opaque UUID as the Content-Disposition
    filename while the real name lives in the URL (path or the
    ``response-content-disposition`` query of S3/Azure/GCS links). Prefer
    whichever candidate actually has a file extension.
    """
    disposition_name = _disposition_filename(content_disposition) if content_disposition else ""
    if disposition_name and _has_extension(disposition_name):
        return disposition_name

    url_name = ""
    query_disposition_name = ""
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if path:
            basename = os.path.basename(path.rstrip('/'))
            if basename:
                decoded = urllib.parse.unquote(basename)
                cleaned = clean_filename(decoded)
                if cleaned and cleaned != "download":
                    url_name = cleaned

        # Signed object-storage links put the real name in a query parameter.
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("response-content-disposition", "content-disposition"):
            for value in query.get(key, []):
                candidate = _disposition_filename(value)
                if candidate:
                    query_disposition_name = candidate
                    break
            if query_disposition_name:
                break
        if not query_disposition_name:
            for value in query.get("filename", []):
                if value.strip():
                    query_disposition_name = clean_filename(urllib.parse.unquote(value.strip()))
                    break
    except Exception:
        pass

    for candidate in (url_name, query_disposition_name):
        if candidate and _has_extension(candidate):
            return candidate

    return disposition_name or url_name or query_disposition_name or "download"
