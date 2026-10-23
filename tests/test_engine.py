"""Test the download engine with a local HTTP Range server.
"""

import asyncio
import os
import sys
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hdm.core.engine import DownloadEngine
from hdm.core.models import DownloadTask, TaskStatus

TEST_DATA = b"HDM_TEST_PAYLOAD_" * 100000  # ~1.7 MB of test data


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

        with open(final_path, "rb") as f:
            downloaded_bytes = f.read()

        assert len(downloaded_bytes) == len(TEST_DATA), "File size mismatch!"
        assert downloaded_bytes == TEST_DATA, "Content integrity mismatch!"

        print(f"✅ Engine test passed! Downloaded {len(downloaded_bytes):,} bytes across {len(task.chunks)} chunks.")

    server.shutdown()


if __name__ == "__main__":
    asyncio.run(run_engine_test())
