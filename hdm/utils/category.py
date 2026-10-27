"""File categorization module for HDM.
Categorizes downloads based on file extensions.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List, Set


class FileCategory(str, Enum):
    ALL = "Tất cả"
    COMPRESSED = "Nén"
    PROGRAMS = "Phần mềm"
    VIDEO = "Video"
    AUDIO = "Âm nhạc"
    DOCUMENTS = "Tài liệu"
    IMAGES = "Hình ảnh"
    OTHERS = "Khác"


CATEGORY_TO_FOLDER: Dict[FileCategory, str] = {
    FileCategory.COMPRESSED: "Compressed",
    FileCategory.PROGRAMS: "Programs",
    FileCategory.VIDEO: "Video",
    FileCategory.AUDIO: "Audio",
    FileCategory.DOCUMENTS: "Documents",
    FileCategory.IMAGES: "Images",
    FileCategory.OTHERS: "Others",
}

CATEGORY_CONFIG_SPECS: List[Dict[str, Any]] = [
    {
        "key": "Programs",
        "category": FileCategory.PROGRAMS,
        "folder": "Programs",
        "icon": "💻",
        "name_vi": "Phần mềm",
        "name_en": "Programs",
        "default": "exe, msi, msix, bat, cmd, ps1, sh, bin, apk, appx, jar, appimage, run, deb, rpm, pkg",
    },
    {
        "key": "Video",
        "category": FileCategory.VIDEO,
        "folder": "Video",
        "icon": "🎬",
        "name_vi": "Video",
        "name_en": "Video",
        "default": "mp4, mkv, avi, mov, wmv, flv, webm, m4v, ts, m3u8, 3gp, vob, ogv, divx, rmvb",
    },
    {
        "key": "Audio",
        "category": FileCategory.AUDIO,
        "folder": "Audio",
        "icon": "🎵",
        "name_vi": "Âm nhạc",
        "name_en": "Audio",
        "default": "mp3, wav, flac, aac, ogg, m4a, wma, opus, aiff, mid, midi, mka",
    },
    {
        "key": "Compressed",
        "category": FileCategory.COMPRESSED,
        "folder": "Compressed",
        "icon": "📦",
        "name_vi": "Tập tin nén",
        "name_en": "Compressed",
        "default": "zip, rar, 7z, tar, gz, bz2, xz, zst, iso, img, cab, tgz, tbz2, lz, lzma, lzh, arj, dmg",
    },
    {
        "key": "Documents",
        "category": FileCategory.DOCUMENTS,
        "folder": "Documents",
        "icon": "📄",
        "name_vi": "Tài liệu",
        "name_en": "Documents",
        "default": "pdf, doc, docx, xls, xlsx, ppt, pptx, txt, rtf, odt, ods, odp, csv, epub, mobi, md, json, xml",
    },
    {
        "key": "Images",
        "category": FileCategory.IMAGES,
        "folder": "Images",
        "icon": "🖼️",
        "name_vi": "Hình ảnh",
        "name_en": "Images",
        "default": "jpg, jpeg, png, gif, bmp, webp, svg, ico, tiff, tif, raw, psd, ai",
    },
]

DEFAULT_CATEGORY_EXTENSIONS: Dict[str, str] = {
    str(spec["key"]): str(spec["default"]) for spec in CATEGORY_CONFIG_SPECS
}


def parse_extensions_string(ext_str: str) -> Set[str]:
    """Parse comma/space/semicolon separated extension list into normalized set."""
    if not ext_str:
        return set()
    cleaned = ext_str.replace(";", ",").replace(" ", ",")
    result = set()
    for item in cleaned.split(","):
        ext = item.strip().lower().lstrip(".")
        if ext:
            result.add(ext)
    return result


def normalize_extension_string(ext_str: str) -> str:
    """Normalize extension string into a sorted comma-separated string."""
    parts = parse_extensions_string(ext_str)
    return ", ".join(sorted(parts))


CATEGORY_EXTENSIONS: Dict[FileCategory, Set[str]] = {
    spec["category"]: parse_extensions_string(spec["default"])
    for spec in CATEGORY_CONFIG_SPECS
}


def set_custom_category_extensions(custom_map: Dict[str, str] | None = None) -> None:
    """Update active CATEGORY_EXTENSIONS based on custom mappings."""
    custom_map = custom_map or {}
    for spec in CATEGORY_CONFIG_SPECS:
        key = str(spec["key"])
        cat: FileCategory = spec["category"]
        raw = (
            custom_map.get(key)
            or custom_map.get(cat.value)
            or custom_map.get(key.lower())
            or spec["default"]
        )
        CATEGORY_EXTENSIONS[cat] = parse_extensions_string(raw)


def get_active_category_extensions() -> Dict[str, str]:
    """Get active extensions mapped by folder key."""
    result = {}
    for spec in CATEGORY_CONFIG_SPECS:
        key = str(spec["key"])
        cat: FileCategory = spec["category"]
        ext_set = CATEGORY_EXTENSIONS.get(cat, set())
        result[key] = ", ".join(sorted(ext_set))
    return result


def get_category_for_filename(filename: str) -> FileCategory:
    """Determine the FileCategory based on filename extension."""
    if not filename:
        return FileCategory.OTHERS

    parts = filename.rsplit(".", 1)
    if len(parts) < 2:
        return FileCategory.OTHERS

    ext = parts[1].lower().strip()
    for spec in CATEGORY_CONFIG_SPECS:
        cat: FileCategory = spec["category"]
        ext_set = CATEGORY_EXTENSIONS.get(cat, set())
        if ext in ext_set:
            return cat

    return FileCategory.OTHERS


def get_category_subfolder(category: FileCategory, base_dir: str) -> str:
    """Get the target subfolder path for a given category under base_dir."""
    subname = CATEGORY_TO_FOLDER.get(category, "Others")
    return os.path.join(base_dir, subname)
