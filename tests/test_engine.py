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


def test_multi_chunk_download():
    asyncio.run(run_engine_test())


def test_proxy_downloads():
    asyncio.run(run_proxy_test())


def test_basic_auth_download():
    asyncio.run(run_auth_test())


def test_probe_non_range_streaming_and_206_wildcard():
    """Probe must stream GET Range fallback (never buffer huge 200 OK body) and ignore 206 Content-Length=1."""

    class NonRangeBigHandler(BaseHTTPRequestHandler):
        fully_sent = False

        def do_HEAD(self):
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(5 * 1024 * 1024))
            self.send_header("Content-Disposition", 'attachment; filename="big_iso.bin"')
            self.end_headers()
            try:
                for _ in range(80):
                    self.wfile.write(b"X" * 65536)
                    self.wfile.flush()
                NonRangeBigHandler.fully_sent = True
            except OSError:
                # Expected: probe closes the stream as soon as headers arrive
                pass

        def log_message(self, format, *args):
            pass

    class Wildcard206Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(405)
            self.end_headers()

        def do_GET(self):
            self.send_response(206)
            self.send_header("Content-Range", "bytes 0-0/*")
            self.send_header("Content-Length", "1")
            self.end_headers()
            self.wfile.write(b"A")

        def log_message(self, format, *args):
            pass

    srv1 = HTTPServer(("127.0.0.1", 0), NonRangeBigHandler)
    threading.Thread(target=srv1.serve_forever, daemon=True).start()
    srv2 = HTTPServer(("127.0.0.1", 0), Wildcard206Handler)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            t1 = DownloadTask(url=f"http://127.0.0.1:{srv1.server_port}/dl", filename="", save_dir=td)
            e1 = DownloadEngine(task=t1)
            async with httpx.AsyncClient() as client:
                assert await e1.probe(client)
            assert t1.total_bytes == 5 * 1024 * 1024
            assert t1.filename == "big_iso.bin"
            assert t1.supports_range is False
            assert NonRangeBigHandler.fully_sent is False

            t2 = DownloadTask(url=f"http://127.0.0.1:{srv2.server_port}/stream.bin", filename="", save_dir=td)
            e2 = DownloadEngine(task=t2)
            async with httpx.AsyncClient() as client:
                assert await e2.probe(client)
            assert t2.supports_range is True
            assert t2.total_bytes == -1, f"206 wildcard must not become 1 byte, got {t2.total_bytes}"

    try:
        asyncio.run(run())
    finally:
        srv1.shutdown()
        srv1.server_close()
        srv2.shutdown()
        srv2.server_close()


def test_multi_chunk_rejects_spurious_200_and_clamps_overflow():
    """Spurious 200 OK on ranged chunks must fail safely; 206 overflow must be clamped to end_byte."""
    payload = os.urandom(3 * 1024 * 1024)  # 3 MB exact random bytes

    class Spurious200Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes=0-"):
                end = int(rng.split("-")[1])
                part = payload[0 : end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes 0-{end}/{len(payload)}")
                self.send_header("Content-Length", str(len(part)))
                self.end_headers()
                self.wfile.write(part)
            else:
                # Buggy CDN sends 200 OK from byte 0 instead of 206
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    class Overflow206Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            rng = self.headers.get("Range", "bytes=0-")
            parts = rng.replace("bytes=", "").split("-")
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else len(payload) - 1
            # Intentionally return extra garbage bytes beyond end_byte
            extra = b"CORRUPT_OVERFLOW!" * 100
            body = payload[start : end + 1] + extra
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    srv_bad = HTTPServer(("127.0.0.1", 0), Spurious200Handler)
    threading.Thread(target=srv_bad.serve_forever, daemon=True).start()
    srv_over = HTTPServer(("127.0.0.1", 0), Overflow206Handler)
    threading.Thread(target=srv_over.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            # 1. Spurious 200 on chunk > 0 must NOT succeed with corrupted data
            t_bad = DownloadTask(
                url=f"http://127.0.0.1:{srv_bad.server_port}/bad.bin",
                filename="bad.bin",
                save_dir=td,
                num_connections=2,
            )
            eng_bad = DownloadEngine(task=t_bad)
            # Fail fast once retry runs; speed up test by checking after 1-2 tries or letting it finish
            # Lowering backoff? Wait: 8 retries is ~12s max; let's pause right after failure registers or let run?
            # Actually let's patch MAX_CHUNK_RETRIES in engine module temporarily? Let's test real behavior quickly!
            import hdm.core.engine as eng_mod
            orig_retries = eng_mod.MAX_CHUNK_RETRIES
            eng_mod.MAX_CHUNK_RETRIES = 2
            try:
                ok = await eng_bad.run()
            finally:
                eng_mod.MAX_CHUNK_RETRIES = orig_retries
            assert not ok
            assert t_bad.status == TaskStatus.ERROR
            assert not os.path.exists(os.path.join(td, "bad.bin"))

            # 2. 206 response sending trailing overflow bytes must be clamped accurately
            t_over = DownloadTask(
                url=f"http://127.0.0.1:{srv_over.server_port}/exact.bin",
                filename="exact.bin",
                save_dir=td,
                num_connections=3,
            )
            eng_over = DownloadEngine(task=t_over)
            assert await eng_over.run(), t_over.error_message
            with open(os.path.join(td, "exact.bin"), "rb") as f:
                assert f.read() == payload

    try:
        asyncio.run(run())
    finally:
        srv_bad.shutdown()
        srv_bad.server_close()
        srv_over.shutdown()
        srv_over.server_close()


def test_non_range_pause_resume_and_truncated_stream():
    """Non-range download must reject truncated EOF, retry cleanly, and support pause->resume."""
    payload = b"NON_RANGE_DATA_" * 150000  # ~2.25 MB

    class NonRangeFlakyHandler(BaseHTTPRequestHandler):
        attempts = 0
        pause_mode = False
        first_chunk_sent = threading.Event()
        release_stream = threading.Event()

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()

        def do_GET(self):
            NonRangeFlakyHandler.attempts += 1
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not NonRangeFlakyHandler.pause_mode and NonRangeFlakyHandler.attempts == 1:
                # Truncate early at ~30% without raising server error
                self.wfile.write(payload[: len(payload) // 3])
                self.wfile.flush()
                return
            if NonRangeFlakyHandler.pause_mode and NonRangeFlakyHandler.attempts == 1:
                # Stream half, signal client, then block until pause is issued
                self.wfile.write(payload[: len(payload) // 2])
                self.wfile.flush()
                NonRangeFlakyHandler.first_chunk_sent.set()
                NonRangeFlakyHandler.release_stream.wait(timeout=3.0)
                return
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), NonRangeFlakyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            # Test 1: Truncated first attempt must retry and succeed with full bytes
            t = DownloadTask(
                url=f"http://127.0.0.1:{srv.server_port}/file.bin",
                filename="file.bin",
                save_dir=td,
                num_connections=4,
            )
            eng = DownloadEngine(task=t)
            assert await eng.run(), t.error_message
            assert NonRangeFlakyHandler.attempts >= 2
            with open(os.path.join(td, "file.bin"), "rb") as f:
                assert f.read() == payload

            # Test 2: Pause mid-stream on non-range task, then resume via new run()
            NonRangeFlakyHandler.attempts = 0
            NonRangeFlakyHandler.pause_mode = True
            NonRangeFlakyHandler.first_chunk_sent.clear()
            NonRangeFlakyHandler.release_stream.clear()
            t2 = DownloadTask(
                url=f"http://127.0.0.1:{srv.server_port}/file2.bin",
                filename="file2.bin",
                save_dir=td,
                num_connections=1,
            )
            eng2 = DownloadEngine(task=t2)
            run_task = asyncio.create_task(eng2.run())
            while not NonRangeFlakyHandler.first_chunk_sent.is_set() and not run_task.done():
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.05)
            eng2.pause()
            NonRangeFlakyHandler.release_stream.set()
            ok = await run_task
            assert not ok and t2.status == TaskStatus.PAUSED

            # Resume same task (chunks list is non-empty with old state)
            NonRangeFlakyHandler.pause_mode = False
            eng2_resume = DownloadEngine(task=t2)
            assert await eng2_resume.run(), t2.error_message
            assert t2.status == TaskStatus.COMPLETED
            with open(os.path.join(td, "file2.bin"), "rb") as f:
                assert f.read() == payload

    try:
        asyncio.run(run())
    finally:
        NonRangeFlakyHandler.release_stream.set()
        srv.shutdown()
        srv.server_close()


def test_cancelled_task_saves_resume_metadata_and_resumes():
    """Cancelling the asyncio task (app shutdown) must flush disk writer and save .meta for resume."""
    payload = b"CANCEL_RESUME_" * 400000  # ~5.6 MB
    started_evt = threading.Event()
    release_evt = threading.Event()

    class SlowRangeHandler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            rng = self.headers.get("Range", "bytes=0-")
            parts = rng.replace("bytes=", "").split("-")
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else len(payload) - 1
            chunk = payload[start : min(end + 1, len(payload))]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            mid = len(chunk) // 2
            self.wfile.write(chunk[:mid])
            self.wfile.flush()
            started_evt.set()
            if not release_evt.is_set():
                release_evt.wait(timeout=3.0)
            try:
                self.wfile.write(chunk[mid:])
                self.wfile.flush()
            except OSError:
                pass

        def log_message(self, format, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), SlowRangeHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            t = DownloadTask(
                url=f"http://127.0.0.1:{srv.server_port}/resumable.bin",
                filename="resumable.bin",
                save_dir=td,
                num_connections=2,
            )
            eng = DownloadEngine(task=t)
            coro = asyncio.create_task(eng.run())
            while not started_evt.is_set() or t.downloaded_bytes == 0:
                await asyncio.sleep(0.05)
                if coro.done():
                    break
            coro.cancel()
            try:
                await coro
            except asyncio.CancelledError:
                pass
            release_evt.set()

            assert t.status == TaskStatus.PAUSED
            assert os.path.exists(t.meta_path), ".meta must be preserved on loop cancel"
            assert os.path.exists(t.temp_path), ".part must be preserved on loop cancel"

            # Resume from saved .meta in a brand new task object with same id
            t_resumed = DownloadTask(
                id=t.id,
                url=t.url,
                filename=t.filename,
                save_dir=td,
                total_bytes=t.total_bytes,
                supports_range=True,
                num_connections=2,
            )
            eng2 = DownloadEngine(task=t_resumed)
            assert await eng2.run(), t_resumed.error_message
            with open(os.path.join(td, "resumable.bin"), "rb") as f:
                assert f.read() == payload

    try:
        asyncio.run(run())
    finally:
        release_evt.set()
        srv.shutdown()
        srv.server_close()


def test_no_overwrite_existing_file_and_permanent_404():
    """Probe filename collision must never delete an existing file; 404 must fail fast without 8 retries."""
    payload = b"NEW_DOWNLOAD_BYTES"
    hits = {"404": 0}

    class CollisionAnd404Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            if self.path == "/missing":
                hits["404"] += 1
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", 'attachment; filename="existing.bin"')
            self.end_headers()

        def do_GET(self):
            if self.path == "/missing":
                hits["404"] += 1
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", 'attachment; filename="existing.bin"')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), CollisionAnd404Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            existing_path = os.path.join(td, "existing.bin")
            with open(existing_path, "wb") as f:
                f.write(b"DO_NOT_OVERWRITE_ME")

            t = DownloadTask(
                url=f"http://127.0.0.1:{srv.server_port}/dl?id=99",
                filename="download",
                save_dir=td,
                num_connections=1,
            )
            eng = DownloadEngine(task=t)
            assert await eng.run(), t.error_message
            with open(existing_path, "rb") as f:
                assert f.read() == b"DO_NOT_OVERWRITE_ME"
            assert t.filename == "existing (1).bin"
            with open(os.path.join(td, "existing (1).bin"), "rb") as f:
                assert f.read() == payload

            # Permanent 404 from chunk GET after HEAD=200 must fail in 1 attempt, not 8
            t404 = DownloadTask(
                url=f"http://127.0.0.1:{srv.server_port}/missing",
                filename="missing.bin",
                save_dir=td,
                total_bytes=1024,
                supports_range=True,
                num_connections=1,
            )
            eng404 = DownloadEngine(task=t404)
            ok404 = await eng404.run()
            assert not ok404
            assert t404.status == TaskStatus.ERROR
            assert hits["404"] == 1, f"Expected fail-fast single 404 attempt, got {hits['404']}"

    try:
        asyncio.run(run())
    finally:
        srv.shutdown()
        srv.server_close()


def test_speed_limit_pacing():
    """speed_limit_kbps must throttle loopback downloads near the configured limit."""
    import time

    payload = b"S" * (280 * 1024)  # 280 KB

    class FastHandler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            rng = self.headers.get("Range", "bytes=0-")
            parts = rng.replace("bytes=", "").split("-")
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else len(payload) - 1
            chunk = payload[start : end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)

        def log_message(self, format, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), FastHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            t = DownloadTask(
                url=f"http://127.0.0.1:{srv.server_port}/throttled.bin",
                filename="throttled.bin",
                save_dir=td,
                num_connections=2,
            )
            # 160 KB/s limit -> 280 KB should take at least ~1.3s
            eng = DownloadEngine(task=t, speed_limit_kbps=160)
            t0 = time.monotonic()
            assert await eng.run(), t.error_message
            elapsed = time.monotonic() - t0
            assert elapsed >= 1.2, f"Throttling bypassed: finished in {elapsed:.2f}s"

    try:
        asyncio.run(run())
    finally:
        srv.shutdown()
        srv.server_close()


def test_streaming_placeholder_title_and_status_reset(monkeypatch):
    """Streaming downloads must resolve placeholder names, locate imageio_ffmpeg exe, and reset PROCESSING -> DOWNLOADING."""
    import yt_dlp

    captured_opts = []
    observed_states = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
            captured_opts.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            assert not download, "Placeholder filename must probe metadata first"
            return {"title": "Cool: Demo/Video", "ext": "mp4"}

        def process_ie_result(self, info, download=True):
            assert download
            outtmpl = self.opts["outtmpl"]
            out_file = outtmpl.replace("%(ext)s", "mp4")
            with open(out_file, "wb") as f:
                f.write(b"FAKE_MP4_DATA")
            for hook in self.opts.get("progress_hooks", []):
                hook({"status": "downloading", "total_bytes": 100, "downloaded_bytes": 50, "speed": 10.0})
                hook({"status": "finished"})
                # Audio track begins downloading after video track finished
                hook({"status": "downloading", "total_bytes": 40, "downloaded_bytes": 20, "speed": 5.0})
                observed_states.append(task_ref.status)
            return {"requested_downloads": [{"filepath": out_file}]}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    # Force imageio_ffmpeg branch by hiding PATH ffmpeg
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr("os.path.exists", lambda p: False if str(p).endswith("ffmpeg.exe") else os.path.lexists(p))

    with tempfile.TemporaryDirectory() as td:
        task_ref = DownloadTask(
            url="https://www.youtube.com/watch?v=test123",
            filename="watch",
            save_dir=td,
            num_connections=2,
        )
        engine = DownloadEngine(task=task_ref)
        ok = asyncio.run(engine.run())
        assert ok, task_ref.error_message
        assert task_ref.filename == "Cool_ Demo_Video.mp4"
        assert os.path.exists(os.path.join(td, "Cool_ Demo_Video.mp4"))
        assert observed_states == [TaskStatus.DOWNLOADING]
        ffmpeg_loc = captured_opts[-1].get("ffmpeg_location", "")
        assert ffmpeg_loc.lower().endswith(".exe"), f"Expected full exe path for imageio_ffmpeg, got {ffmpeg_loc!r}"


def test_loopback_self_signed_https():
    """Loopback HTTPS URLs (localhost/127.0.0.1) accept self-signed dev certs while public hosts keep TLS verify."""
    import datetime
    import ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from hdm.core.engine import is_loopback_url, ssl_verify_for_url

    assert is_loopback_url("https://localhost:7101/SlideEditor/x/export") is True
    assert is_loopback_url("https://127.0.0.1:8443/a.zip") is True
    assert is_loopback_url("https://[::1]:5000/a.zip") is True
    assert is_loopback_url("https://sub.localhost/a.zip") is True
    assert ssl_verify_for_url("https://localhost:7101/export") is False
    assert ssl_verify_for_url("https://example.com/file.zip") is True
    assert ssl_verify_for_url("https://localhost.evil.com/file.zip") is True

    payload = b"SELF_SIGNED_LOCAL_EXPORT_OK_" * 1000

    class ExportHandler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", 'attachment; filename="slides_export.pptx"')
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", 'attachment; filename="slides_export.pptx"')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )

    with tempfile.TemporaryDirectory() as td:
        cert_file = os.path.join(td, "cert.pem")
        key_file = os.path.join(td, "key.pem")
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_file, "wb") as f:
            f.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                )
            )

        srv = HTTPServer(("127.0.0.1", 0), ExportHandler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        try:
            url = f"https://localhost:{srv.server_port}/SlideEditor/demo/export"
            t = DownloadTask(url=url, filename="export", save_dir=td, num_connections=1)
            eng = DownloadEngine(task=t)
            assert asyncio.run(eng.run()), t.error_message
            assert t.filename == "slides_export.pptx"
            with open(os.path.join(td, "slides_export.pptx"), "rb") as f:
                assert f.read() == payload
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    asyncio.run(run_engine_test())
    asyncio.run(run_proxy_test())
    asyncio.run(run_auth_test())
