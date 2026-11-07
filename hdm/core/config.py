"""Configuration management for HDM.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict
from urllib.parse import urlparse

from hdm.utils.i18n import normalize_language, set_language
from hdm.utils.site_auth import sanitize_site_credentials
from hdm.utils.system import get_app_data_folder, get_default_downloads_folder, resolve_download_dir


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

PROXY_SCHEMES = ("http", "https", "socks4", "socks5", "socks5h")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def normalize_schedule_time(value: str) -> str:
    """Validate an "HH:MM" clock value; "" means "no bound"."""
    text = (value or "").strip()
    if not text:
        return ""
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"Invalid time: {value}")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def normalize_proxy_url(value: str) -> str:
    """Validate a proxy address; returns "" for a direct connection.

    Accepts "host:port" (assumed HTTP) plus http/https/socks4/socks5(s)
    URLs, optionally with credentials. Raises ValueError when unusable.
    """
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"http://{text}"
    try:
        parsed = urlparse(text)
        parsed.port  # noqa: B018 - forces the lazy port validation
    except ValueError as e:
        raise ValueError(f"Invalid proxy address: {e}") from e
    if parsed.scheme.lower() not in PROXY_SCHEMES:
        raise ValueError(f"Unsupported proxy scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("Proxy host is missing")
    return text


@dataclass
class Config:
    default_save_dir: str = field(default_factory=get_default_downloads_folder)
    auto_categorize: bool = False
    max_concurrent_tasks: int = 3
    default_connections: int = 8
    min_chunk_size: int = 1048576       # 1 MB
    server_enabled: bool = True
    server_port: int = 9618
    auto_start: bool = True
    user_agent: str = DEFAULT_USER_AGENT
    theme: str = "dark"
    language: str = "vi"                # "vi" or "en"
    start_with_windows: bool = False    # Auto-start with Windows on boot
    show_download_dialog: bool = True   # Show IDM-style confirmation modal on link capture
    show_extension_guide: bool = True   # Show the extension install guide on startup
    speed_limit_kbps: int = 0           # 0 = unlimited
    proxy_url: str = ""                 # "" = direct connection
    schedule_enabled: bool = False      # Only download inside the daily window
    schedule_start: str = ""            # "HH:MM", "" = no start bound
    schedule_stop: str = ""             # "HH:MM", "" = no stop bound
    site_credentials: Dict[str, Dict[str, str]] = field(default_factory=dict)
    category_extensions: Dict[str, str] = field(default_factory=dict)
    category_folders: Dict[str, str] = field(default_factory=dict)

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
                    # A config copied from another machine may point at a drive
                    # that does not exist here; never keep an unusable save dir.
                    cfg.default_save_dir = resolve_download_dir(cfg.default_save_dir)
                    try:
                        cfg.proxy_url = normalize_proxy_url(cfg.proxy_url)
                    except ValueError:
                        cfg.proxy_url = ""
                    for attr in ("schedule_start", "schedule_stop"):
                        try:
                            setattr(cfg, attr, normalize_schedule_time(getattr(cfg, attr)))
                        except ValueError:
                            setattr(cfg, attr, "")
                    cfg.site_credentials = sanitize_site_credentials(cfg.site_credentials)
                    set_language(cfg.language)
                    from hdm.utils.category import set_custom_category_extensions, set_custom_category_folders
                    set_custom_category_extensions(cfg.category_extensions)
                    set_custom_category_folders(cfg.category_folders)
                    return cfg
            except Exception:
                pass
        config = Config()
        set_language(config.language)
        from hdm.utils.category import set_custom_category_extensions, set_custom_category_folders
        set_custom_category_extensions(config.category_extensions)
        set_custom_category_folders(config.category_folders)
        self.save(config)
        return config

    def save(self, config: Config | None = None) -> None:
        if config is not None:
            self.config = config
        self.config.default_save_dir = resolve_download_dir(self.config.default_save_dir)
        try:
            self.config.proxy_url = normalize_proxy_url(self.config.proxy_url)
        except ValueError:
            pass
        for attr in ("schedule_start", "schedule_stop"):
            try:
                setattr(self.config, attr, normalize_schedule_time(getattr(self.config, attr)))
            except ValueError:
                pass
        self.config.site_credentials = sanitize_site_credentials(self.config.site_credentials)
        set_language(self.config.language)
        try:
            from hdm.utils.category import set_custom_category_extensions, set_custom_category_folders
            set_custom_category_extensions(self.config.category_extensions)
            set_custom_category_folders(self.config.category_folders)
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
