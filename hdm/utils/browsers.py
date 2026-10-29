"""Installed browser detection and HDM extension staging.

Chrome, Cốc Cốc and Firefox do not accept a local unpacked extension without
user clicks, so the dialog only detects browsers, copies the extension into
AppData and opens the browser's extension manager with a short guide.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List

from hdm.utils.system import get_app_data_folder, is_windows

DETACHED_PROCESS = 0x00000008 if os.name == "nt" else 0


@dataclass
class Browser:
    key: str
    name: str
    exe_path: str
    kind: str  # "chromium" | "firefox"
    user_data_dir: str = ""
    profiles_ini: str = ""
    management_page: str = "chrome://extensions"


@dataclass(frozen=True)
class _Candidate:
    key: str
    name: str
    exe_paths: tuple
    kind: str = "chromium"
    user_data: str = ""
    profiles_ini: str = ""
    management_page: str = "chrome://extensions"
    app_paths_entry: str = ""


def _env_path(value: str) -> str:
    return os.path.expandvars(value) if value else ""


def _known_locations() -> List["_Candidate"]:
    app_paths = "software\\Microsoft\\Windows\\CurrentVersion\\App Paths"
    return [
        _Candidate(
            "chrome", "Google Chrome",
            (
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
            ),
            user_data=r"%LocalAppData%\Google\Chrome\User Data",
            app_paths_entry=app_paths + "\\chrome.exe",
        ),
        _Candidate(
            "edge", "Microsoft Edge",
            (
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
            ),
            user_data=r"%LocalAppData%\Microsoft\Edge\User Data",
            management_page="edge://extensions",
            app_paths_entry=app_paths + "\\msedge.exe",
        ),
        _Candidate(
            "brave", "Brave",
            (
                r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
            ),
            user_data=r"%LocalAppData%\BraveSoftware\Brave-Browser\User Data",
            management_page="brave://extensions",
            app_paths_entry=app_paths + "\\brave.exe",
        ),
        _Candidate(
            "coccoc", "Cốc Cốc",
            (
                r"%ProgramFiles%\CocCoc\Browser\Application\browser.exe",
                r"%ProgramFiles(x86)%\CocCoc\Browser\Application\browser.exe",
                r"%LocalAppData%\CocCoc\Browser\Application\browser.exe",
            ),
            user_data=r"%LocalAppData%\CocCoc\Browser\User Data",
            management_page="coccoc://extensions",
        ),
        _Candidate(
            "vivaldi", "Vivaldi",
            (
                r"%LocalAppData%\Vivaldi\Application\vivaldi.exe",
                r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe",
            ),
            user_data=r"%LocalAppData%\Vivaldi\User Data",
            management_page="vivaldi://extensions",
            app_paths_entry=app_paths + "\\vivaldi.exe",
        ),
        _Candidate(
            "chromium", "Chromium",
            (r"%LocalAppData%\Chromium\Application\chrome.exe",),
            user_data=r"%LocalAppData%\Chromium\User Data",
        ),
        _Candidate(
            "firefox", "Mozilla Firefox",
            (
                r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
                r"%LocalAppData%\Mozilla Firefox\firefox.exe",
            ),
            kind="firefox",
            profiles_ini=r"%AppData%\Mozilla\Firefox\profiles.ini",
            management_page="about:debugging#/runtime/this-firefox",
            app_paths_entry=app_paths + "\\firefox.exe",
        ),
    ]


def _registry_app_path(entry: str) -> str:
    if not is_windows() or not entry:
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, entry, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "")
                    if value and os.path.exists(value):
                        return value
            except OSError:
                continue
    return ""


def detect_browsers() -> List[Browser]:
    """Return installed browsers that can host the HDM extension."""
    browsers: List[Browser] = []
    seen = set()
    for candidate in _known_locations():
        exe = ""
        for path in candidate.exe_paths:
            resolved = _env_path(path)
            if resolved and os.path.exists(resolved):
                exe = resolved
                break
        if not exe:
            exe = _registry_app_path(candidate.app_paths_entry)
        if not exe:
            continue
        data_dir = _env_path(candidate.user_data)
        # An empty/missing user data folder means the browser was never started.
        if candidate.kind == "chromium" and not os.path.isdir(data_dir):
            continue
        profiles_ini = _env_path(candidate.profiles_ini)
        if candidate.kind == "firefox" and not os.path.exists(profiles_ini):
            continue
        key = exe.lower()
        if key in seen:
            continue
        seen.add(key)
        browsers.append(
            Browser(
                key=candidate.key,
                name=candidate.name,
                exe_path=exe,
                kind=candidate.kind,
                user_data_dir=data_dir,
                profiles_ini=profiles_ini,
                management_page=candidate.management_page,
            )
        )
    return browsers


def bundled_extension_dir(kind: str = "chromium") -> str:
    """Extension folder shipped beside the app (source checkout or frozen build)."""
    folder = "extension-firefox" if kind == "firefox" else "extension"
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = (
        os.path.join(root, folder),
        os.path.abspath(os.path.join(root, "..", folder)),
        # Source checkout: build_extension.py writes the Firefox bundle to dist/.
        os.path.join(root, "dist", folder),
    )
    for candidate in candidates:
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "manifest.json")):
            return candidate
    return ""


def _manifest_version(folder: str) -> str:
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "")
    except (OSError, ValueError):
        return ""


def stage_extension(kind: str = "chromium") -> str:
    """Copy the extension into AppData so the loaded folder never moves."""
    source = bundled_extension_dir(kind)
    if not source:
        raise FileNotFoundError("Không tìm thấy thư mục extension đi kèm ứng dụng.")
    folder = "extension-firefox" if kind == "firefox" else "extension"
    target = os.path.join(get_app_data_folder(), folder)
    version = _manifest_version(source)
    if version and os.path.isdir(target) and _manifest_version(target) == version:
        return target
    staging = target + ".tmp"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(source, staging)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.replace(staging, target)
    return target


def _spawn(args: List[str]) -> None:
    subprocess.Popen(
        args,
        close_fds=True,
        creationflags=DETACHED_PROCESS,
    )


def launch_browser(browser: Browser) -> None:
    """Open the browser with its last used profile.

    Chrome and Edge drop ``chrome://`` URLs passed on the command line, so the
    caller copies the manager URL instead of navigating to it.
    """
    _spawn([browser.exe_path])
