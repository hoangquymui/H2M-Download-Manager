"""Configuration management for HDM.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

from hdm.utils.i18n import normalize_language, set_language
from hdm.utils.system import get_app_data_folder, get_default_downloads_folder


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class Config:
    default_save_dir: str = field(default_factory=get_default_downloads_folder)
    auto_categorize: bool = False
    max_concurrent_tasks: int = 3
    default_connections: int = 8
    min_chunk_size: int = 1048576       # 1 MB
    min_steal_size: int = 2097152       # 2 MB minimum to split in half
    server_enabled: bool = True
    server_port: int = 9618
    auto_start: bool = True
    user_agent: str = DEFAULT_USER_AGENT
    theme: str = "dark"
    language: str = "vi"                # "vi" or "en"
    start_with_windows: bool = False    # Auto-start with Windows on boot
    show_download_dialog: bool = True   # Show IDM-style confirmation modal on link capture
    speed_limit_kbps: int = 0           # 0 = unlimited
    category_extensions: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """Manages loading and saving application configuration."""
    def __init__(self) -> None:
        self.config_dir = get_app_data_folder()
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = self.load()

    def load(self) -> Config:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg = Config.from_dict(data)
                    set_language(cfg.language)
                    from hdm.utils.category import set_custom_category_extensions
                    set_custom_category_extensions(cfg.category_extensions)
                    return cfg
            except Exception:
                pass
        config = Config()
        set_language(config.language)
        from hdm.utils.category import set_custom_category_extensions
        set_custom_category_extensions(config.category_extensions)
        self.save(config)
        return config

    def save(self, config: Config | None = None) -> None:
        if config is not None:
            self.config = config
        set_language(self.config.language)
        try:
            from hdm.utils.category import set_custom_category_extensions
            set_custom_category_extensions(self.config.category_extensions)
        except Exception:
            pass
        try:
            from hdm.utils.system import set_autostart
            set_autostart(self.config.start_with_windows)
        except Exception:
            pass
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass
