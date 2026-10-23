"""File categorization module for HDM.
Categorizes downloads based on file extensions.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Dict, Set


class FileCategory(str, Enum):
    ALL = "Tất cả"
    COMPRESSED = "Nén"
    PROGRAMS = "Phần mềm"
    VIDEO = "Video"
    AUDIO = "Âm nhạc"
    DOCUMENTS = "Tài liệu"
    IMAGES = "Hình ảnh"
    OTHERS = "Khác"


CATEGORY_EXTENSIONS: Dict[FileCategory, Set[str]] = {
    FileCategory.COMPRESSED: {
        "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "zst", "iso", "img",
        "cab", "tgz", "tbz2", "lz", "lzma", "lzh", "arj", "dmg"
    },
    FileCategory.PROGRAMS: {
        "exe", "msi", "msix", "bat", "cmd", "ps1", "sh", "bin", "apk", "appx",
        "jar", "appimage", "run", "deb", "rpm", "pkg"
    },
    FileCategory.VIDEO: {
        "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "ts",
        "m3u8", "3gp", "vob", "ogv", "divx", "rmvb"
    },
    FileCategory.AUDIO: {
        "mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "aiff",
        "mid", "midi", "mka"
    },
    FileCategory.DOCUMENTS: {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf",
        "odt", "ods", "odp", "csv", "epub", "mobi", "md", "json", "xml"
    },
    FileCategory.IMAGES: {
        "jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "tiff",
        "tif", "raw", "psd", "ai"
    }
}


def get_category_for_filename(filename: str) -> FileCategory:
    """Determine the FileCategory based on filename extension."""
    if not filename:
        return FileCategory.OTHERS

    parts = filename.rsplit(".", 1)
    if len(parts) < 2:
        return FileCategory.OTHERS

    ext = parts[1].lower().strip()
    for category, ext_set in CATEGORY_EXTENSIONS.items():
        if ext in ext_set:
            return category

    return FileCategory.OTHERS


def get_category_subfolder(category: FileCategory, base_dir: str) -> str:
    """Get the target subfolder path for a given category under base_dir."""
    folder_names = {
        FileCategory.COMPRESSED: "Compressed",
        FileCategory.PROGRAMS: "Programs",
        FileCategory.VIDEO: "Video",
        FileCategory.AUDIO: "Audio",
        FileCategory.DOCUMENTS: "Documents",
        FileCategory.IMAGES: "Images",
        FileCategory.OTHERS: "Others",
    }
    subname = folder_names.get(category, "Others")
    return os.path.join(base_dir, subname)
