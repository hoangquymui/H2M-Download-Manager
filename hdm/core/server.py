"""HDM Local HTTP Integration Server.
Listens for incoming download links and requests from the Browser Extension.
Uses pure asyncio stream server without external web framework dependencies.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional

from hdm.core.manager import DownloadQueueManager

logger = logging.getLogger("HDM.Server")


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

    async def start(self) -> None:
        """Start listening on localhost port."""
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
            )
            logger.info(f"HDM Browser Integration Server listening on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start integration server on port {self.port}: {e}")

    async def stop(self) -> None:
        """Stop integration server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("HDM Browser Integration Server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Process incoming HTTP requests from the browser extension."""
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                await writer.wait_closed()
                return

            line_str = request_line.decode("utf-8", errors="ignore").strip()
            parts = line_str.split()
            if len(parts) < 2:
                writer.close()
                await writer.wait_closed()
                return

            method = parts[0].upper()
            path = parts[1]

            # Read headers
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

            # Read body if present
            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            # Handle CORS preflight
            if method == "OPTIONS":
                self._send_response(
                    writer,
                    status=204,
                    status_text="No Content",
                    body="",
                )
                return

            # Route requests
            if method == "GET" and path == "/api/v1/status":
                resp_data = {
                    "status": "ok",
                    "app": "HDM",
                    "version": "1.0.0",
                    "active_tasks": self.manager.get_active_count(),
                    "total_speed": self.manager.get_total_speed(),
                }
                self._send_json(writer, resp_data)

            elif method == "POST" and path == "/api/v1/download":
                try:
                    payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                    url = payload.get("url")
                    if not url:
                        self._send_json(writer, {"ok": False, "error": "Missing URL"}, status=400)
                        return

                    filename = payload.get("filename")
                    custom_headers: Dict[str, str] = {}
                    if "user_agent" in payload:
                        custom_headers["User-Agent"] = payload["user_agent"]
                    if "referer" in payload:
                        custom_headers["Referer"] = payload["referer"]
                    if "cookies" in payload:
                        custom_headers["Cookie"] = payload["cookies"]

                    show_dialog = True
                    if self.config_manager and hasattr(self.config_manager, "config"):
                        show_dialog = getattr(self.config_manager.config, "show_download_dialog", True)

                    if show_dialog and self.on_download_requested:
                        req_data = {
                            "url": url,
                            "filename": filename or "",
                            "headers": custom_headers,
                        }
                        self.on_download_requested(req_data)
                        self._send_json(writer, {"ok": True, "mode": "dialog"})
                    else:
                        task = self.manager.add_task(
                            url=url,
                            filename=filename,
                            headers=custom_headers if custom_headers else None,
                            auto_start=True,
                        )
                        self._send_json(writer, {"ok": True, "task_id": task.id})
                except Exception as e:
                    self._send_json(writer, {"ok": False, "error": str(e)}, status=500)

            elif method == "POST" and path == "/api/v1/show":
                if self.on_show_requested:
                    self.on_show_requested()
                self._send_json(writer, {"ok": True})

            else:
                self._send_json(writer, {"error": "Not Found"}, status=404, status_text="Not Found")

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

    def _send_json(
        self,
        writer: asyncio.StreamWriter,
        data: Dict[str, Any],
        status: int = 200,
        status_text: str = "OK",
    ) -> None:
        """Send JSON response with proper CORS headers."""
        body = json.dumps(data, ensure_ascii=False)
        self._send_response(
            writer,
            status=status,
            status_text=status_text,
            content_type="application/json; charset=utf-8",
            body=body,
        )

    def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status: int = 200,
        status_text: str = "OK",
        content_type: str = "text/plain",
        body: str = "",
    ) -> None:
        """Format and write raw HTTP response to socket."""
        body_bytes = body.encode("utf-8")
        lines = [
            f"HTTP/1.1 {status} {status_text}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body_bytes)}",
            "Access-Control-Allow-Origin: *",
            "Access-Control-Allow-Methods: GET, POST, OPTIONS",
            "Access-Control-Allow-Headers: Content-Type, X-HDM-Client, Authorization, Access-Control-Request-Private-Network, *",
            "Access-Control-Allow-Private-Network: true",
            "Connection: close",
            "",
            "",
        ]
        header_data = "\r\n".join(lines).encode("utf-8")
        writer.write(header_data + body_bytes)
