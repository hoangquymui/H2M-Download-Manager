"""Per-site HTTP Basic credentials.

Patterns are host names, optionally with a leading "*." wildcard. Matching is
case-insensitive and ignores ports. Passwords are stored DPAPI-encrypted; this
module never writes plaintext back to the config.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from hdm.utils.secrets import unprotect_secret

_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def normalize_site_pattern(value: str) -> str:
    """Turn user input ("https://Example.com/foo", "example.com:8080") into a host pattern."""
    text = (value or "").strip().lower()
    if not text:
        raise ValueError("Site host is required")
    if "://" in text:
        text = urlparse(text).hostname or ""
    else:
        text = text.split("/", 1)[0]
    wildcard = text.startswith("*.")
    host = text[2:] if wildcard else text
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    if not host or not _HOST_RE.match(host):
        raise ValueError(f"Invalid site host: {value}")
    return f"*.{host}" if wildcard else host


def host_matches(pattern: str, host: str) -> bool:
    """True when *host* satisfies an exact or "*.domain" pattern."""
    pattern = (pattern or "").strip().lower().rstrip(".")
    host = (host or "").strip().lower().rstrip(".")
    if not pattern or not host:
        return False
    if pattern.startswith("*."):
        base = pattern[2:]
        return host == base or host.endswith("." + base)
    return host == pattern


def find_site_credentials(
    entries: Optional[Dict[str, Dict[str, str]]],
    url: str,
) -> Optional[Tuple[str, str]]:
    """Return (username, password) for the most specific entry matching *url*."""
    if not entries:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None

    best_pattern = ""
    best: Optional[Tuple[str, str]] = None
    for pattern, entry in entries.items():
        if not isinstance(entry, dict) or not host_matches(pattern, host):
            continue
        username = str(entry.get("username") or "")
        password = unprotect_secret(str(entry.get("password") or ""))
        if not username or not password:
            continue
        # Exact hosts always win; otherwise prefer the longest wildcard.
        is_exact = 0 if pattern.startswith("*.") else 1
        best_is_exact = 0 if best_pattern.startswith("*.") else 1
        if best is None or (is_exact, len(pattern)) > (best_is_exact, len(best_pattern)):
            best_pattern = pattern
            best = (username, password)
    return best


def sanitize_site_credentials(raw: Any) -> Dict[str, Dict[str, str]]:
    """Keep only well-formed entries and normalize their host patterns."""
    cleaned: Dict[str, Dict[str, str]] = {}
    if not isinstance(raw, dict):
        return cleaned
    for pattern, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        username = entry.get("username")
        password = entry.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            continue
        username = username.strip()
        if not username or not password:
            continue
        try:
            normalized = normalize_site_pattern(str(pattern))
        except ValueError:
            continue
        cleaned[normalized] = {"username": username, "password": password}
    return cleaned
