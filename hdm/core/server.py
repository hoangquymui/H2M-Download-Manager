"""HDM Local HTTP Integration Server.
Listens for incoming download links and requests from the Browser Extension.
Uses pure asyncio stream server without external web framework dependencies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Callable, Dict, List, Optional

from hdm.core.engine import is_streaming_url
from hdm.core.manager import DownloadQueueManager
from hdm.utils.category import FileCategory

logger = logging.getLogger("HDM.Server")

SERVER_VERSION = "1.1.0"
MAX_BODY_BYTES = 12 * 1024 * 1024         # Download payloads + captured HLS playlist
MAX_MANIFEST_BYTES = 6 * 1024 * 1024
MAX_QUALITIES_BYTES = 5 * 1024 * 1024

# Requests coming from real web pages are rejected; only browser extensions
# (and non-browser local clients that send no Origin) may talk to this server.
_EXTENSION_ORIGIN_RE = re.compile(r"^(?:chrome|moz)-extension://[A-Za-z0-9._-]+$")


class BrowserIntegrationServer:
    """Lightweight async HTTP server for browser extension communication."""

    def __init__(
        self,
        manager: DownloadQueueManager,
        config_manager: Optional[Any] = None,
        host: str = "127.0.0.1",
        port: int = 9618,
        on_show_requested: Optional[Callable[[], None]] = None,
        on_download_requested: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.manager = manager
        self.config_manager = config_manager
        self.host = host
        self.port = port
        self.on_show_requested = on_show_requested
        self.on_download_requested = on_download_requested
        self._server: Optional[asyncio.Server] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # None means "aborted" (server stopping), so the extension keeps its
        # browser download instead of treating it as a user cancellation.
        self._pending_dialogs: Dict[str, asyncio.Future] = {}

    async def start(self) -> None:
        """Start listening on localhost port."""
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
            )
            self._loop = asyncio.get_running_loop()
            logger.info(f"HDM Browser Integration Server listening on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start integration server on port {self.port}: {e}")

    async def stop(self) -> None:
        """Stop integration server."""
        self._abort_pending_dialogs()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._loop = None
            logger.info("HDM Browser Integration Server stopped")

    def _abort_pending_dialogs(self) -> None:
        """Release waiting HTTP requests when the server stops or is reconfigured."""
        for future in self._pending_dialogs.values():
            if not future.done():
                future.set_result(None)
        self._pending_dialogs.clear()

    def resolve_dialog(self, request_id: str, accepted: Optional[bool]) -> None:
        """Resolve a pending confirmation dialog. Safe to call from the GUI thread.

        None means the decision could not be applied (e.g. adding the task
        failed), so the extension keeps its browser download.
        """
        if not request_id:
            return
        loop = self._loop
        future = self._pending_dialogs.get(request_id)
        if not loop or future is None or future.done():
            return

        result = None if accepted is None else bool(accepted)

        def _resolve() -> None:
            if not future.done():
                future.set_result(result)

        try:
            loop.call_soon_threadsafe(_resolve)
        except RuntimeError:
            pass

    async def _request_dialog_confirmation(self, req_data: Dict[str, Any]) -> Optional[bool]:
        """Show the confirmation dialog and wait until the user decides.

        There is no timeout: the dialog stays open until the user answers it,
        and the browser copy stays paused meanwhile. Returns None when the
        server is shut down before a decision is made.
        """
        loop = asyncio.get_running_loop()
        request_id = uuid.uuid4().hex
        future: asyncio.Future = loop.create_future()
        self._pending_dialogs[request_id] = future
        req_data["request_id"] = request_id
        try:
            if self.on_download_requested:
                self.on_download_requested(req_data)
            return await future
        finally:
            self._pending_dialogs.pop(request_id, None)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Process incoming HTTP requests from the browser extension."""
        try:
            request_line = await reader.readline()
            if not request_line:
                return

            line_str = request_line.decode("utf-8", errors="ignore").strip()
            parts = line_str.split()
            if len(parts) < 2:
                return

            method = parts[0].upper()
            path = parts[1]

            headers: Dict[str, str] = {}
            content_length = 0
            while True:
                header_line = await reader.readline()
                if not header_line or header_line == b"\r\n" or header_line == b"\n":
                    break
                header_str = header_line.decode("utf-8", errors="ignore").strip()
                if ":" in header_str:
                    k, v = header_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        try:
                            content_length = int(v.strip())
                        except ValueError:
                            pass

            origin = headers.get("origin", "")
            allowed_origin = origin if origin and _EXTENSION_ORIGIN_RE.match(origin) else ""

            # Block requests initiated by regular web pages (CSRF / DNS rebinding).
            if origin and not allowed_origin:
                self._send_json(
                    writer,
                    {"ok": False, "error": "Forbidden origin"},
                    status=403,
                    status_text="Forbidden",
                )
                return

            # CORS preflight
            if method == "OPTIONS":
                self._send_response(
                    writer,
                    status=204,
                    status_text="No Content",
                    body="",
                    origin=allowed_origin,
                )
                return

            if content_length > MAX_BODY_BYTES:
                self._send_json(
                    writer,
                    {"ok": False, "error": "Request body too large"},
                    status=413,
                    status_text="Payload Too Large",
                    origin=allowed_origin,
                )
                return

            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            if method == "GET" and path == "/api/v1/status":
                resp_data = {
                    "status": "ok",
                    "app": "HDM",
                    "version": SERVER_VERSION,
                    "active_tasks": self.manager.get_active_count(),
                    "total_speed": self.manager.get_total_speed(),
                }
                self._send_json(writer, resp_data, origin=allowed_origin)

            elif method == "POST" and path == "/api/v1/download":
                try:
                    payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                    url = (payload.get("url") or "").strip()
                    if not url:
                        self._send_json(
                            writer,
                            {"ok": False, "error": "Missing URL"},
                            status=400,
                            origin=allowed_origin,
                        )
                        return
                    if not url.lower().startswith(("http://", "https://")):
                        self._send_json(
                            writer,
                            {"ok": False, "error": "Only http(s) URLs are accepted"},
                            status=400,
                            origin=allowed_origin,
                        )
                        return

                    manifest = payload.get("manifest", "")
                    if (
                        not isinstance(manifest, str)
                        or not manifest.strip()
                        or "#EXTM3U" not in manifest
                        or len(manifest) > MAX_MANIFEST_BYTES
                    ):
                        manifest = ""
                    else:
                        manifest = manifest.strip()

                    qualities = self._sanitize_qualities(payload.get("qualities"))

                    # blob: playlists exist only inside the browser tab, so yt-dlp
                    # can never fetch them. Fall back to the highest resolved
                    # per-quality playlist captured alongside.
                    if manifest and self._has_blob_uris(manifest):
                        manifest = self._highest_quality_manifest(qualities)

                    filename = payload.get("filename")
                    custom_headers: Dict[str, str] = {}
                    for key, header in (("user_agent", "User-Agent"), ("referer", "Referer"), ("cookies", "Cookie")):
                        value = payload.get(key)
                        if isinstance(value, str) and value.strip():
                            custom_headers[header] = value.strip()

                    quality = payload.get("quality", "")
                    format_type = payload.get("format", "")
                    category = payload.get("category", "")
                    if not category:
                        if format_type == "mp3" or quality in ("128", "192", "320") or (filename and filename.lower().endswith(".mp3")):
                            category = FileCategory.AUDIO.value
                        elif manifest or is_streaming_url(url) or format_type == "mp4" or quality in ("1080", "720", "480", "360"):
                            category = FileCategory.VIDEO.value

                    show_dialog = True
                    if self.config_manager and hasattr(self.config_manager, "config"):
                        show_dialog = getattr(self.config_manager.config, "show_download_dialog", True)

                    if show_dialog and self.on_download_requested:
                        req_data = {
                            "url": url,
                            "filename": filename or "",
                            "headers": custom_headers,
                            "quality": quality,
                            "category": category,
                            "manifest": manifest,
                            "qualities": qualities,
                            "is_captured": True,
                        }
                        accepted = await self._request_dialog_confirmation(req_data)
                        if accepted is True:
                            self._send_json(writer, {"ok": True, "mode": "auto"}, origin=allowed_origin)
                        elif accepted is False:
                            self._send_json(
                                writer,
                                {"ok": False, "mode": "cancelled"},
                                origin=allowed_origin,
                            )
                        else:
                            # Undecided (server shutting down): let the extension
                            # keep the browser download instead of dropping it.
                            self._send_json(
                                writer,
                                {"ok": False, "mode": "error"},
                                origin=allowed_origin,
                            )
                    else:
                        task = self.manager.add_task(
                            url=url,
                            filename=filename,
                            headers=custom_headers if custom_headers else None,
                            auto_start=True,
                            quality=quality,
                            category=category,
                            manifest=manifest or None,
                        )
                        self._send_json(
                            writer,
                            {"ok": True, "mode": "auto", "task_id": task.id},
                            origin=allowed_origin,
                        )
                except Exception as e:
                    self._send_json(
                        writer,
                        {"ok": False, "error": str(e)},
                        status=500,
                        status_text="Internal Server Error",
                        origin=allowed_origin,
                    )

            elif method == "POST" and path == "/api/v1/show":
                if self.on_show_requested:
                    self.on_show_requested()
                self._send_json(writer, {"ok": True}, origin=allowed_origin)

            else:
                self._send_json(
                    writer,
                    {"error": "Not Found"},
                    status=404,
                    status_text="Not Found",
                    origin=allowed_origin,
                )

        except Exception as e:
            logger.debug(f"HTTP Server client handling error: {e}")
        finally:
            try:
                await writer.drain()
            except Exception:
                pass
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    def _has_blob_uris(manifest: str) -> bool:
        """True when the playlist references in-page blob: URLs (unfetchable)."""
        for line in manifest.splitlines():
            value = line.strip()
            if value and not value.startswith("#") and value.startswith("blob:"):
                return True
        return False

    @staticmethod
    def _highest_quality_manifest(qualities: List[Dict[str, str]]) -> str:
        """Pick the highest captured rendition (qualities come sorted by height)."""
        best = ""
        best_height = -1
        for item in qualities:
            height = item.get("height", "")
            value = int(height) if height.isdigit() else -1
            if value > best_height:
                best, best_height = item.get("manifest", ""), value
        return best

    @staticmethod
    def _sanitize_qualities(raw: Any) -> List[Dict[str, str]]:
        """Keep only valid per-quality playlists sent by the extension."""
        if not isinstance(raw, list):
            return []
        cleaned: List[Dict[str, str]] = []
        total = 0
        for item in raw[:8]:
            if not isinstance(item, dict):
                continue
            manifest = item.get("manifest")
            if not isinstance(manifest, str) or "#EXTM3U" not in manifest:
                continue
            manifest = manifest.strip()
            if not manifest or len(manifest) > MAX_MANIFEST_BYTES:
                continue
            if total + len(manifest) > MAX_QUALITIES_BYTES:
                break
            total += len(manifest)
            cleaned.append(
                {
                    "label": str(item.get("label") or "").strip()[:24],
                    "height": str(item.get("height") or "").strip()[:8],
                    "manifest": manifest,
                }
            )
        cleaned.sort(
            key=lambda q: int(q["height"]) if q["height"].isdigit() else 0,
            reverse=True,
        )
        return cleaned

    def _send_json(
        self,
        writer: asyncio.StreamWriter,
        data: Dict[str, Any],
        status: int = 200,
        status_text: str = "OK",
        origin: str = "",
    ) -> None:
        """Send JSON response with restricted CORS headers."""
        body = json.dumps(data, ensure_ascii=False)
        self._send_response(
            writer,
            status=status,
            status_text=status_text,
            content_type="application/json; charset=utf-8",
            body=body,
            origin=origin,
        )

    def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status: int = 200,
        status_text: str = "OK",
        content_type: str = "text/plain",
        body: str = "",
        origin: str = "",
    ) -> None:
        """Format and write raw HTTP response to socket."""
        body_bytes = body.encode("utf-8")
        lines = [
            f"HTTP/1.1 {status} {status_text}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body_bytes)}",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, X-HDM-Client, Authorization, Access-Control-Request-Private-Network",
            "Access-Control-Allow-Private-Network: true",
            "Cache-Control: no-store",
            "Connection: close",
        ]
        if origin:
            lines.append(f"Access-Control-Allow-Origin: {origin}")
            lines.append("Vary: Origin")
        lines.extend(["", ""])
        header_data = "\r\n".join(lines).encode("utf-8")
        writer.write(header_data + body_bytes)
