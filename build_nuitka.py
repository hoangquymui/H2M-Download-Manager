"""Build HDM as a Nuitka standalone distribution (compiled C, instant start).

The result in `dist/HDM` is a self-contained folder: HDM.exe, Qt runtime,
yt-dlp/ejs data, ffmpeg and the browser extension folders beside the exe.
Nuitka compiles the Python sources to C, so no .py/.pyc files are shipped.

Usage:
    python build_nuitka.py                  # MSVC when available, else MinGW64
    python build_nuitka.py --compiler=mingw64
    python build_nuitka.py --compiler=msvc
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(ROOT_DIR, "build", "nuitka")
DIST_DIR = os.path.join(ROOT_DIR, "dist")
APP_DIR = os.path.join(DIST_DIR, "HDM")
ICON_PATH = os.path.join(ROOT_DIR, "app.ico")
ENTRY_POINT = os.path.join(ROOT_DIR, "main.py")


def read_version() -> str:
    with open(os.path.join(ROOT_DIR, "hdm", "__init__.py"), encoding="utf-8") as f:
        match = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
    if not match:
        raise RuntimeError("Không tìm thấy __version__ trong hdm/__init__.py")
    return match.group(1)


def detect_compiler() -> str:
    """Prefer MSVC; fall back to MinGW64 (Nuitka downloads it on demand)."""
    if shutil.which("cl"):
        return "msvc"
    vswhere = os.path.join(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        "Microsoft Visual Studio", "Installer", "vswhere.exe",
    )
    if os.path.exists(vswhere):
        return "msvc"
    return "mingw64"


def nuitka_command(compiler: str, version: str) -> list:
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICON_PATH}",
        # get_app_icon() also looks for app.ico beside the executable.
        "--include-data-files=app.ico=app.ico",
        # yt-dlp resolves extractors at runtime by module name.
        "--include-package=yt_dlp",
        "--include-package-data=yt_dlp",
        "--include-package=yt_dlp_ejs",
        "--include-package-data=yt_dlp_ejs",
        "--include-package-data=imageio_ffmpeg",
        "--include-package-data=certifi",
        # yt-dlp probes installed distributions (notably yt-dlp-ejs) by metadata.
        "--include-distribution-metadata=yt-dlp",
        "--include-distribution-metadata=yt-dlp-ejs",
        f"--output-dir={BUILD_DIR}",
        "--output-filename=HDM.exe",
        "--company-name=H2M Team",
        "--product-name=HDM",
        "--file-description=HDM - H2M Download Manager",
        f"--file-version={version}.0",
        f"--product-version={version}.0",
        "--msvc=latest" if compiler == "msvc" else "--mingw64",
        ENTRY_POINT,
    ]
    return cmd


def copy_tree(src: str, dst: str) -> None:
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def folder_size(path: str) -> int:
    total = 0
    for current, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(current, name))
            except OSError:
                pass
    return total


def stage_distribution(version: str) -> None:
    """Copy the compiled folder to dist/HDM and add extension folders."""
    source = os.path.join(BUILD_DIR, "main.dist")
    exe = os.path.join(source, "HDM.exe")
    if not os.path.exists(exe):
        raise RuntimeError(f"Không thấy HDM.exe trong {source}")

    copy_tree(source, APP_DIR)
    print(f"  Standalone: {APP_DIR}")

    import build_extension
    for target in ("chrome", "firefox"):
        build_extension.build(target)

    copy_tree(os.path.join(DIST_DIR, "extension-chrome"), os.path.join(APP_DIR, "extension"))
    copy_tree(os.path.join(DIST_DIR, "extension-firefox"), os.path.join(APP_DIR, "extension-firefox"))
    print("  Extension (Chromium): extension/")
    print("  Extension (Firefox):  extension-firefox/")

    if not os.path.exists(os.path.join(APP_DIR, "app.ico")):
        shutil.copy2(ICON_PATH, os.path.join(APP_DIR, "app.ico"))

    size_mb = folder_size(APP_DIR) / (1024 * 1024)
    print(f"  Kích thước thư mục: {size_mb:.1f} MB")
    print(f"  Phiên bản: {version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HDM with Nuitka (standalone).")
    parser.add_argument("--compiler", choices=("auto", "msvc", "mingw64"), default="auto")
    args = parser.parse_args()

    version = read_version()
    compiler = detect_compiler() if args.compiler == "auto" else args.compiler
    cmd = nuitka_command(compiler, version)

    print("=" * 60)
    print("   HDM — Nuitka Standalone Builder")
    print("=" * 60)
    print(f" Compiler: {compiler}")
    print(f" Version:  {version}")
    print(" Lần build đầu có thể mất 30-60 phút (biên dịch C toàn bộ).")
    print("=" * 60)

    os.makedirs(BUILD_DIR, exist_ok=True)
    started = time.time()
    result = subprocess.run(cmd, cwd=ROOT_DIR)
    if result.returncode != 0:
        sys.exit(result.returncode)

    elapsed = time.time() - started
    print(f"\nBiên dịch xong sau {elapsed / 60:.1f} phút.")
    stage_distribution(version)


if __name__ == "__main__":
    main()
