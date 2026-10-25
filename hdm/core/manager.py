"""Download Task Queue Manager for HDM.
Coordinates task lifecycles, concurrency limits, and state persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from hdm.core.config import ConfigManager
from hdm.core.engine import DownloadEngine, is_streaming_url
from hdm.core.models import DownloadTask, TaskStatus
from hdm.utils.category import FileCategory, get_category_for_filename, get_category_subfolder
from hdm.utils.formatters import clean_filename, extract_filename_from_url
from hdm.utils.system import get_app_data_folder

logger = logging.getLogger("HDM.Manager")


class DownloadQueueManager:
    """Manages the queue of download tasks and concurrency."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager
        self.config = config_manager.config
        self.tasks: Dict[str, DownloadTask] = {}
        self.active_engines: Dict[str, DownloadEngine] = {}
        self.active_tasks: Dict[str, asyncio.Task[bool]] = {}

        self.storage_file = os.path.join(get_app_data_folder(), "tasks.json")

        # Callbacks for GUI notifications
        self.on_task_added: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_updated: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_removed: Optional[Callable[[str], None]] = None
        self.on_chunk_updated: Optional[Callable[[DownloadTask], None]] = None

        self._queue_running = True
        self._loop_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()

        self.load_tasks()

    def start_scheduler(self) -> None:
        """Start the background queue scheduler."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._scheduler_loop())

    async def _scheduler_loop(self) -> None:
        """Scheduler that starts QUEUED tasks when concurrent slots are available."""
        while self._queue_running:
            await asyncio.sleep(0.5)
            async with self._lock:
                running_count = sum(
                    1 for t in self.tasks.values()
                    if t.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING)
                )
                slots_available = self.config.max_concurrent_tasks - running_count

                if slots_available > 0:
                    queued_tasks = [
                        t for t in self.tasks.values()
                        if t.status == TaskStatus.QUEUED
                    ]
                    for task in queued_tasks[:slots_available]:
                        self._launch_task_coroutine(task)

    def _launch_task_coroutine(self, task: DownloadTask) -> None:
        """Internal helper to create DownloadEngine and spawn async task."""
        if task.id in self.active_tasks and not self.active_tasks[task.id].done():
            return

        engine = DownloadEngine(
            task=task,
            on_progress=self._handle_task_progress,
            on_chunk_update=self._handle_chunk_update,
        )
        self.active_engines[task.id] = engine

        async def run_wrapper() -> bool:
            try:
                success = await engine.run()
                return success
            except Exception as e:
                logger.error(f"Task {task.id} crashed: {e}")
                task.status = TaskStatus.ERROR
                task.error_message = str(e)
                return False
            finally:
                if task.id in self.active_engines:
                    del self.active_engines[task.id]
                if task.id in self.active_tasks:
                    del self.active_tasks[task.id]
                self._handle_task_progress(task)
                self.save_tasks()

        self.active_tasks[task.id] = asyncio.create_task(run_wrapper())

    def _handle_task_progress(self, task: DownloadTask) -> None:
        if self.on_task_updated:
            self.on_task_updated(task)

    def _handle_chunk_update(self, task: DownloadTask) -> None:
        if self.on_chunk_updated:
            self.on_chunk_updated(task)

    def add_task(
        self,
        url: str,
        filename: Optional[str] = None,
        save_dir: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        connections: Optional[int] = None,
        auto_start: Optional[bool] = None,
        quality: Optional[str] = None,
        category: Optional[str] = None,
    ) -> DownloadTask:
        """Create and queue a new download task."""
        if not filename:
            filename = extract_filename_from_url(url)
        filename = clean_filename(filename)

        # Determine category with strict format & quality prioritization
        final_category: FileCategory
        if category:
            try:
                final_category = FileCategory(category)
            except ValueError:
                final_category = get_category_for_filename(filename)
        elif quality in ("128", "192", "320") or (
            filename and filename.lower().endswith((".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"))
        ):
            final_category = FileCategory.AUDIO
        elif quality in ("1080", "720", "480", "360") or (
            filename and filename.lower().endswith((".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv"))
        ):
            final_category = FileCategory.VIDEO
        elif is_streaming_url(url):
            final_category = FileCategory.VIDEO
        else:
            final_category = get_category_for_filename(filename)

        if not save_dir:
            save_dir = self.config.default_save_dir
            if self.config.auto_categorize:
                save_dir = get_category_subfolder(final_category, save_dir)

        os.makedirs(save_dir, exist_ok=True)

        if not connections or connections <= 0:
            connections = self.config.default_connections

        should_start = auto_start if auto_start is not None else self.config.auto_start

        task = DownloadTask(
            url=url,
            filename=filename,
            save_dir=save_dir,
            headers=headers or {"User-Agent": self.config.user_agent},
            num_connections=connections,
            category=final_category.value,
            quality=quality or "",
            status=TaskStatus.QUEUED if should_start else TaskStatus.PAUSED,
        )

        self.tasks[task.id] = task
        self.save_tasks()

        if self.on_task_added:
            self.on_task_added(task)

        if should_start:
            self.start_task(task.id)

        return task

    def start_task(self, task_id: str) -> bool:
        """Set task status to QUEUED so scheduler picks it up."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.QUEUED, TaskStatus.PAUSED, TaskStatus.ERROR, TaskStatus.CANCELLED):
            task.status = TaskStatus.QUEUED
            task.error_message = ""
            if self.on_task_updated:
                self.on_task_updated(task)
            self.save_tasks()
            return True
        return False

    def pause_task(self, task_id: str) -> bool:
        """Pause an active downloading task."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.id in self.active_engines:
            self.active_engines[task.id].pause()
            task.status = TaskStatus.PAUSED
            task.speed = 0.0
            if self.on_task_updated:
                self.on_task_updated(task)
            self.save_tasks()
            return True
        elif task.status == TaskStatus.QUEUED:
            task.status = TaskStatus.PAUSED
            if self.on_task_updated:
                self.on_task_updated(task)
            self.save_tasks()
            return True
        return False

    def pause_all(self) -> None:
        """Pause all currently active tasks."""
        for task_id in list(self.tasks.keys()):
            self.pause_task(task_id)

    def resume_all(self) -> None:
        """Resume all paused tasks."""
        for task in self.tasks.values():
            if task.status == TaskStatus.PAUSED:
                self.start_task(task.id)

    def delete_task(self, task_id: str, delete_file: bool = True) -> bool:
        """Remove task from queue and delete files from disk."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        # Stop active download first
        if task.id in self.active_engines:
            self.active_engines[task.id].cancel()

        if delete_file:
            import time
            # Allow brief moment for background I/O handles to release
            time.sleep(0.15)
            paths_to_delete = [
                task.full_path,
                task.temp_path,
                task.meta_path,
                f"{task.full_path}.crdownload",
                f"{task.full_path}.part",
            ]
            for path in paths_to_delete:
                for attempt in range(5):
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                            logger.info(f"Deleted file from disk: {path}")
                            break
                        except Exception as e:
                            logger.warning(f"Failed attempt {attempt + 1} deleting {path}: {e}")
                            time.sleep(0.1)
                    else:
                        break

        del self.tasks[task_id]
        self.save_tasks()

        if self.on_task_removed:
            self.on_task_removed(task_id)
        return True

    def get_total_speed(self) -> float:
        """Calculate aggregate download speed across all active tasks."""
        return sum(
            t.speed for t in self.tasks.values()
            if t.status == TaskStatus.DOWNLOADING
        )

    def get_active_count(self) -> int:
        """Return number of actively running tasks."""
        return sum(
            1 for t in self.tasks.values()
            if t.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING)
        )

    def save_tasks(self) -> None:
        """Persist task list to JSON storage."""
        try:
            data = [t.to_dict() for t in self.tasks.values()]
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save tasks: {e}")

    def load_tasks(self) -> None:
        """Load persistent tasks from JSON storage."""
        if not os.path.exists(self.storage_file):
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    task = DownloadTask.from_dict(item)
                    self.tasks[task.id] = task
        except Exception as e:
            logger.warning(f"Failed to load tasks: {e}")
