"""Compile the standalone HDM folder into a single installer with Inno Setup.

Prerequisite: `python build_nuitka.py` has produced dist/HDM/HDM.exe, and
Inno Setup 6 is installed (ISCC.exe on PATH or in Program Files).

Usage:
    python build_installer.py
    python build_installer.py --iscc "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT_DIR, "dist")
APP_DIR = os.path.join(DIST_DIR, "HDM")
ISS_PATH = os.path.join(ROOT_DIR, "installer", "HDM.iss")


def read_version() -> str:
    with open(os.path.join(ROOT_DIR, "hdm", "__init__.py"), encoding="utf-8") as f:
        match = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
    if not match:
        raise RuntimeError("Không tìm thấy __version__ trong hdm/__init__.py")
    return match.group(1)


def find_iscc(explicit: str = "") -> str:
    if explicit:
        return explicit
    found = shutil.which("iscc")
    if found:
        return found
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 5", "ISCC.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise RuntimeError(
        "Không tìm thấy ISCC.exe. Cài Inno Setup 6 (https://jrsoftware.org/isdl.php) "
        "hoặc truyền --iscc đường_dẫn_ISCC.exe"
    )


def ensure_extension_folders() -> None:
    import build_extension
    for target in ("chrome", "firefox"):
        folder = os.path.join(DIST_DIR, f"extension-{target}")
        if not os.path.exists(folder):
            build_extension.build(target)
    for src, dst in (
        (os.path.join(DIST_DIR, "extension-chrome"), os.path.join(APP_DIR, "extension")),
        (os.path.join(DIST_DIR, "extension-firefox"), os.path.join(APP_DIR, "extension-firefox")),
    ):
        if not os.path.exists(dst):
            shutil.copytree(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HDM installer with Inno Setup.")
    parser.add_argument("--iscc", default="", help="Đường dẫn tới ISCC.exe")
    args = parser.parse_args()

    version = read_version()
    if not os.path.exists(os.path.join(APP_DIR, "HDM.exe")):
        raise SystemExit(
            "Chưa có dist/HDM/HDM.exe. Chạy `python build_nuitka.py` trước."
        )
    ensure_extension_folders()
    iscc = find_iscc(args.iscc)

    print("=" * 60)
    print("   HDM — Inno Setup Installer Builder")
    print("=" * 60)
    print(f" ISCC:    {iscc}")
    print(f" Version: {version}")
    print("=" * 60)

    result = subprocess.run(
        [iscc, f"/DMyAppVersion={version}", ISS_PATH],
        cwd=ROOT_DIR,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)

    setup_path = os.path.join(DIST_DIR, f"HDM_Setup_v{version}.exe")
    if not os.path.exists(setup_path):
        raise SystemExit(f"ISCC báo thành công nhưng không thấy {setup_path}")
    size_mb = os.path.getsize(setup_path) / (1024 * 1024)
    print(f"\n[OK] Installer: {setup_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
