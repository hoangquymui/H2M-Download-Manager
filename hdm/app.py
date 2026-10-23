"""Application entrypoint and coordinator.
Bridges the PySide6 main UI thread with the dedicated asyncio engine thread.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from typing import Optional

from PySide6.QtCore import QThread
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from hdm.core.config import ConfigManager
from hdm.core.manager import DownloadQueueManager
from hdm.core.server import BrowserIntegrationServer
from hdm.gui.main_window import MainWindow
from hdm.gui.style import apply_theme
from hdm.utils.system import get_app_icon

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("HDM.App")


class AsyncEngineThread(QThread):
    """Dedicated background thread running the asyncio event loop for downloads and HTTP server."""

    def __init__(self, manager: DownloadQueueManager, config_manager: ConfigManager) -> None:
        super().__init__()
        self.manager = manager
        self.config_manager = config_manager
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server: Optional[BrowserIntegrationServer] = None
        self.on_show_window: Optional[callable] = None
        self._stop_event: Optional[asyncio.Event] = None

    def run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._run_async_services())
        except Exception as e:
            logger.error(f"Error in AsyncEngineThread: {e}")
        finally:
            try:
                # Cancel all remaining tasks cleanly
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self.loop.close()
            except Exception:
                pass

    async def _run_async_services(self) -> None:
        self._stop_event = asyncio.Event()

        # Start download queue scheduler inside the active running loop
        self.manager.start_scheduler()

        # Start browser integration server if configured
        if self.config_manager.config.server_enabled:
            self.server = BrowserIntegrationServer(
                manager=self.manager,
                host="127.0.0.1",
                port=self.config_manager.config.server_port,
                on_show_requested=self.on_show_window,
            )
            await self.server.start()

        logger.info("Async Engine background loop running.")
        await self._stop_event.wait()

        # Graceful shutdown of integration server
        if self.server:
            await self.server.stop()

    def stop(self) -> None:
        """Gracefully shut down the event loop."""
        if self.loop and self.loop.is_running():
            if self._stop_event:
                self.loop.call_soon_threadsafe(self._stop_event.set)
        self.wait(2000)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("HDM")
    app.setOrganizationName("H2M Team")
    # Fusion renders identically on every Windows version and respects QSS colors
    app.setStyle("Fusion")
    app.setWindowIcon(get_app_icon())

    # 1. Initialize configuration and queue manager
    config_mgr = ConfigManager()

    # Apply the saved light/dark theme before any window is created
    apply_theme(app, config_mgr.config.theme)

    download_mgr = DownloadQueueManager(config_mgr)

    # 2. Start Async Engine Thread
    engine_thread = AsyncEngineThread(download_mgr, config_mgr)

    # 3. Initialize Main GUI Window
    main_window = MainWindow(download_mgr, config_mgr)
    engine_thread.on_show_window = lambda: main_window.bridge.show_window_signal.emit()

    engine_thread.start()

    # 4. Cleanup on exit
    def cleanup():
        logger.info("Application shutting down...")
        engine_thread.stop()
        download_mgr.save_tasks()

    app.aboutToQuit.connect(cleanup)

    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
