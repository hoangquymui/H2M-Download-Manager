"""End-to-end tests for app logic: server, queue manager, persistence, i18n, autostart, and GUI."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hdm.core.config import Config, ConfigManager
from hdm.core.manager import DownloadQueueManager
from hdm.core.models import Chunk, DownloadTask, TaskStatus
from hdm.core.server import BrowserIntegrationServer
from hdm.utils.i18n import TRANSLATIONS, set_language


def _isolated_config_manager(td: str) -> ConfigManager:
    cfg_mgr = ConfigManager.__new__(ConfigManager)
    cfg_mgr.config_dir = td
    cfg_mgr.config_file = os.path.join(td, "config.json")
    cfg_mgr.config = Config(default_save_dir=td, show_download_dialog=False)
    return cfg_mgr


def _isolated_queue_manager(td: str, cfg_mgr: ConfigManager | None = None) -> DownloadQueueManager:
    cfg_mgr = cfg_mgr or _isolated_config_manager(td)
    mgr = DownloadQueueManager.__new__(DownloadQueueManager)
    mgr.config_manager = cfg_mgr
    mgr.tasks = {}
    mgr.active_engines = {}
    mgr.active_tasks = {}
    mgr.storage_file = os.path.join(td, "tasks.json")
    mgr.on_task_added = None
    mgr.on_task_updated = None
    mgr.on_task_removed = None
    mgr.on_chunk_updated = None
    mgr._queue_running = True
    mgr._loop_task = None
    mgr._lock = asyncio.Lock()
    mgr._tasks_lock = threading.RLock()
    mgr._save_lock = threading.Lock()
    mgr._pending_requeue = set()
    mgr._schedule_allowed = True
    mgr._schedule_paused_ids = set()
    return mgr


def test_models_and_config_recovery():
    """from_dict must revert PROCESSING -> PAUSED, reset stale chunk states, and clamp invalid config."""
    raw = {
        "id": "task-recover",
        "url": "https://example.com/big.zip",
        "filename": "big.zip",
        "save_dir": tempfile.gettempdir(),
        "total_bytes": 1000,
        "status": TaskStatus.PROCESSING.value,
        "num_connections": 0,
        "headers": None,
        "chunks": [
            {"chunk_id": 1, "start_byte": 0, "end_byte": 499, "current_pos": 500, "status": "downloading"},
            {"chunk_id": 2, "start_byte": 500, "end_byte": 999, "current_pos": 600, "status": "downloading"},
        ],
    }
    restored = DownloadTask.from_dict(raw)
    assert restored.status == TaskStatus.PAUSED
    assert restored.num_connections == 1
    assert restored.headers == {}
    assert restored.chunks[0].status == "completed"
    assert restored.chunks[1].status == "pending"
    assert restored.chunks[1].speed == 0.0

    bad_cfg = Config.from_dict({
        "max_concurrent_tasks": 0,
        "default_connections": 999,
        "min_chunk_size": 10,
        "server_port": 80,
        "speed_limit_kbps": -5,
        "category_extensions": None,
    })
    assert bad_cfg.max_concurrent_tasks == 1
    assert bad_cfg.default_connections == 32
    assert bad_cfg.min_chunk_size == 65536
    assert bad_cfg.server_port == 1024
    assert bad_cfg.speed_limit_kbps == 0
    assert bad_cfg.category_extensions == {}


def test_autostart_frozen_and_nuitka_detection(monkeypatch):
    """get_autostart_command must detect both PyInstaller sys.frozen and Nuitka __compiled__."""
    import hdm.utils.system as sys_mod

    monkeypatch.setattr(sys_mod.sys, "executable", r"C:\Apps\HDM\HDM.exe")
    monkeypatch.delattr(sys_mod.sys, "frozen", raising=False)
    monkeypatch.setitem(sys_mod.__dict__, "__compiled__", object())
    try:
        assert sys_mod.is_frozen_executable() is True
        assert sys_mod.get_autostart_command() == '"C:\\Apps\\HDM\\HDM.exe" --autostart'
    finally:
        sys_mod.__dict__.pop("__compiled__", None)

    monkeypatch.setattr(sys_mod.sys, "frozen", True, raising=False)
    assert sys_mod.get_autostart_command() == '"C:\\Apps\\HDM\\HDM.exe" --autostart'


def test_i18n_key_parity():
    """Vietnamese and English translation dictionaries must expose identical keys."""
    vi_keys = set(TRANSLATIONS["vi"])
    en_keys = set(TRANSLATIONS["en"])
    assert vi_keys == en_keys, f"VI-EN={vi_keys - en_keys}, EN-VI={en_keys - vi_keys}"


def test_integration_server_http_behavior():
    """Verify query string routing, Origin protection, User-Agent merge, and negative Content-Length rejection."""
    async def run():
        with tempfile.TemporaryDirectory() as td:
            mgr = _isolated_queue_manager(td)
            srv = BrowserIntegrationServer(manager=mgr, config_manager=mgr.config_manager, host="127.0.0.1", port=0)
            await srv.start()
            port = srv._server.sockets[0].getsockname()[1]
            try:
                async with httpx.AsyncClient() as client:
                    # 1. Query string on /api/v1/status must route cleanly
                    r = await client.get(
                        f"http://127.0.0.1:{port}/api/v1/status?t=123",
                        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
                    )
                    assert r.status_code == 200
                    assert r.json()["status"] == "ok"
                    assert r.headers.get("access-control-allow-origin") == "chrome-extension://abcdefghijklmnop"

                    # 2. Normal webpage origin must be forbidden (CSRF protection)
                    r_bad = await client.get(
                        f"http://127.0.0.1:{port}/api/v1/status",
                        headers={"Origin": "https://evil.example.com"},
                    )
                    assert r_bad.status_code == 403

                    # 3. Direct download without dialog merges default User-Agent
                    r_dl = await client.post(
                        f"http://127.0.0.1:{port}/api/v1/download",
                        json={"url": "https://example.com/archive.zip", "referer": "https://example.com"},
                        headers={"Origin": "moz-extension://12345-abcde"},
                    )
                    assert r_dl.status_code == 200
                    payload = r_dl.json()
                    assert payload["ok"] is True
                    task = mgr.tasks[payload["task_id"]]
                    assert task.headers.get("Referer") == "https://example.com"
                    assert task.headers.get("User-Agent") == mgr.config.user_agent

                    # 4. Negative Content-Length via async raw stream returns 400
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    try:
                        writer.write(
                            b"POST /api/v1/download HTTP/1.1\r\n"
                            b"Host: 127.0.0.1\r\n"
                            b"Content-Length: -5\r\n\r\n"
                        )
                        await writer.drain()
                        raw = await asyncio.wait_for(reader.read(4096), timeout=3.0)
                        assert b"400 Bad Request" in raw, raw
                    finally:
                        writer.close()
                        await writer.wait_closed()
            finally:
                await srv.stop()

    asyncio.run(run())


def test_manager_single_completion_event_and_fast_pause_resume():
    """COMPLETED must emit on_task_updated once; rapid pause->resume must requeue cleanly."""
    payload = b"QUEUE_TEST_" * 10000

    class SimpleHandler(BaseHTTPRequestHandler):
        gate = threading.Event()

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            SimpleHandler.gate.wait(timeout=2.0)
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), SimpleHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    async def run():
        with tempfile.TemporaryDirectory() as td:
            mgr = _isolated_queue_manager(td)
            completed_events = []
            mgr.on_task_updated = lambda t: (
                completed_events.append(t.status) if t.status == TaskStatus.COMPLETED else None
            )

            # 1. Single completion notification
            SimpleHandler.gate.set()
            t1 = mgr.add_task(f"http://127.0.0.1:{srv.server_port}/f1.bin", save_dir=td, auto_start=True)
            mgr._launch_task_coroutine(t1)
            await mgr.active_tasks[t1.id]
            assert t1.status == TaskStatus.COMPLETED
            assert len(completed_events) == 1, f"Duplicate COMPLETED callback: {completed_events}"

            # 2. Rapid pause -> resume while previous coroutine is exiting
            SimpleHandler.gate.clear()
            t2 = mgr.add_task(f"http://127.0.0.1:{srv.server_port}/f2.bin", save_dir=td, auto_start=True)
            mgr._launch_task_coroutine(t2)
            await asyncio.sleep(0.05)
            assert mgr.pause_task(t2.id) is True
            assert mgr.start_task(t2.id) is True
            assert t2.id in mgr._pending_requeue
            SimpleHandler.gate.set()
            await mgr.active_tasks[t2.id]
            assert t2.status == TaskStatus.QUEUED, f"Rapid pause->resume lost QUEUED state: {t2.status}"

    try:
        asyncio.run(run())
    finally:
        SimpleHandler.gate.set()
        srv.shutdown()
        srv.server_close()


def test_gui_filters_refresh_and_probe_worker(monkeypatch):
    """Verify headless MainWindow filtering/refreshing, error detail display, and ProbeWorker proxy/auth."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from hdm.gui.add_dialog import ProbeWorker
    from hdm.gui.detail_dialog import DownloadDetailDialog
    from hdm.gui.main_window import MainWindow
    from tests.test_engine import AUTH_PASS, AUTH_USER, AuthRangeTestHandler, _ForwardProxy, _ForwardProxyHandler

    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as td:
        mgr = _isolated_queue_manager(td)
        t_dl = DownloadTask(id="t_dl", url="https://a/1.bin", filename="1.bin", save_dir=td)
        t_dl.status = TaskStatus.CONNECTING
        t_err = DownloadTask(
            id="t_err",
            url="https://a/2.bin",
            filename="2.bin",
            save_dir=td,
            status=TaskStatus.ERROR,
            error_message="HTTP 403 Forbidden",
        )
        mgr.tasks[t_dl.id] = t_dl
        mgr.tasks[t_err.id] = t_err

        win = MainWindow(mgr, mgr.config_manager)
        try:
            # Select "status_downloading" in sidebar (row 2: header=0, all=1, status_downloading=2)
            for i in range(win.sidebar.count()):
                item = win.sidebar.item(i)
                if item and item.data(0x0100) == "status_downloading":  # Qt.UserRole
                    win.sidebar.setCurrentRow(i)
                    break
            assert win.table.rowCount() == 1, "status_downloading must include CONNECTING tasks"

            # Mutate task metadata & status -> _refresh_table_data must sync table and sidebar counts
            t_dl.filename = "resolved.bin"
            t_dl.total_bytes = 2048
            win._refresh_table_data()
            assert win.table.item(0, 1).text() == "resolved.bin"
            assert "KB" in win.table.item(0, 3).text()

            # Complete t_dl -> should leave status_downloading view automatically and notify tray once
            tray_msgs = []
            if hasattr(win, "tray"):
                monkeypatch.setattr(win.tray, "isVisible", lambda: True)
                monkeypatch.setattr(win.tray, "showMessage", lambda *args: tray_msgs.append(args))
            t_dl.status = TaskStatus.COMPLETED
            win._on_task_updated_signal(t_dl)
            win._on_task_updated_signal(t_dl)
            assert len(tray_msgs) <= 1, "Tray notification fired twice"
            win._refresh_table_data()
            assert win.table.rowCount() == 0

            # Detail dialog must reveal error message when status == ERROR
            detail = DownloadDetailDialog(t_err, win)
            assert not detail.lbl_error_value.isHidden()
            assert not detail.lbl_error_title.isHidden()
            assert "403 Forbidden" in detail.lbl_error_value.text()
            detail.close()
        finally:
            win.update_timer.stop()
            if hasattr(win, "tray") and win.tray:
                win.tray.hide()
            win.close()

    # Verify ProbeWorker routes via proxy + Basic Auth
    origin = HTTPServer(("127.0.0.1", 0), AuthRangeTestHandler)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    proxy = _ForwardProxy(("127.0.0.1", 0), _ForwardProxyHandler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        results = []
        errors = []
        worker = ProbeWorker(
            url=f"http://127.0.0.1:{origin.server_port}/auth_item.bin",
            user_agent="HDM-Test",
            proxy_url=f"http://127.0.0.1:{proxy.server_address[1]}",
            credentials=(AUTH_USER, AUTH_PASS),
        )
        worker.finished_signal.connect(lambda fn, sz, rng: results.append((fn, sz, rng)))
        worker.error_signal.connect(lambda err: errors.append(err))
        worker.run()  # Run synchronously in test thread so Qt signals emit directly
        app.processEvents()
        assert not errors, f"ProbeWorker failed unexpectedly: {errors}"
        assert results and results[0][0] == "auth_item.bin" and results[0][1] > 0 and results[0][2] is True
        assert proxy.requests, "ProbeWorker bypassed configured proxy"
    finally:
        proxy.shutdown()
        proxy.server_close()
        origin.shutdown()
        origin.server_close()
        set_language("vi")
