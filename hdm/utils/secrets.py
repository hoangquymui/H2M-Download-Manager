"""At-rest protection for secrets stored in the HDM config file.

Windows uses DPAPI (CryptProtectData) scoped to the current user, so a copied
config.json cannot be decrypted on another machine or account. Other platforms
fall back to a clearly marked base64 container for development only.
"""

from __future__ import annotations

import base64
import ctypes
import platform
from ctypes import wintypes

_ENCRYPTED_PREFIX = "dpapi:"
_PLAIN_PREFIX = "plain:"
_ENTROPY = b"HDM.site-credentials.v1"
_UI_FORBIDDEN = 0x1


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _crypt32():
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    return crypt32


def _local_free(pointer) -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.LocalFree(ctypes.cast(pointer, wintypes.HLOCAL))


def protect_secret(text: str) -> str:
    """Encrypt *text* for storage; raises RuntimeError when DPAPI fails."""
    if not text:
        return ""
    if platform.system() != "Windows":
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return _PLAIN_PREFIX + encoded

    data_in, _keep_in = _make_blob(text.encode("utf-8"))
    entropy, _keep_entropy = _make_blob(_ENTROPY)
    data_out = _DataBlob()
    ok = _crypt32().CryptProtectData(
        ctypes.byref(data_in),
        "HDM",
        ctypes.byref(entropy),
        None,
        None,
        _UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    if not ok:
        raise RuntimeError("CryptProtectData failed")
    try:
        payload = ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        _local_free(data_out.pbData)
    return _ENCRYPTED_PREFIX + base64.b64encode(payload).decode("ascii")


def unprotect_secret(token: str) -> str:
    """Decrypt a stored secret; returns "" when the token is unusable."""
    if not token:
        return ""
    if token.startswith(_ENCRYPTED_PREFIX):
        if platform.system() != "Windows":
            return ""
        try:
            payload = base64.b64decode(token[len(_ENCRYPTED_PREFIX):])
            data_in, _keep_in = _make_blob(payload)
            entropy, _keep_entropy = _make_blob(_ENTROPY)
            data_out = _DataBlob()
            ok = _crypt32().CryptUnprotectData(
                ctypes.byref(data_in),
                None,
                ctypes.byref(entropy),
                None,
                None,
                _UI_FORBIDDEN,
                ctypes.byref(data_out),
            )
            if not ok:
                return ""
            try:
                return ctypes.string_at(data_out.pbData, data_out.cbData).decode("utf-8")
            finally:
                _local_free(data_out.pbData)
        except (OSError, ValueError):
            return ""
    if token.startswith(_PLAIN_PREFIX):
        try:
            return base64.b64decode(token[len(_PLAIN_PREFIX):]).decode("utf-8")
        except ValueError:
            return ""
    return ""
