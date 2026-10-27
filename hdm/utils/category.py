"""File categorization module for HDM.
Categorizes downloads based on file extensions and manages category subfolders.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict, List, Set


class FileCategory(str, Enum):
    ALL = "Tất cả"
    VIDEO = "Video"
    AUDIO = "Nhạc"
    COMPRESSED = "Tệp nén"
    DOCUMENTS = "Tài liệu"
    PROGRAMS = "Chương trình"
    IMAGES = "Hình ảnh"
    OTHERS = "Khác"


CATEGORY_CONFIG_SPECS: List[Dict[str, Any]] = [
    {
        "key": "Video",
        "category": FileCategory.VIDEO,
        "default_folder": "Video",
        "icon": "🎬",
        "name_vi": "Video",
        "name_en": "Video",
        "default": "mp4 mkv avi mov wmv flv webm m4v mpg mpeg 3gp ts m2ts vob",
    },
    {
        "key": "Music",
        "category": FileCategory.AUDIO,
        "default_folder": "Music",
        "icon": "🎵",
        "name_vi": "Nhạc",
        "name_en": "Music",
        "default": "mp3 m4a flac wav aac ogg wma opus ape alac",
    },
    {
        "key": "Compressed",
        "category": FileCategory.COMPRESSED,
        "default_folder": "Compressed",
        "icon": "📦",
        "name_vi": "Tệp nén",
        "name_en": "Compressed",
        "default": "zip rar 7z gz tar bz2 xz tgz iso img cab zst",
    },
    {
        "key": "Documents",
        "category": FileCategory.DOCUMENTS,
        "default_folder": "Documents",
        "icon": "📄",
        "name_vi": "Tài liệu",
        "name_en": "Documents",
        "default": "pdf doc docx xls xlsx ppt pptx txt rtf odt ods odp epub csv",
    },
    {
        "key": "Programs",
        "category": FileCategory.PROGRAMS,
        "default_folder": "Programs",
        "icon": "💻",
        "name_vi": "Chương trình",
        "name_en": "Programs",
        "default": "exe msi apk dmg bin appx msix xapk jar deb rpm",
    },
    {
        "key": "Pictures",
        "category": FileCategory.IMAGES,
        "default_folder": "Pictures",
        "icon": "🖼️",
        "name_vi": "Hình ảnh",
        "name_en": "Pictures",
        "default": "jpg jpeg png gif bmp webp tif tiff svg psd heic",
    },
    {
        "key": "Other",
        "category": FileCategory.OTHERS,
        "default_folder": "Other",
        "icon": "📂",
        "name_vi": "Khác",
        "name_en": "Other",
        "default": "",
    },
]

DEFAULT_CATEGORY_FOLDERS: Dict[str, str] = {
    str(spec["key"]): str(spec["default_folder"]) for spec in CATEGORY_CONFIG_SPECS
}

DEFAULT_CATEGORY_EXTENSIONS: Dict[str, str] = {
    str(spec["key"]): str(spec["default"]) for spec in CATEGORY_CONFIG_SPECS
}


def parse_extensions_string(ext_str: str) -> Set[str]:
    """Parse comma/space/semicolon separated extension list into normalized set."""
    if not ext_str:
        return set()
    cleaned = ext_str.replace(";", " ").replace(",", " ")
    result = set()
    for item in cleaned.split():
        ext = item.strip().lower().lstrip(".")
        if ext:
            result.add(ext)
    return result


def normalize_extension_string(ext_str: str) -> str:
    """Normalize extension string into a sorted space-separated string."""
    parts = parse_extensions_string(ext_str)
    return " ".join(sorted(parts))


CATEGORY_EXTENSIONS: Dict[FileCategory, Set[str]] = {
    spec["category"]: parse_extensions_string(spec["default"])
    for spec in CATEGORY_CONFIG_SPECS
}

CATEGORY_FOLDERS: Dict[FileCategory, str] = {
    spec["category"]: str(spec["default_folder"])
    for spec in CATEGORY_CONFIG_SPECS
}

# Backward compatibility alias
CATEGORY_TO_FOLDER: Dict[FileCategory, str] = CATEGORY_FOLDERS


def set_custom_category_folders(custom_map: Dict[str, str] | None = None) -> None:
    """Update active CATEGORY_FOLDERS based on custom folder mappings."""
    custom_map = custom_map or {}
    for spec in CATEGORY_CONFIG_SPECS:
        key = str(spec["key"])
        cat: FileCategory = spec["category"]
        folder = (
            custom_map.get(key)
            or custom_map.get(cat.value)
            or custom_map.get(key.lower())
            or (custom_map.get("Audio") if key == "Music" else None)
            or (custom_map.get("Âm nhạc") if key == "Music" else None)
            or (custom_map.get("Images") if key == "Pictures" else None)
            or (custom_map.get("Others") if key == "Other" else None)
            or spec["default_folder"]
        )
        CATEGORY_FOLDERS[cat] = str(folder).strip() or spec["default_folder"]


def get_category_folder_name(category: FileCategory) -> str:
    """Get the active folder name for a given category."""
    return CATEGORY_FOLDERS.get(category, "Other")


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
            or (custom_map.get("Audio") if key == "Music" else None)
            or (custom_map.get("Âm nhạc") if key == "Music" else None)
            or (custom_map.get("Images") if key == "Pictures" else None)
            or (custom_map.get("Others") if key == "Other" else None)
            or spec["default"]
        )
        CATEGORY_EXTENSIONS[cat] = parse_extensions_string(raw)


def get_active_category_extensions() -> Dict[str, str]:
    """Get active extensions mapped by category key."""
    result = {}
    for spec in CATEGORY_CONFIG_SPECS:
        key = str(spec["key"])
        cat: FileCategory = spec["category"]
        ext_set = CATEGORY_EXTENSIONS.get(cat, set())
        result[key] = " ".join(sorted(ext_set))
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
    subname = get_category_folder_name(category)
    return os.path.join(base_dir, subname)
