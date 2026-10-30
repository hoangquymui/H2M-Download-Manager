"""HDM Download Engine.
High-performance asynchronous multi-connection downloading with a fixed
segment count per task (one segment per configured connection).
"""

from __future__ import annotations

import asyncio
import gc
import hashlib
import ipaddress
import json
import logging
import os
import pathlib
import random
import re
import shutil
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from hdm.core.models import Chunk, DownloadTask, TaskStatus
from hdm.core.sparse_file import preallocate_file
from hdm.utils.formatters import extract_filename_from_url

logger = logging.getLogger("HDM.Engine")

MIN_CHUNK_SIZE = 1048576       # 1 MB
READ_BUFFER_SIZE = 262144      # 256 KB read buffer for high-speed streaming
MAX_CHUNK_RETRIES = 8          # Retries with exponential backoff before failing

STREAMING_DOMAINS = (
    "youtube.com",
    "youtube-nocookie.com",
    "youtu.be",
    "facebook.com",
    "fb.watch",
    "tiktok.com",
    "douyin.com",
    "instagram.com",
    "threads.net",
    "twitter.com",
    "x.com",
    "reddit.com",
    "vimeo.com",
    "dailymotion.com",
    "bilibili.com",
    "twitch.tv",
    "soundcloud.com",
    "pinterest.com",
    "rumble.com",
    "streamable.com",
    "weibo.com",
    "kuaishou.com",
    "vk.com",
    "bandcamp.com",
    "mixcloud.com",
)


def is_streaming_url(url: str) -> bool:
    """Check if the URL belongs to a streaming service or manifests supported by yt-dlp.

    Hosts are matched by exact domain / subdomain, never by raw substring, so
    domains like 'box.com' are not treated as 'x.com'.
    """
    if not url:
        return False
    value = url.strip().lower()
    try:
        parsed = urlparse(value)
    except ValueError:
        return False

    if parsed.scheme == "file":
        path = parsed.path or ""
        return path.endswith(".m3u8") or path.endswith(".mpd")

    if not parsed.netloc:
        # Allow bare host input like "vimeo.com/123"
        try:
            parsed = urlparse(f"https://{value.lstrip('/')}")
        except ValueError:
            return False

    host = (parsed.hostname or "").strip(".")
    path = parsed.path or ""
    if ".m3u8" in path or ".mpd" in path:
        return True
    if ".m3u8" in (parsed.query or "") or ".mpd" in (parsed.query or ""):
        return True

    for domain in STREAMING_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


HEIGHT_QUALITIES = ("1080", "720", "480", "360", "240", "144")

# YouTube-family hosts handle authentication and URL signing themselves. Raw
# browser cookies/headers confuse them (bot checks, 403 on googlevideo), so
# yt-dlp is left to manage its own session there.
NO_BROWSER_HEADER_DOMAINS = (
    "youtube.com",
    "youtube-nocookie.com",
    "youtu.be",
    "googlevideo.com",
    "googleusercontent.com",
)


def _needs_browser_headers(url: str) -> bool:
    """False for platforms where raw browser headers break yt-dlp."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return True
    return not any(host == d or host.endswith("." + d) for d in NO_BROWSER_HEADER_DOMAINS)


def _is_placeholder_filename(name: str) -> bool:
    """True when a filename carries no real name (empty, generic, no extension).

    Signed CDN links usually suggest an opaque UUID, so those names must yield
    to the Content-Disposition / URL name. A name the user chose always wins.
    """
    base = os.path.basename((name or "").strip())
    if not base:
        return True
    if base.lower() in ("watch", "watch.html", "index.html", "download", "videoplayback"):
        return True
    return not os.path.splitext(base)[1]


def _cookie_pairs(cookie_header: str) -> List[Tuple[str, str]]:
    """Split a `Cookie: a=1; b=2` header into (name, value) pairs."""
    pairs: List[Tuple[str, str]] = []
    for part in (cookie_header or "").split(";"):
        name, sep, value = part.strip().partition("=")
        name = name.strip()
        value = value.strip()
        if not sep or not name or any(c in name + value for c in "\t\r\n"):
            continue
        pairs.append((name, value))
    return pairs


def _media_hosts(url: str, manifest: str) -> List[str]:
    """Hosts that will receive the captured cookies: the task URL plus every
    absolute URL in the playlist (variants, segments, keys)."""
    hosts: List[str] = []
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        host = ""
    if host:
        hosts.append(host)
    for match in re.finditer(r"https?://[^\s\"'`<>\\]+", manifest or ""):
        try:
            host = (urlparse(match.group(0)).hostname or "").lower()
        except ValueError:
            continue
        if host:
            hosts.append(host)
    return list(dict.fromkeys(hosts))


def _write_cookiefile(path: str, cookie_header: str, url: str, manifest: str) -> bool:
    """Write a Netscape cookie file for the stream hosts.

    yt-dlp drops a plain `Cookie:` header when the playlist is fed from a local
    file:// URL, because it can no longer infer a domain to scope it to. A
    cookie jar scoped to the media hosts keeps protected HLS working.
    """
    pairs = _cookie_pairs(cookie_header)
    hosts = _media_hosts(url, manifest)
    if not pairs or not hosts:
        return False
    expiry = int(time.time()) + 86400 * 365
    lines = ["# Netscape HTTP Cookie File", ""]
    for host in hosts:
        bare = host.lstrip(".")
        try:
            ipaddress.ip_address(bare)
            domain, include_subdomains = bare, "FALSE"
        except ValueError:
            # Netscape requires a leading dot whenever subdomains are included;
            # a leading dot never matches an IP literal, hence the branch above.
            domain, include_subdomains = f".{bare}", "TRUE"
        for name, value in pairs:
            lines.append(f"{domain}\t{include_subdomains}\t/\tFALSE\t{expiry}\t{name}\t{value}")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        return False
    return True


def _js_runtimes() -> Dict[str, Dict[str, Any]]:
    """Enable installed JS runtimes for yt-dlp's YouTube challenge solving.

    Recent yt-dlp only enables deno by default; without a runtime (plus the
    yt-dlp-ejs solver) YouTube silently loses most formats.
    """
    runtimes: Dict[str, Dict[str, Any]] = {}
    for name in ("node", "deno", "bun"):
        if shutil.which(name):
            runtimes[name] = {}
    return runtimes


def _stream_format_spec(quality: str, is_audio_only: bool, manifest: str = "") -> str:
    """Pick the yt-dlp format selector for a stream or captured playlist.

    Height filters only apply when the source actually exposes several
    renditions (master playlist or a stream URL); a captured media playlist is
    already a single rendition. MP4/M4A is preferred so YouTube and similar
    sites produce a universally playable file.
    """
    if is_audio_only:
        return "bestaudio/best"

    height = quality if quality in HEIGHT_QUALITIES else ""
    is_master = "#EXT-X-STREAM-INF" in manifest

    if manifest and not is_master:
        return "best"
    if is_master:
        # Masters may expose muxed renditions or separate video/audio variants.
        if height:
            return (
                f"b[height<={height}]/bv*[height<={height}]+ba/"
                f"b[height<={height}]/b"
            )
        return "b/bv*+ba/b"
    if height:
        return (
            f"bv*[height<={height}][vcodec^=avc1]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/b[height<={height}]/b"
        )
    return "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*+ba/b"


class AsyncBatchDiskWriter:
    """High-throughput asynchronous non-blocking disk writer.
    Eliminates file write lock contention between concurrent download workers.
    """

    def __init__(self, file_path: str, mode: str = "r+b", queue_size: int = 512) -> None:
        self.file_path = file_path
        self.mode = mode
        self.queue: asyncio.Queue[Optional[Tuple[int, bytes]]] = asyncio.Queue(maxsize=queue_size)
        self._handle: Optional[Any] = None
        self._writer_task: Optional[asyncio.Task[None]] = None
        self._closed = False
        self._write_error: Optional[str] = None
        self._flush_interval = 0.5
        self._last_flush = time.time()

    async def start(self) -> None:
        """Open the target file and spawn the dedicated disk writer coroutine."""
        self._handle = open(self.file_path, self.mode)
        self._writer_task = asyncio.create_task(self._worker_loop())

    async def put(self, offset: int, data: bytes) -> None:
        """Enqueue a block of data for asynchronous disk write."""
        if self._closed:
            return
        if self._write_error:
            # Never silently drop payload: a caller must be able to abort the task.
            raise IOError(f"Lỗi ghi đĩa: {self._write_error}")
        await self.queue.put((offset, data))

    async def truncate(self, size: int = 0) -> None:
        """Truncate the file at a specific size (used for non-range stream retries)."""
        if self._handle and not self._write_error:
            self._handle.seek(size)
            self._handle.truncate(size)

    async def _worker_loop(self) -> None:
        """Background loop reading from queue and writing directly to disk."""
        while True:
            item = await self.queue.get()
            if item is None:
                self.queue.task_done()
                break

            offset, data = item
            try:
                if self._handle and not self._write_error:
                    self._handle.seek(offset)
                    self._handle.write(data)
                    now = time.time()
                    if now - self._last_flush >= self._flush_interval:
                        self._handle.flush()
                        self._last_flush = now
            except Exception as e:
                self._write_error = str(e)
                logger.error(f"AsyncBatchDiskWriter error at offset {offset}: {e}")
            finally:
                self.queue.task_done()

    @property
    def error(self) -> Optional[str]:
        return self._write_error

    async def close(self) -> None:
        """Gracefully drain the writer queue, flush buffers, and close the file handle."""
        if self._closed:
            return
        self._closed = True
        try:
            await self.queue.put(None)
            if self._writer_task:
                await self._writer_task
        except Exception:
            pass
        finally:
            self._writer_task = None
            if self._handle:
                try:
                    self._handle.flush()
                    self._handle.close()
                except Exception:
                    pass
                self._handle = None


async def verify_file_checksum(file_path: str, expected_hash: str, algorithm: str = "sha256") -> bool:
    """Verify file integrity asynchronously without blocking the event loop."""
    if not os.path.exists(file_path) or not expected_hash:
        return False

    def compute() -> str:
        algo_name = algorithm.lower().replace("-", "")
        if algo_name == "sha256":
            hasher = hashlib.sha256()
        elif algo_name == "md5":
            hasher = hashlib.md5()
        elif algo_name == "sha1":
            hasher = hashlib.sha1()
        elif algo_name == "sha512":
            hasher = hashlib.sha512()
        else:
            hasher = hashlib.sha256()

        with open(file_path, "rb") as f:
            while chunk := f.read(524288):  # 512 KB chunks
                hasher.update(chunk)
        return hasher.hexdigest()

    try:
        computed = await asyncio.to_thread(compute)
        return computed.lower() == expected_hash.strip().lower()
    except Exception as e:
        logger.warning(f"Failed to verify checksum for {file_path}: {e}")
        return False


class DownloadEngine:
    """Core download engine handling fixed-connection chunking, streaming, and resume."""

    def __init__(
        self,
        task: DownloadTask,
        on_progress: Optional[Callable[[DownloadTask], None]] = None,
        on_chunk_update: Optional[Callable[[DownloadTask], None]] = None,
        min_chunk_size: int = MIN_CHUNK_SIZE,
        speed_limit_kbps: int = 0,
    ) -> None:
        self.task = task
        self.on_progress = on_progress
        self.on_chunk_update = on_chunk_update
        self.min_chunk_size = max(65536, min_chunk_size or MIN_CHUNK_SIZE)
        self.speed_limit_kbps = max(0, speed_limit_kbps or 0)

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pause_requested = asyncio.Event()
        self._cancel_requested = asyncio.Event()
        self._chunks_lock = asyncio.Lock()

        self._disk_writer: Optional[AsyncBatchDiskWriter] = None
        self._disk_writer_error: Optional[str] = None
        self._fail_counts: Dict[int, int] = {}
        self._last_speed_check_time = time.time()
        self._last_downloaded_bytes = 0

    def _signal_from_any_thread(self, event: asyncio.Event) -> None:
        """Set an asyncio.Event safely even when called from the Qt GUI thread."""
        loop = self._loop
        if loop and loop.is_running():
            try:
                loop.call_soon_threadsafe(event.set)
                return
            except RuntimeError:
                pass
        event.set()

    def pause(self) -> None:
        """Signal the engine to pause downloading."""
        self._signal_from_any_thread(self._pause_requested)

    def cancel(self) -> None:
        """Signal the engine to cancel downloading."""
        self._signal_from_any_thread(self._cancel_requested)

    def update_url(self, new_url: str) -> None:
        """Update download URL (useful when temporary CDN links expire with HTTP 403/410)."""
        self.task.url = new_url
        logger.info(f"Task {self.task.id} updated with refreshed URL: {new_url}")

    async def probe(self, client: httpx.AsyncClient) -> bool:
        """Inspect the URL with HEAD / GET Range probe, or yt_dlp for streaming video."""
        self.task.status = TaskStatus.CONNECTING
        if self.on_progress:
            self.on_progress(self.task)

        # Check if URL is from a streaming video site (YouTube, Facebook, TikTok, etc.)
        if is_streaming_url(self.task.url):
            try:
                import yt_dlp

                def extract():
                    ydl_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "skip_download": True,
                        "nocheckcertificate": True,
                        "noplaylist": True,
                    }
                    if self.task.headers:
                        ydl_opts["http_headers"] = dict(self.task.headers)
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(self.task.url, download=False)

                info = await asyncio.to_thread(extract)
                if info:
                    title = info.get("title", "")
                    from hdm.utils.formatters import clean_filename
                    ext = info.get("ext", "mp4")
                    if not self.task.filename or self.task.filename.startswith("watch"):
                        clean_t = clean_filename(title) if title else "video"
                        self.task.filename = f"{clean_t}.{ext}"

                    self.task.total_bytes = info.get("filesize") or info.get("filesize_approx") or 0
                    self.task.supports_range = True
                    return True
            except Exception as e:
                logger.debug(f"yt_dlp streaming probe exception: {e}")

        headers = dict(self.task.headers)
        headers.setdefault("Accept-Encoding", "identity")
        probe_success = False

        # 1. First attempt HEAD request
        try:
            head_resp = await client.head(self.task.url, headers=headers, follow_redirects=True, timeout=15.0)
            if head_resp.status_code in (200, 206):
                probe_success = True
                self._extract_metadata(head_resp)
        except Exception as e:
            logger.debug(f"HEAD probe failed for {self.task.url}: {e}")

        # 2. Fallback to GET with Range: bytes=0-0
        if not probe_success or self.task.total_bytes <= 0:
            try:
                range_headers = dict(headers)
                range_headers["Range"] = "bytes=0-0"
                get_resp = await client.get(self.task.url, headers=range_headers, follow_redirects=True, timeout=15.0)
                if get_resp.status_code >= 400 and not probe_success:
                    self.task.error_message = f"Máy chủ trả về lỗi HTTP {get_resp.status_code}"
                    self.task.status = TaskStatus.ERROR
                    return False
                if get_resp.status_code in (200, 206):
                    self._extract_metadata(get_resp)
                    if get_resp.status_code == 206:
                        self.task.supports_range = True
                        content_range = get_resp.headers.get("content-range", "")
                        if "/" in content_range:
                            try:
                                total_str = content_range.split("/")[1]
                                if total_str != "*":
                                    self.task.total_bytes = int(total_str)
                            except ValueError:
                                pass
            except Exception as e:
                logger.error(f"GET Range probe failed for {self.task.url}: {e}")
                self.task.error_message = f"Không thể kết nối đến máy chủ: {e}"
                self.task.status = TaskStatus.ERROR
                return False

        # Ensure filename is set
        if not self.task.filename:
            self.task.filename = extract_filename_from_url(str(self.task.url))

        return True

    def _extract_metadata(self, response: httpx.Response) -> None:
        """Extract size, ETag, Range support, and filename from response headers."""
        headers = response.headers
        cl = headers.get("x-identity-content-length") or headers.get("content-length")
        if cl:
            try:
                self.task.total_bytes = int(cl)
            except ValueError:
                pass

        accept_ranges = headers.get("accept-ranges", "").lower()
        if accept_ranges == "bytes" or response.status_code == 206:
            self.task.supports_range = True

        etag = headers.get("etag", "").strip('"')
        if etag:
            self.task.etag = etag

        content_type = headers.get("content-type", "")
        if content_type:
            self.task.content_type = content_type

        # Only replace a placeholder name: a name typed in the dialog (or a real
        # name from the URL) must survive the server's headers.
        cd = headers.get("content-disposition", "")
        extracted_name = extract_filename_from_url(str(response.url), cd)
        if (
            extracted_name
            and extracted_name != "download"
            and _is_placeholder_filename(self.task.filename)
        ):
            self.task.filename = extracted_name

    def _save_metadata(self) -> None:
        """Save chunk progress state into .hdm_meta file for resume."""
        try:
            meta_data = {
                "url": self.task.url,
                "filename": self.task.filename,
                "total_bytes": self.task.total_bytes,
                "etag": self.task.etag,
                "supports_range": self.task.supports_range,
                "chunks": [c.to_dict() for c in self.task.chunks],
            }
            with open(self.task.meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save metadata to {self.task.meta_path}: {e}")

    def _load_metadata(self) -> bool:
        """Load chunks from existing .hdm_meta file if valid."""
        if not os.path.exists(self.task.meta_path):
            return False
        try:
            with open(self.task.meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("total_bytes") != self.task.total_bytes or not data.get("chunks"):
                return False

            # The remote file must still be the same object; otherwise byte offsets
            # from the old download are meaningless and the resume is corrupt.
            saved_etag = str(data.get("etag", "") or "")
            if saved_etag and self.task.etag and saved_etag != self.task.etag:
                logger.info(f"Task {self.task.id}: ETag changed, restarting download")
                return False

            self.task.chunks = [Chunk.from_dict(c) for c in data["chunks"]]
            # A pause stores chunks mid-flight as "downloading"; nothing owns
            # them in the new run, so they would never be claimed again.
            for chunk in self.task.chunks:
                if chunk.end_byte >= 0 and chunk.remaining_bytes <= 0:
                    chunk.status = "completed"
                elif chunk.status in ("downloading", "failed"):
                    chunk.status = "pending"
                chunk.speed = 0.0
            self.task.update_downloaded_from_chunks()
            return True
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")
        return False

    def _prepare_temp_dir(self) -> bool:
        """Create the hidden temp folder that holds every partial artifact."""
        try:
            os.makedirs(self.task.temp_dir, exist_ok=True)
            return True
        except OSError as e:
            self.task.status = TaskStatus.ERROR
            self.task.error_message = f"Không thể tạo thư mục tạm: {e}"
            if self.on_progress:
                self.on_progress(self.task)
            return False

    def _migrate_legacy_temp(self) -> None:
        """Move partial files from the old beside-the-target layout into .hdm_tmp."""
        for legacy, current in (
            (self.task.legacy_temp_path, self.task.temp_path),
            (self.task.legacy_meta_path, self.task.meta_path),
        ):
            if os.path.exists(legacy) and not os.path.exists(current):
                try:
                    os.replace(legacy, current)
                except OSError as e:
                    logger.debug(f"Legacy temp migration skipped for {legacy}: {e}")

    def _cleanup_temp_files(self, keep_partial: bool) -> None:
        """Remove temp artifacts; the shared folder disappears when it is empty."""
        paths = [self.task.meta_path]
        if not keep_partial:
            paths.append(self.task.temp_path)
            shutil.rmtree(self.task.stream_temp_dir, ignore_errors=True)
        for path in paths:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if not keep_partial:
            try:
                os.rmdir(self.task.temp_dir)
            except OSError:
                pass

    async def _inline_hls_keys(self, manifest: str, workdir: str) -> str:
        """Point AES-128 key URIs at local copies fetched with the session.

        yt-dlp requests EXT-X-KEY URIs without the captured Referer/Cookie, so
        protected keys answer 403 even when segments download fine. Keys that
        cannot be fetched are left untouched for yt-dlp to retry.
        """
        headers = dict(self.task.headers or {})
        key_files: Dict[str, Optional[str]] = {}
        lines: List[str] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=30.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            for line in manifest.splitlines():
                if not line.startswith("#EXT-X-KEY") or "METHOD=AES-128" not in line.upper():
                    lines.append(line)
                    continue
                match = re.search(r'URI="([^"]+)"', line) or re.search(r"URI=([^,\s]+)", line)
                uri = match.group(1) if match else ""
                if not uri.lower().startswith(("http://", "https://")):
                    lines.append(line)
                    continue
                if uri not in key_files:
                    local_uri: Optional[str] = None
                    try:
                        response = await client.get(uri)
                        response.raise_for_status()
                        if len(response.content) != 16:
                            raise ValueError(f"unexpected key length {len(response.content)}")
                        key_path = os.path.join(workdir, f"key_{len(key_files)}.bin")
                        with open(key_path, "wb") as f:
                            f.write(response.content)
                        local_uri = pathlib.Path(key_path).absolute().as_uri()
                    except Exception as e:
                        logger.debug(f"HLS key prefetch skipped for {uri}: {e}")
                    key_files[uri] = local_uri
                if key_files[uri]:
                    line = line.replace(match.group(0), f'URI="{key_files[uri]}"')
                lines.append(line)
        return "\n".join(lines)

    async def _download_streaming_video(self) -> bool:
        """Download streaming media from YouTube, Facebook, TikTok, etc. using yt_dlp."""
        import yt_dlp
        from hdm.utils.formatters import clean_filename

        self.task.status = TaskStatus.DOWNLOADING
        if self.on_progress:
            self.on_progress(self.task)

        num_conns = max(1, min(32, self.task.num_connections or 8))
        self.task.supports_range = True

        if not self.task.chunks:
            self.task.chunks = [
                Chunk(
                    chunk_id=i + 1,
                    start_byte=0,
                    end_byte=0,
                    current_pos=0,
                    status="downloading",
                )
                for i in range(num_conns)
            ]

        try:
            os.makedirs(self.task.save_dir, exist_ok=True)
            os.makedirs(self.task.stream_temp_dir, exist_ok=True)
        except Exception as e:
            self.task.status = TaskStatus.ERROR
            self.task.error_message = f"Không thể tạo thư mục lưu: {e}"
            if self.on_progress:
                self.on_progress(self.task)
            return False
        base_name = os.path.splitext(self.task.filename)[0] if self.task.filename else "video"
        base_name = clean_filename(base_name)
        out_pattern = os.path.join(self.task.save_dir, f"{base_name}.%(ext)s")

        def progress_hook(d):
            if self._cancel_requested.is_set():
                raise Exception("Tác vụ đã bị hủy bởi người dùng")
            if self._pause_requested.is_set():
                raise Exception("Tác vụ đã tạm dừng")

            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0.0

                if total > 0:
                    self.task.total_bytes = total
                self.task.downloaded_bytes = downloaded
                self.task.speed = speed

                if self.task.chunks and self.task.total_bytes > 0:
                    chunk_size = self.task.total_bytes // num_conns
                    for i, c in enumerate(self.task.chunks):
                        c.start_byte = i * chunk_size
                        c.end_byte = (i + 1) * chunk_size - 1 if i < num_conns - 1 else self.task.total_bytes - 1
                        c_len = max(1, c.end_byte - c.start_byte + 1)
                        c_dl = min(c_len, max(0, downloaded - i * chunk_size))
                        c.current_pos = c.start_byte + c_dl
                        c.status = "completed" if c_dl >= c_len else "downloading"
                        c.speed = speed / num_conns
                    if self.on_chunk_update:
                        self.on_chunk_update(self.task)

                if self.on_progress:
                    self.on_progress(self.task)

            elif d["status"] == "finished":
                if self.task.total_bytes > 0:
                    self.task.downloaded_bytes = self.task.total_bytes
                self.task.speed = 0.0
                self.task.status = TaskStatus.PROCESSING
                self.task.error_message = (
                    "Đang trích xuất & chuyển đổi MP3 (FFmpeg)..."
                    if is_audio_only
                    else "Đang ghép nối video & âm thanh (FFmpeg)..."
                )
                if self.task.chunks:
                    for c in self.task.chunks:
                        c.current_pos = c.end_byte + 1
                        c.status = "completed"
                        c.speed = 0.0
                    if self.on_chunk_update:
                        self.on_chunk_update(self.task)
                if self.on_progress:
                    self.on_progress(self.task)

        def postprocessor_hook(d):
            if self._cancel_requested.is_set():
                raise Exception("Tác vụ đã bị hủy bởi người dùng")
            if self._pause_requested.is_set():
                raise Exception("Tác vụ đã tạm dừng")

            status = d.get("status")
            pp = d.get("postprocessor", "")
            if status == "started":
                self.task.status = TaskStatus.PROCESSING
                self.task.speed = 0.0
                if "ExtractAudio" in pp or is_audio_only:
                    self.task.error_message = "Đang trích xuất & chuyển đổi MP3 (FFmpeg)..."
                else:
                    self.task.error_message = "Đang ghép nối video & âm thanh (FFmpeg)..."
                if self.on_progress:
                    self.on_progress(self.task)
            elif status == "finished":
                self.task.error_message = ""

        # Locate ffmpeg across PATH, the packaged dependency, and common installs
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        ffmpeg_paths = [
            shutil.which("ffmpeg"),
            os.path.join(local_appdata, "Microsoft", "WinGet", "Links", "ffmpeg.exe") if local_appdata else "",
            r"C:\Program Files\File Converter\ffmpeg.exe",
            os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"),
            os.path.join(os.path.dirname(sys.executable), "bin", "ffmpeg.exe"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
        ]
        ffmpeg_bin = next((p for p in ffmpeg_paths if p and os.path.exists(p)), None)
        if not ffmpeg_bin:
            try:
                import imageio_ffmpeg

                ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_bin = None

        quality = getattr(self.task, "quality", "") or ""
        is_audio_only = bool(
            (self.task.filename and self.task.filename.lower().endswith(".mp3"))
            or quality in ("128", "192", "320")
        )

        if self.task.manifest:
            # The captured playlist already represents one specific rendition.
            format_spec = _stream_format_spec(quality, is_audio_only, self.task.manifest)
        else:
            format_spec = _stream_format_spec(quality, is_audio_only)

        ydl_opts = {
            "format": format_spec,
            "outtmpl": out_pattern,
            "paths": {"temp": self.task.stream_temp_dir},
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "concurrent_fragment_downloads": num_conns,
            "buffersize": 16 * 1024 * 1024,      # 16 MB memory buffer for high bitrate
            "http_chunk_size": 10 * 1024 * 1024, # 10 MB chunk size for video fragments
            "retries": 10,
            "fragment_retries": 10,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noplaylist": True,
        }
        if self.speed_limit_kbps > 0:
            ydl_opts["ratelimit"] = self.speed_limit_kbps * 1024

        runtimes = _js_runtimes()
        if runtimes:
            ydl_opts["js_runtimes"] = runtimes

        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin)
            if is_audio_only:
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": quality if quality in ("128", "192", "320") else "128",
                }]

        cookie_dirs: List[str] = []
        if self.task.headers and _needs_browser_headers(self.task.url):
            # Cookies/Referer are required by many protected HLS CDNs; dropping
            # them here made the browser-captured streams fail with HTTP 403.
            headers = dict(self.task.headers)
            cookie_header = headers.pop("Cookie", "") or headers.pop("cookie", "")
            if cookie_header:
                cookie_dir = tempfile.mkdtemp(prefix="hdm_cookies_")
                cookie_dirs.append(cookie_dir)
                cookie_path = os.path.join(cookie_dir, "cookies.txt")
                if _write_cookiefile(cookie_path, cookie_header, self.task.url, self.task.manifest):
                    ydl_opts["cookiefile"] = cookie_path
            if headers:
                ydl_opts["http_headers"] = headers

        manifest_dir = ""
        manifest_path = ""
        if self.task.manifest:
            # The page generated the playlist in JS (blob: URL), so it cannot be
            # re-fetched. Feed the captured text to yt-dlp as a local playlist.
            # Keep it outside save_dir: yt-dlp leaks read handles on Windows and
            # the file often survives deletion until the process exits.
            manifest_dir = tempfile.mkdtemp(prefix="hdm_m3u8_")
            manifest_path = os.path.join(manifest_dir, f"manifest_{self.task.id}.m3u8")
            ydl_opts["enable_file_urls"] = True

        def cleanup_manifest() -> None:
            for cookie_dir in cookie_dirs:
                shutil.rmtree(cookie_dir, ignore_errors=True)
            if not manifest_dir:
                return
            for _ in range(3):
                # yt-dlp's urllib handler leaks the file response object; a GC
                # pass releases the Windows handle so the file can be removed.
                gc.collect()
                shutil.rmtree(manifest_dir, ignore_errors=True)
                if not os.path.exists(manifest_dir):
                    return
                time.sleep(0.2)

        try:
            source = self.task.url
            if manifest_path:
                try:
                    manifest_text = self.task.manifest.strip()
                    manifest_text = await self._inline_hls_keys(manifest_text, manifest_dir)
                    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
                        f.write(manifest_text + "\n")
                    source = pathlib.Path(manifest_path).absolute().as_uri()
                except Exception as e:
                    self.task.status = TaskStatus.ERROR
                    self.task.error_message = f"Không thể lưu manifest HLS: {e}"
                    if self.on_progress:
                        self.on_progress(self.task)
                    return False

            def do_dl():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(source, download=True)

            info = await asyncio.to_thread(do_dl)

            # Locate downloaded file
            final_path = None
            if info and "requested_downloads" in info:
                for rd in info["requested_downloads"]:
                    p = rd.get("filepath")
                    if p and os.path.exists(p):
                        final_path = p
                        break
            if not final_path and info and "_filename" in info and os.path.exists(info["_filename"]):
                final_path = info["_filename"]

            if not final_path:
                for ext in [".mp4", ".webm", ".mkv", ".m4a", ".mp3"]:
                    cand = os.path.join(self.task.save_dir, f"{base_name}{ext}")
                    if os.path.exists(cand):
                        final_path = cand
                        break

            if final_path and os.path.exists(final_path):
                self.task.filename = os.path.basename(final_path)
                self.task.total_bytes = os.path.getsize(final_path)
                self.task.downloaded_bytes = self.task.total_bytes
                self.task.status = TaskStatus.COMPLETED
                self.task.error_message = ""
                self.task.speed = 0.0
                self.task.completed_at = time.time()
                if self.on_progress:
                    self.on_progress(self.task)
                return True
            else:
                self.task.status = TaskStatus.ERROR
                self.task.error_message = "Không tìm thấy tệp sau khi tải video"
                if self.on_progress:
                    self.on_progress(self.task)
                return False

        except Exception as e:
            if self._cancel_requested.is_set():
                self.task.status = TaskStatus.CANCELLED
            elif self._pause_requested.is_set():
                self.task.status = TaskStatus.PAUSED
            else:
                message = str(e)
                lowered = message.lower()
                if not _js_runtimes() and (
                    "signature" in lowered or "javascript runtime" in lowered
                ):
                    message += " — HDM: cài Node.js (hoặc Deno) để giải mã luồng YouTube."
                self.task.status = TaskStatus.ERROR
                self.task.error_message = f"Lỗi tải video: {message}"
            if self.on_progress:
                self.on_progress(self.task)
            return False
        finally:
            cleanup_manifest()
            # Paused streams keep their fragments so Resume can continue them.
            self._cleanup_temp_files(keep_partial=self.task.status == TaskStatus.PAUSED)

    async def run(self) -> bool:
        """Execute the download process."""
        self._loop = asyncio.get_running_loop()
        self._pause_requested.clear()
        self._cancel_requested.clear()

        # Captured in-page playlists and streaming platforms go through yt-dlp
        if self.task.manifest or is_streaming_url(self.task.url):
            return await self._download_streaming_video()

        timeout = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=45.0)
        limits = httpx.Limits(max_connections=64, max_keepalive_connections=32, keepalive_expiry=30.0)
        default_headers = {"Accept-Encoding": "identity"}

        async with httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            headers=default_headers,
            follow_redirects=True,
            http2=True,
        ) as client:
            # 1. Probe server metadata if not yet known
            if self.task.total_bytes <= 0:
                success = await self.probe(client)
                if not success:
                    return False

            # Check free disk space before preallocation
            from hdm.core.sparse_file import check_free_space
            if self.task.total_bytes > 0:
                has_space, free_bytes, req_bytes = check_free_space(self.task.save_dir, self.task.total_bytes)
                if not has_space:
                    from hdm.utils.formatters import format_bytes
                    drive = os.path.splitdrive(os.path.abspath(self.task.save_dir))[0] or self.task.save_dir
                    self.task.error_message = (
                        f"Ổ đĩa {drive} không đủ dung lượng trống "
                        f"(Cần: {format_bytes(req_bytes)}, Còn trống: {format_bytes(free_bytes)}). "
                        f"Vui lòng chọn thư mục lưu trên ổ đĩa khác (ví dụ ổ D:)."
                    )
                    self.task.status = TaskStatus.ERROR
                    if self.on_progress:
                        self.on_progress(self.task)
                    return False

            try:
                os.makedirs(self.task.save_dir, exist_ok=True)
            except Exception as e:
                self.task.status = TaskStatus.ERROR
                self.task.error_message = f"Không thể tạo thư mục lưu: {e}"
                if self.on_progress:
                    self.on_progress(self.task)
                return False

            if not self._prepare_temp_dir():
                return False
            self._migrate_legacy_temp()

            # 2. Initialize chunks or load from saved metadata
            if self.task.supports_range and self.task.total_bytes > 0:
                has_meta = self._load_metadata()
                if has_meta and not os.path.exists(self.task.temp_path):
                    # Meta survived but the partial file was removed: byte offsets
                    # would produce a corrupt sparse file, so restart from scratch.
                    has_meta = False
                    self.task.chunks = []
                    self.task.downloaded_bytes = 0
                if not has_meta or not self.task.chunks:
                    # Initial partition
                    num_workers = min(
                        self.task.num_connections,
                        max(1, self.task.total_bytes // self.min_chunk_size)
                    )
                    chunk_size = self.task.total_bytes // num_workers
                    self.task.chunks = []
                    for i in range(num_workers):
                        start = i * chunk_size
                        end = (start + chunk_size - 1) if (i < num_workers - 1) else (self.task.total_bytes - 1)
                        self.task.chunks.append(
                            Chunk(
                                chunk_id=i + 1,
                                start_byte=start,
                                end_byte=end,
                                current_pos=start,
                                status="pending",
                            )
                        )
                    # Pre-allocate sparse file
                    preallocate_file(self.task.temp_path, self.task.total_bytes)
                    self._save_metadata()
            else:
                # Single-stream download
                if not self.task.chunks:
                    self.task.chunks = [
                        Chunk(
                            chunk_id=1,
                            start_byte=0,
                            end_byte=self.task.total_bytes - 1 if self.task.total_bytes > 0 else -1,
                            current_pos=0,
                            status="pending",
                        )
                    ]

            self.task.status = TaskStatus.DOWNLOADING
            self._last_speed_check_time = time.time()
            self._last_downloaded_bytes = self.task.downloaded_bytes

            # 3. Start non-blocking disk writer for direct binary streaming
            mode = "r+b" if (self.task.supports_range and os.path.exists(self.task.temp_path)) else "wb"
            try:
                self._disk_writer = AsyncBatchDiskWriter(self.task.temp_path, mode=mode)
                await self._disk_writer.start()
            except Exception as e:
                self.task.error_message = f"Không thể mở tệp ghi: {e}"
                self.task.status = TaskStatus.ERROR
                return False

            # 4. Launch speed tracking task
            speed_task = asyncio.create_task(self._speed_monitor())

            try:
                # 5. Launch worker tasks. Never open more connections than the
                # task asked for, even when resumed metadata holds extra chunks.
                num_workers = (
                    min(self.task.num_connections, len(self.task.chunks))
                    if self.task.supports_range else 1
                )
                num_workers = max(1, num_workers)
                workers = [
                    asyncio.create_task(self._worker(client, worker_id=i + 1))
                    for i in range(num_workers)
                ]

                await asyncio.gather(*workers)
            finally:
                speed_task.cancel()
                try:
                    await speed_task
                except asyncio.CancelledError:
                    pass

                if self._disk_writer:
                    await self._disk_writer.close()
                    if self._disk_writer.error:
                        self._disk_writer_error = self._disk_writer.error
                    self._disk_writer = None

            # 6. Check completion status
            if self._cancel_requested.is_set():
                self.task.status = TaskStatus.CANCELLED
                self.task.speed = 0.0
                self._cleanup_temp_files(keep_partial=False)
                return False

            if self._pause_requested.is_set():
                self.task.status = TaskStatus.PAUSED
                self.task.speed = 0.0
                self._save_metadata()
                if self.on_progress:
                    self.on_progress(self.task)
                return False

            # A failed disk write corrupts the partial file: never report COMPLETED.
            if self._disk_writer_error:
                self.task.status = TaskStatus.ERROR
                self.task.error_message = f"Lỗi ghi đĩa: {self._disk_writer_error}"
                self.task.speed = 0.0
                if self.on_progress:
                    self.on_progress(self.task)
                return False

            # Check if all chunks finished
            all_done = all(c.status == "completed" for c in self.task.chunks)
            if all_done:
                self.task.status = TaskStatus.COMPLETED
                self.task.speed = 0.0
                self.task.completed_at = time.time()
                if self.task.total_bytes <= 0:
                    # Unknown-size stream: real size is whatever we received
                    self.task.total_bytes = sum(c.downloaded_bytes for c in self.task.chunks)
                self.task.downloaded_bytes = self.task.total_bytes

                # Resume metadata is no longer needed; the partial file is kept
                # for the (same-volume) atomic rename below.
                self._cleanup_temp_files(keep_partial=True)

                # Move .part to final file
                try:
                    if os.path.exists(self.task.full_path):
                        os.remove(self.task.full_path)
                    shutil.move(self.task.temp_path, self.task.full_path)
                except Exception as e:
                    self.task.error_message = f"Lỗi hoàn tất tệp: {e}"
                    self.task.status = TaskStatus.ERROR
                    return False

                # Drop the shared temp folder when no other task is using it.
                try:
                    os.rmdir(self.task.temp_dir)
                except OSError:
                    pass

                # Optional automatic checksum verification
                checksum = getattr(self.task, "checksum", "") or ""
                if checksum:
                    algo = getattr(self.task, "checksum_algo", "sha256") or "sha256"
                    valid = await verify_file_checksum(self.task.full_path, checksum, algo)
                    if not valid:
                        self.task.error_message = f"Cảnh báo: Mã băm {algo.upper()} không khớp với giá trị mong đợi"
                        logger.warning(f"Task {self.task.id}: checksum mismatch for {self.task.full_path}")

                if self.on_progress:
                    self.on_progress(self.task)
                return True
            else:
                if self.task.status != TaskStatus.ERROR:
                    self.task.status = TaskStatus.PAUSED
                self._save_metadata()
                return False

    async def _speed_monitor(self) -> None:
        """Periodically update speed and ETA, and trigger progress callbacks."""
        while not (self._pause_requested.is_set() or self._cancel_requested.is_set()):
            await asyncio.sleep(0.5)
            now = time.time()
            elapsed = now - self._last_speed_check_time
            if elapsed >= 0.5:
                curr_bytes = sum(c.downloaded_bytes for c in self.task.chunks)
                delta = max(0, curr_bytes - self._last_downloaded_bytes)
                self.task.speed = delta / elapsed
                self.task.downloaded_bytes = curr_bytes
                self._last_downloaded_bytes = curr_bytes
                self._last_speed_check_time = now

                if self.on_progress:
                    self.on_progress(self.task)

    async def _worker(self, client: httpx.AsyncClient, worker_id: int) -> None:
        """Worker coroutine that claims pending chunks until none are left.

        The chunk list is fixed before the workers start, so the number of
        concurrent connections never exceeds the configured limit.
        """
        idle_retries = 0
        while not (
            self._pause_requested.is_set()
            or self._cancel_requested.is_set()
            or self.task.status == TaskStatus.ERROR
        ):
            # 1. Claim a pending chunk
            chunk = await self._get_pending_chunk()

            # 2. If no chunk available right now
            if not chunk:
                async with self._chunks_lock:
                    all_done = all(c.status == "completed" for c in self.task.chunks)
                if all_done:
                    break

                # Wait briefly: another worker may be retrying a failed chunk
                idle_retries += 1
                if idle_retries > 6:
                    break
                await asyncio.sleep(0.5)
                continue

            idle_retries = 0
            # 3. Download this chunk
            await self._download_chunk(client, chunk)

    async def _get_pending_chunk(self) -> Optional[Chunk]:
        """Find and claim a chunk that is pending or needs retry."""
        async with self._chunks_lock:
            # Priority 1: Pending chunks
            # (end_byte < 0 means unknown size: single stream until EOF)
            for c in self.task.chunks:
                if c.status == "pending" and (c.remaining_bytes > 0 or c.end_byte < 0):
                    c.status = "downloading"
                    return c
            # Priority 2: Failed chunks for automatic retry (bounded)
            for c in self.task.chunks:
                if c.status == "failed" and (c.remaining_bytes > 0 or c.end_byte < 0):
                    if self._fail_counts.get(c.chunk_id, 0) >= MAX_CHUNK_RETRIES:
                        continue
                    c.status = "downloading"
                    return c
        return None

    def _register_failure(self, chunk: Chunk, reason: str) -> None:
        """Mark chunk failed; after MAX_CHUNK_RETRIES the whole task becomes ERROR."""
        chunk.status = "failed"
        count = self._fail_counts.get(chunk.chunk_id, 0) + 1
        self._fail_counts[chunk.chunk_id] = count
        if count >= MAX_CHUNK_RETRIES:
            self.task.error_message = f"Tải thất bại sau {count} lần thử ({reason})"
            self.task.status = TaskStatus.ERROR

    async def _download_chunk(self, client: httpx.AsyncClient, chunk: Chunk) -> None:
        """Download assigned byte range and stream into non-blocking disk writer."""
        headers = dict(self.task.headers)
        headers.setdefault("Accept-Encoding", "identity")
        if self.task.supports_range and chunk.end_byte >= chunk.current_pos:
            headers["Range"] = f"bytes={chunk.current_pos}-{chunk.end_byte}"
        elif not self.task.supports_range:
            # Server ignores Range: a retry must restart the stream from byte 0
            chunk.current_pos = chunk.start_byte
            if self._disk_writer:
                await self._disk_writer.truncate(0)

        chunk.status = "downloading"
        chunk_last_time = time.time()
        chunk_last_bytes = chunk.downloaded_bytes

        # Jittered exponential backoff for retries
        fail_count = self._fail_counts.get(chunk.chunk_id, 0)
        if fail_count > 0:
            backoff = min(0.3 * (1.5 ** fail_count) + random.uniform(0.1, 0.3), 3.0)
            await asyncio.sleep(backoff)

        try:
            async with client.stream("GET", self.task.url, headers=headers) as resp:
                if resp.status_code not in (200, 206):
                    self._register_failure(chunk, f"HTTP {resp.status_code}")
                    return

                async for block in resp.aiter_bytes(chunk_size=READ_BUFFER_SIZE):
                    if self._pause_requested.is_set() or self._cancel_requested.is_set():
                        break

                    block_len = len(block)
                    if block_len == 0:
                        continue

                    # Direct write via non-blocking async queue
                    if self._disk_writer:
                        await self._disk_writer.put(chunk.current_pos, block)

                    chunk.current_pos += block_len

                    # Stop if reached end of dynamically shortened chunk
                    if self.task.supports_range and chunk.current_pos > chunk.end_byte:
                        break

                    # Update local chunk speed
                    now = time.time()
                    elapsed = now - chunk_last_time
                    if elapsed >= 0.5:
                        chunk.speed = (chunk.downloaded_bytes - chunk_last_bytes) / elapsed
                        chunk_last_bytes = chunk.downloaded_bytes
                        chunk_last_time = now

                    # Bandwidth throttling when speed_limit_kbps is configured
                    if self.speed_limit_kbps > 0:
                        active_cnt = max(
                            1,
                            sum(1 for c in self.task.chunks if c.status == "downloading"),
                        )
                        per_worker_bps = (self.speed_limit_kbps * 1024.0) / active_cnt
                        if per_worker_bps > 0 and chunk.speed > per_worker_bps:
                            sleep_sec = min(0.25, block_len / per_worker_bps)
                            if sleep_sec > 0.005:
                                await asyncio.sleep(sleep_sec)

                # Verify completion
                if chunk.current_pos > chunk.end_byte or (
                    not self.task.supports_range and not self._pause_requested.is_set()
                ):
                    chunk.status = "completed"
                    chunk.speed = 0.0
                elif not self._pause_requested.is_set() and not self._cancel_requested.is_set():
                    self._register_failure(chunk, "kết nối bị ngắt giữa chừng")

        except Exception as e:
            logger.debug(f"Chunk {chunk.chunk_id} download error: {e}")
            if self._disk_writer and self._disk_writer.error:
                # Disk failure cannot be fixed by retrying the chunk.
                chunk.status = "failed"
                self.task.status = TaskStatus.ERROR
                self.task.error_message = f"Lỗi ghi đĩa: {self._disk_writer.error}"
            elif not self._pause_requested.is_set():
                self._register_failure(chunk, f"{type(e).__name__}: {e}")
        finally:
            if self.on_chunk_update:
                self.on_chunk_update(self.task)
