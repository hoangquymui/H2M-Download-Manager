"""Package the HDM browser extension for Chromium browsers and Firefox.

Chromium browsers (Chrome, Edge, Cốc Cốc, Brave) load `extension/` directly.
Firefox has no MV3 service workers and needs a Gecko ID, so it gets a
generated copy with a rewritten manifest.

Usage:
    python build_extension.py              # both browsers
    python build_extension.py firefox      # Firefox only
    python build_extension.py chrome       # Chromium bundle only (store zip)
"""

import json
import os
import shutil
import sys
import zipfile

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "extension")
OUT_DIR = os.path.join(ROOT_DIR, "dist")

GECKO_ID = "hdm@h2m.team"
# world: "MAIN" content scripts require Firefox 128.
FIREFOX_MIN_VERSION = "128.0"


def load_manifest() -> dict:
    with open(os.path.join(SRC_DIR, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def firefox_manifest(base: dict) -> dict:
    manifest = dict(base)
    manifest.pop("minimum_chrome_version", None)
    # Firefox runs MV3 backgrounds as event pages, not service workers; the
    # same background.js works for both.
    manifest["background"] = {"scripts": ["background.js"]}
    manifest["browser_specific_settings"] = {
        "gecko": {
            "id": GECKO_ID,
            "strict_min_version": FIREFOX_MIN_VERSION,
            # Required for new AMO submissions: HDM only talks to localhost.
            "data_collection_permissions": {"required": ["none"]},
        }
    }
    return manifest


def zip_dir(folder: str, zip_path: str) -> None:
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for current, _, files in os.walk(folder):
            for name in files:
                full = os.path.join(current, name)
                zf.write(full, os.path.relpath(full, folder).replace(os.sep, "/"))


def build(target: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    out_dir = os.path.join(OUT_DIR, f"extension-{target}")
    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(SRC_DIR, out_dir)

    manifest = load_manifest()
    if target == "firefox":
        manifest = firefox_manifest(manifest)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    zip_path = os.path.join(OUT_DIR, f"HDM-extension-{target}.zip")
    zip_dir(out_dir, zip_path)

    print(f"[{target}] folder: {out_dir}")
    print(f"[{target}] zip:    {zip_path}")


def main() -> None:
    targets = sys.argv[1:] or ["chrome", "firefox"]
    unknown = [t for t in targets if t not in ("chrome", "firefox")]
    if unknown:
        print(f"Unknown target(s): {', '.join(unknown)}")
        sys.exit(2)
    os.makedirs(OUT_DIR, exist_ok=True)
    for target in targets:
        build(target)


if __name__ == "__main__":
    main()
