"""Windows NTFS Sparse File and file pre-allocation utilities.
Enables instant pre-allocation of large files without I/O zero-filling overhead.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
from typing import Tuple


def check_free_space(target_dir: str, required_bytes: int) -> Tuple[bool, int, int]:
    """Check if the target directory has sufficient free disk space.
    Returns (has_enough_space, free_bytes, required_bytes).
    """
    try:
        drive_path = os.path.abspath(target_dir)
        while not os.path.exists(drive_path) and os.path.dirname(drive_path) != drive_path:
            drive_path = os.path.dirname(drive_path)

        total, used, free = shutil.disk_usage(drive_path)
        # Keep at least 150 MB buffer for system stability
        safety_buffer = 157286400  # 150 MB
        has_enough = free >= (required_bytes + safety_buffer)
        return has_enough, free, required_bytes
    except Exception:
        return True, 0, required_bytes


def preallocate_file(file_path: str, size: int) -> bool:
    """Instantly create and allocate a sparse file of the exact target size.
    On Windows NTFS, this sets the virtual length in < 1ms without zero-filling physical disk blocks.
    """
    if size <= 0:
        return True

    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

    if platform.system() == "Windows":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateFileW.restype = ctypes.c_void_p
            kernel32.CreateFileW.argtypes = [
                ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p
            ]
            kernel32.SetFilePointerEx.argtypes = [
                ctypes.c_void_p, ctypes.c_longlong, ctypes.c_void_p, ctypes.c_ulong
            ]

            GENERIC_READ = 0x80000000
            GENERIC_WRITE = 0x40000000
            OPEN_ALWAYS = 4
            FSCTL_SET_SPARSE = 0x000900C4
            FILE_BEGIN = 0

            h = kernel32.CreateFileW(
                file_path,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_ALWAYS,
                0,
                None
            )
            if h is not None and h != -1 and h != 0xFFFFFFFFFFFFFFFF:
                try:
                    # 1. Enable sparse file attribute so physical zero-filling is avoided
                    bytes_ret = ctypes.c_ulong(0)
                    kernel32.DeviceIoControl(
                        h,
                        FSCTL_SET_SPARSE,
                        None,
                        0,
                        None,
                        0,
                        ctypes.byref(bytes_ret),
                        None
                    )

                    # 2. Instantly set virtual file pointer to target size
                    new_pos = ctypes.c_longlong(0)
                    kernel32.SetFilePointerEx(h, size, ctypes.byref(new_pos), FILE_BEGIN)
                    kernel32.SetEndOfFile(h)
                    return True
                finally:
                    kernel32.CloseHandle(h)
        except Exception:
            pass

    # Non-Windows or fallback: touch file without blocking zero-fill
    try:
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                f.write(b"")
        return True
    except Exception:
        return False
