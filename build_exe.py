"""Build script to compile HDM into a standalone Windows executable using PyInstaller.
"""

import os
import shutil
import subprocess
import sys


def build():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(root_dir, "main.py")
    ico_path = os.path.join(root_dir, "app.ico")
    dist_dir = os.path.join(root_dir, "dist")
    build_dir = os.path.join(root_dir, "build")

    print("=" * 60)
    print("   HDM (H2M Download Manager) — Windows Executable Builder")
    print("=" * 60)

    # Clean previous builds
    for d in (dist_dir, build_dir):
        if os.path.exists(d):
            print(f"Cleaning {d}...")
            shutil.rmtree(d, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=HDM",
        "--noconsole",
        "--onedir",  # onedir is faster to launch and avoids temp unpack latency
        f"--icon={ico_path}",
        f"--add-data={ico_path};.",
        "--clean",
        "--noconfirm",
        main_py,
    ]

    print("\nRunning PyInstaller command:")
    print(" ".join(cmd))
    print("\nCompiling... (this may take a few moments)\n")

    result = subprocess.run(cmd, cwd=root_dir)

    if result.returncode == 0:
        exe_path = os.path.join(dist_dir, "HDM", "HDM.exe")
        ext_src = os.path.join(root_dir, "extension")
        ext_dst = os.path.join(dist_dir, "HDM", "extension")
        if os.path.exists(ext_src):
            shutil.copytree(ext_src, ext_dst, dirs_exist_ok=True)
            print(f" Extension copied: {ext_dst}")
        print("\n" + "=" * 60)
        print(" [SUCCESS] HDM has been successfully built!")
        print(f" Output folder: {os.path.join(dist_dir, 'HDM')}")
        print(f" Executable:    {exe_path}")
        print("=" * 60)
    else:
        print(f"\n[ERROR] Build failed with code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
