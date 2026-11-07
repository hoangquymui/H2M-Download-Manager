"""Test the download engine with a local HTTP Range server.
"""

import asyncio
import base64
import os
import socket
import socketserver
import sys
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hdm.core.engine import DownloadEngine
from hdm.core.models import DownloadTask, TaskStatus

TEST_DATA = b"HDM_TEST_PAYLOAD_" * 1000000  # ~17 MB, enough for 4 chunks


class RangeTestHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(TEST_DATA)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        if not range_header:
            self.send_response(200)
            self.send_header("Content-Length", str(len(TEST_DATA)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(TEST_DATA)
            return

        # Parse Range: bytes=start-end
        parts = range_header.replace("bytes=", "").split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else len(TEST_DATA) - 1
        end = min(end, len(TEST_DATA) - 1)

        chunk = TEST_DATA[start : end + 1]

        self.send_response(206)
        self.send_header("Content-Range", f"bytes {start}-{end}/{len(TEST_DATA)}")
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(chunk)

    def log_message(self, format, *args):
        pass  # Quiet test logging


class _ForwardProxyHandler(socketserver.BaseRequestHandler):
    """Minimal forwarding proxy: absolute-URI requests plus CONNECT tunnels."""

    def handle(self):
        self.request.settimeout(15)
        data = b""
        while b"\r\n\r\n" not in data:
            part = self.request.recv(65536)
            if not part:
                return
            data += part
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        try:
            method, target, version = lines[0].split(b" ", 2)
        except ValueError:
            return

        if method == b"CONNECT":
            host, _, port = target.decode().partition(":")
            self.server.requests.append(("CONNECT", target.decode()))
            upstream = socket.create_connection((host, int(port or "443")), timeout=15)
            try:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _relay_both(self.request, upstream)
            finally:
                upstream.close()
            return

        parsed = urlsplit(target.decode())
        self.server.requests.append((method.decode(), target.decode()))
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        lines[0] = f"{method.decode()} {path} {version.decode()}".encode()
        upstream = socket.create_connection(
            (parsed.hostname, parsed.port or 80), timeout=15
        )
        try:
            upstream.sendall(b"\r\n".join(lines) + b"\r\n\r\n" + body)
            while True:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                self.request.sendall(chunk)
        finally:
            upstream.close()


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data += chunk
    return data


def _relay_both(client: socket.socket, upstream: socket.socket) -> None:
    def pump(src: socket.socket, dst: socket.socket) -> None:
        try:
            while True:
                chunk = src.recv(65536)
                if not chunk:
                    break
                dst.sendall(chunk)
        except OSError:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    worker = threading.Thread(target=pump, args=(upstream, client), daemon=True)
    worker.start()
    pump(client, upstream)
    worker.join(timeout=5)


class _Socks5Handler(socketserver.BaseRequestHandler):
    """Minimal SOCKS5 proxy (no auth, CONNECT only) for the proxy test."""

    def handle(self):
        sock = self.request
        sock.settimeout(15)
        try:
            version, method_count = _recv_exact(sock, 2)
            if version != 5:
                return
            _recv_exact(sock, method_count)
            sock.sendall(b"\x05\x00")

            version, command, _, address_type = _recv_exact(sock, 4)
            if version != 5 or command != 1:
                return
            if address_type == 1:
                host = socket.inet_ntoa(_recv_exact(sock, 4))
            elif address_type == 3:
                host = _recv_exact(sock, _recv_exact(sock, 1)[0]).decode()
            elif address_type == 4:
                host = socket.inet_ntop(socket.AF_INET6, _recv_exact(sock, 16))
            else:
                return
            port = int.from_bytes(_recv_exact(sock, 2), "big")
            self.server.requests.append((host, port))

            try:
                upstream = socket.create_connection((host, port), timeout=15)
            except OSError:
                sock.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            try:
                sock.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
                _relay_both(sock, upstream)
            finally:
                upstream.close()
        except (ConnectionError, OSError):
            pass


class _ForwardProxy(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests = []


async def run_engine_test():
    # Start local range server on random port
    server = HTTPServer(("127.0.0.1", 0), RangeTestHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/sample_payload.bin"

    with tempfile.TemporaryDirectory() as td:
        task = DownloadTask(
            url=url,
            filename="sample_payload.bin",
            save_dir=td,
            num_connections=4,
        )

        progress_updates = []
        chunk_updates = []

        engine = DownloadEngine(
            task=task,
            on_progress=lambda t: progress_updates.append(t.downloaded_bytes),
            on_chunk_update=lambda t: chunk_updates.append(len(t.chunks)),
        )

        success = await engine.run()

        assert success, f"Download failed: {task.error_message}"
        assert task.status == TaskStatus.COMPLETED

        final_path = os.path.join(td, "sample_payload.bin")
        assert os.path.exists(final_path), "Target file was not created!"

        # Every temporary artifact lives in one hidden folder that is removed
        # once the download completes.
        assert not os.path.exists(os.path.join(td, ".hdm_tmp")), "Temp folder left behind!"
        # The chunk list is fixed up front: no dynamic segment splitting means
        # the thread count never grows past the configured value.
        assert len(task.chunks) <= task.num_connections, "More chunks than connections!"
        assert not chunk_updates or max(chunk_updates) == len(task.chunks)

        with open(final_path, "rb") as f:
            downloaded_bytes = f.read()

        assert len(downloaded_bytes) == len(TEST_DATA), "File size mismatch!"
        assert downloaded_bytes == TEST_DATA, "Content integrity mismatch!"

        print(f"✅ Engine test passed! Downloaded {len(downloaded_bytes):,} bytes across {len(task.chunks)} chunks.")

    server.shutdown()


AUTH_USER = "alice"
AUTH_PASS = "s3cret"


class AuthRangeTestHandler(RangeTestHandler):
    """Range server that only answers with HTTP Basic credentials."""

    def _denied(self) -> bool:
        expected = "Basic " + base64.b64encode(
            f"{AUTH_USER}:{AUTH_PASS}".encode()
        ).decode()
        if self.headers.get("Authorization") == expected:
            return False
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="hdm-test"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def do_HEAD(self):
        if not self._denied():
            super().do_HEAD()

    def do_GET(self):
        if not self._denied():
            super().do_GET()


def test_host_scoped_auth():
    from hdm.core.engine import HostScopedBasicAuth

    auth = HostScopedBasicAuth("example.com", "user", "pass")
    other = next(auth.auth_flow(httpx.Request("GET", "https://cdn.other.net/key.bin")))
    assert "authorization" not in other.headers, "credentials leaked to another host"

    same = next(auth.auth_flow(httpx.Request("GET", "https://example.com/file.zip")))
    expected = "Basic " + base64.b64encode(b"user:pass").decode()
    assert same.headers["authorization"] == expected

    upper = next(auth.auth_flow(httpx.Request("GET", "https://EXAMPLE.com/x")))
    assert upper.headers["authorization"] == expected
    print("✅ host-scoped auth passed!")


async def run_auth_test():
    """A Basic-auth protected download works only when credentials are supplied."""
    server = HTTPServer(("127.0.0.1", 0), AuthRangeTestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/protected.bin"

    with tempfile.TemporaryDirectory() as td:
        task = DownloadTask(url=url, filename="protected.bin", save_dir=td, num_connections=4)
        engine = DownloadEngine(task=task)
        assert not await engine.run(), "download without credentials must fail"
        assert task.status == TaskStatus.ERROR
        assert not os.path.exists(os.path.join(td, "protected.bin"))

    with tempfile.TemporaryDirectory() as td:
        task = DownloadTask(url=url, filename="protected.bin", save_dir=td, num_connections=4)
        engine = DownloadEngine(task=task, credentials=(AUTH_USER, AUTH_PASS))
        success = await engine.run()
        assert success, f"authenticated download failed: {task.error_message}"
        with open(os.path.join(td, "protected.bin"), "rb") as f:
            assert f.read() == TEST_DATA
        print("✅ Basic-auth download passed!")

    server.shutdown()


async def _download_through(url: str, proxy_url: str, filename: str, td: str) -> DownloadTask:
    task = DownloadTask(url=url, filename=filename, save_dir=td, num_connections=4)
    engine = DownloadEngine(task=task, proxy_url=proxy_url)
    success = await engine.run()
    assert success, f"Download via {proxy_url} failed: {task.error_message}"
    with open(os.path.join(td, filename), "rb") as f:
        assert f.read() == TEST_DATA, f"Content mismatch through {proxy_url}"
    return task


async def run_proxy_test():
    """Downloads configured with a proxy must route every request through it."""
    origin = HTTPServer(("127.0.0.1", 0), RangeTestHandler)
    threading.Thread(target=origin.serve_forever, daemon=True).start()

    http_proxy = _ForwardProxy(("127.0.0.1", 0), _ForwardProxyHandler)
    threading.Thread(target=http_proxy.serve_forever, daemon=True).start()
    socks_proxy = _ForwardProxy(("127.0.0.1", 0), _Socks5Handler)
    threading.Thread(target=socks_proxy.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{origin.server_port}/proxied_payload.bin"

    with tempfile.TemporaryDirectory() as td_http, tempfile.TemporaryDirectory() as td_socks:
        await _download_through(
            url, f"http://127.0.0.1:{http_proxy.server_address[1]}", "http_proxy.bin", td_http
        )
        assert http_proxy.requests, "HTTP proxy received no requests — traffic bypassed it"
        assert all(
            target.startswith("http://127.0.0.1:")
            for _, target in http_proxy.requests
            if not target.startswith("CONNECT")
        )

        await _download_through(
            url, f"socks5://127.0.0.1:{socks_proxy.server_address[1]}", "socks_proxy.bin", td_socks
        )
        assert socks_proxy.requests, "SOCKS5 proxy received no connections"

        print(
            f"✅ Proxy test passed! HTTP: {len(http_proxy.requests)} requests, "
            f"SOCKS5: {len(socks_proxy.requests)} connections."
        )

    http_proxy.shutdown()
    http_proxy.server_close()
    socks_proxy.shutdown()
    socks_proxy.server_close()
    origin.shutdown()


def test_ytdlp_receives_proxy(monkeypatch):
    """The streaming path must hand the configured proxy to yt-dlp."""
    import yt_dlp

    captured = []

    class FakeYDL:
        def __init__(self, opts):
            captured.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            raise RuntimeError("stop after options were built")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)

    proxy = "socks5://127.0.0.1:1080"
    with tempfile.TemporaryDirectory() as td:
        task = DownloadTask(
            url="https://www.youtube.com/watch?v=test",
            filename="video.mp4",
            save_dir=td,
            num_connections=4,
        )
        engine = DownloadEngine(task=task, proxy_url=proxy, credentials=("site-user", "site-pass"))
        asyncio.run(engine._download_streaming_video())

    assert captured, "yt-dlp was never configured"
    assert captured[0].get("proxy") == proxy
    assert captured[0].get("username") == "site-user"
    assert captured[0].get("password") == "site-pass"
    print("✅ yt-dlp proxy and credential options passed!")


def test_basic_auth_download():
    asyncio.run(run_auth_test())


if __name__ == "__main__":
    asyncio.run(run_engine_test())
    asyncio.run(run_proxy_test())
    asyncio.run(run_auth_test())
