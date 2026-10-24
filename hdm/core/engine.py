"""HDM Download Engine.
High-performance asynchronous multi-connection downloading with Dynamic Segmentation (Work Stealing).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from hdm.core.models import Chunk, DownloadTask, TaskStatus
from hdm.core.sparse_file import preallocate_file
from hdm.utils.formatters import extract_filename_from_url

logger = logging.getLogger("HDM.Engine")

MIN_CHUNK_SIZE = 1048576       # 1 MB
MIN_STEAL_SIZE = 2097152       # 2 MB minimum remaining to split in half
READ_BUFFER_SIZE = 65536       # 64 KB read buffer
MAX_CHUNK_RETRIES = 5          # give up on a segment after this many failures

STREAMING_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "facebook.com/watch",
    "facebook.com/reel",
    "fb.watch",
    "instagram.com",
    "twitter.com",
    "x.com",
    "vimeo.com",
    "dailymotion.com",
    "bilibili.com",
    "twitch.tv",
    "soundcloud.com",
)


def is_streaming_url(url: str) -> bool:
    """Check if the URL belongs to a streaming service supported by yt-dlp."""
    if not url:
        return False
    u = url.lower()
    return any(d in u for d in STREAMING_DOMAINS)


class DownloadEngine:
    """Core download engine handling dynamic segmentation, streaming, and resume."""

    def __init__(
        self,
        task: DownloadTask,
        on_progress: Optional[Callable[[DownloadTask], None]] = None,
        on_chunk_update: Optional[Callable[[DownloadTask], None]] = None,
    ) -> None:
        self.task = task
        self.on_progress = on_progress
        self.on_chunk_update = on_chunk_update

        self._pause_requested = asyncio.Event()
        self._cancel_requested = asyncio.Event()
        self._chunks_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

        self._file_handle: Optional[Any] = None
        self._fail_counts: Dict[int, int] = {}
        self._last_speed_check_time = time.time()
        self._last_downloaded_bytes = 0

    def pause(self) -> None:
        """Signal the engine to pause downloading."""
        self._pause_requested.set()

    def cancel(self) -> None:
        """Signal the engine to cancel downloading."""
        self._cancel_requested.set()
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

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
        cl = headers.get("content-length")
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

        # Extract filename if currently default
        cd = headers.get("content-disposition", "")
        extracted_name = extract_filename_from_url(str(response.url), cd)
        if extracted_name and extracted_name != "download":
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
            if data.get("total_bytes") == self.task.total_bytes and data.get("chunks"):
                self.task.chunks = [Chunk.from_dict(c) for c in data["chunks"]]
                self.task.update_downloaded_from_chunks()
                return True
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")
        return False

    async def _download_streaming_video(self) -> bool:
        """Download streaming media from YouTube, Facebook, TikTok, etc. using yt_dlp."""
        import yt_dlp
        from hdm.utils.formatters import clean_filename

        self.task.status = TaskStatus.DOWNLOADING
        if self.on_progress:
            self.on_progress(self.task)

        os.makedirs(self.task.save_dir, exist_ok=True)
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
                if self.on_progress:
                    self.on_progress(self.task)

            elif d["status"] == "finished":
                if self.task.total_bytes > 0:
                    self.task.downloaded_bytes = self.task.total_bytes
                self.task.speed = 0.0
                if self.on_progress:
                    self.on_progress(self.task)

        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": out_pattern,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noplaylist": True,
        }
        if self.task.headers:
            ydl_opts["http_headers"] = dict(self.task.headers)

        try:
            def do_dl():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(self.task.url, download=True)

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
                self.task.status = TaskStatus.ERROR
                self.task.error_message = f"Lỗi tải video: {e}"
            if self.on_progress:
                self.on_progress(self.task)
            return False

    async def run(self) -> bool:
        """Execute the download process."""
        self._pause_requested.clear()
        self._cancel_requested.clear()

        # Route streaming video platforms (YouTube, Facebook, etc.) to yt_dlp
        if is_streaming_url(self.task.url):
            return await self._download_streaming_video()

        timeout = httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=30.0)
        limits = httpx.Limits(max_connections=32, max_keepalive_connections=16)

        async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True) as client:
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

            os.makedirs(self.task.save_dir, exist_ok=True)

            # 2. Initialize chunks or load from saved metadata
            if self.task.supports_range and self.task.total_bytes > 0:
                has_meta = self._load_metadata()
                if not has_meta or not self.task.chunks:
                    # Initial partition
                    num_workers = min(
                        self.task.num_connections,
                        max(1, self.task.total_bytes // MIN_CHUNK_SIZE)
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

            # 3. Open target file for direct binary writing
            mode = "r+b" if (self.task.supports_range and os.path.exists(self.task.temp_path)) else "wb"
            try:
                self._file_handle = open(self.task.temp_path, mode)
            except Exception as e:
                self.task.error_message = f"Không thể mở tệp ghi: {e}"
                self.task.status = TaskStatus.ERROR
                return False

            # 4. Launch speed tracking task
            speed_task = asyncio.create_task(self._speed_monitor())

            try:
                # 5. Launch worker tasks with Dynamic Segmentation (Work Stealing)
                num_workers = len(self.task.chunks) if self.task.supports_range else 1
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

                if self._file_handle:
                    self._file_handle.close()
                    self._file_handle = None

            # 6. Check completion status
            if self._cancel_requested.is_set():
                self.task.status = TaskStatus.CANCELLED
                self.task.speed = 0.0
                if os.path.exists(self.task.temp_path):
                    try:
                        os.remove(self.task.temp_path)
                    except Exception:
                        pass
                if os.path.exists(self.task.meta_path):
                    try:
                        os.remove(self.task.meta_path)
                    except Exception:
                        pass
                return False

            if self._pause_requested.is_set():
                self.task.status = TaskStatus.PAUSED
                self.task.speed = 0.0
                self._save_metadata()
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

                # Clean up .hdm_meta file
                if os.path.exists(self.task.meta_path):
                    try:
                        os.remove(self.task.meta_path)
                    except Exception:
                        pass

                # Move .hdm_part to final file
                try:
                    if os.path.exists(self.task.full_path):
                        os.remove(self.task.full_path)
                    shutil.move(self.task.temp_path, self.task.full_path)
                except Exception as e:
                    self.task.error_message = f"Lỗi hoàn tất tệp: {e}"
                    self.task.status = TaskStatus.ERROR
                    return False

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
        """Worker coroutine that claims pending chunks or steals work when idle."""
        while not (self._pause_requested.is_set() or self._cancel_requested.is_set()):
            # 1. Claim a pending chunk
            chunk = await self._get_pending_chunk()

            # 2. If no pending chunk, attempt Dynamic Segmentation (Work Stealing)
            if not chunk and self.task.supports_range:
                chunk = await self._steal_chunk()

            # 3. If still no chunk available, worker can retire
            if not chunk:
                break

            # 4. Download this chunk
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

    async def _steal_chunk(self) -> Optional[Chunk]:
        """Dynamic Segmentation: Steal half of the work from the chunk with maximum remaining bytes."""
        async with self._chunks_lock:
            active_chunks = [
                c for c in self.task.chunks
                if c.status == "downloading" and c.remaining_bytes >= MIN_STEAL_SIZE
            ]
            if not active_chunks:
                return None

            # Pick chunk with largest unfinished remaining bytes
            target = max(active_chunks, key=lambda c: c.remaining_bytes)
            remaining = target.remaining_bytes
            half = remaining // 2

            split_point = target.current_pos + half

            new_chunk = Chunk(
                chunk_id=len(self.task.chunks) + 1,
                start_byte=split_point,
                end_byte=target.end_byte,
                current_pos=split_point,
                status="downloading",
            )
            # Shorten the target chunk
            target.end_byte = split_point - 1
            self.task.chunks.append(new_chunk)

            logger.info(
                f"[Work Stealing] Worker split chunk {target.chunk_id}: "
                f"new chunk {new_chunk.chunk_id} [{new_chunk.start_byte}-{new_chunk.end_byte}]"
            )

            if self.on_chunk_update:
                self.on_chunk_update(self.task)

            return new_chunk

    def _register_failure(self, chunk: Chunk, reason: str) -> None:
        """Mark chunk failed; after MAX_CHUNK_RETRIES the whole task becomes ERROR."""
        chunk.status = "failed"
        count = self._fail_counts.get(chunk.chunk_id, 0) + 1
        self._fail_counts[chunk.chunk_id] = count
        if count >= MAX_CHUNK_RETRIES:
            self.task.error_message = f"Tải thất bại sau {count} lần thử ({reason})"
            self.task.status = TaskStatus.ERROR

    async def _download_chunk(self, client: httpx.AsyncClient, chunk: Chunk) -> None:
        """Download assigned byte range and write directly to file."""
        headers = dict(self.task.headers)
        if self.task.supports_range and chunk.end_byte >= chunk.current_pos:
            headers["Range"] = f"bytes={chunk.current_pos}-{chunk.end_byte}"
        elif not self.task.supports_range:
            # Server ignores Range: a retry must restart the stream from byte 0
            chunk.current_pos = chunk.start_byte
            if self._file_handle:
                async with self._write_lock:
                    self._file_handle.seek(0)
                    self._file_handle.truncate()

        chunk.status = "downloading"
        chunk_last_time = time.time()
        chunk_last_bytes = chunk.downloaded_bytes

        # Backoff before retrying to avoid hammering servers during network glitches
        fail_count = self._fail_counts.get(chunk.chunk_id, 0)
        if fail_count > 0:
            await asyncio.sleep(min(0.5 * fail_count, 2.5))

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

                    # Direct write to file at exact offset
                    async with self._write_lock:
                        if self._file_handle:
                            self._file_handle.seek(chunk.current_pos)
                            self._file_handle.write(block)

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
            if not self._pause_requested.is_set():
                self._register_failure(chunk, f"{type(e).__name__}: {e}")
        finally:
            if self.on_chunk_update:
                self.on_chunk_update(self.task)
