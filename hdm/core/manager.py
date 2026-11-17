"""Download Task Queue Manager for HDM.
Coordinates task lifecycles, concurrency limits, and state persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from hdm.core.config import ConfigManager
from hdm.core.engine import DownloadEngine, is_streaming_url
from hdm.core.models import DownloadTask, TaskStatus
from hdm.utils.category import FileCategory, get_category_for_filename, get_category_subfolder
from hdm.utils.formatters import clean_filename, extract_filename_from_url, get_unique_filename
from hdm.utils.site_auth import find_site_credentials
from hdm.utils.system import get_app_data_folder, resolve_download_dir

logger = logging.getLogger("HDM.Manager")


def _parse_clock(value: str) -> Optional[int]:
    """Parse "HH:MM" into minutes since midnight; None when unset/invalid."""
    try:
        hour_text, minute_text = str(value).strip().split(":")
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, ValueError):
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return hour * 60 + minute


def is_within_window(
    now_minutes: int,
    start: Optional[int],
    stop: Optional[int],
) -> bool:
    """True when *now* falls inside the daily window (start inclusive, stop exclusive).

    A window whose start is later than its stop crosses midnight.
    """
    if start is None and stop is None:
        return True
    if start is not None and stop is not None:
        if start <= stop:
            return start <= now_minutes < stop
        return now_minutes >= start or now_minutes < stop
    if start is not None:
        return now_minutes >= start
    return now_minutes < stop


class DownloadQueueManager:
    """Manages the queue of download tasks and concurrency."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self.config_manager = config_manager
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
        self._tasks_lock = threading.RLock()
        self._save_lock = threading.Lock()
        self._pending_requeue: set[str] = set()
        self._schedule_allowed = self._schedule_allows_now()
        self._schedule_paused_ids: set[str] = set()

        self.load_tasks()

    @property
    def config(self):
        return self.config_manager.config

    def _guard(self) -> threading.RLock:
        lock = getattr(self, "_tasks_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._tasks_lock = lock
        return lock

    def _requeue_set(self) -> set[str]:
        s = getattr(self, "_pending_requeue", None)
        if s is None:
            s = set()
            self._pending_requeue = s
        return s

    def _schedule_allows_now(self) -> bool:
        """True when the configured daily download window is open."""
        if not getattr(self.config, "schedule_enabled", False):
            return True
        now = datetime.now()
        return is_within_window(
            now.hour * 60 + now.minute,
            _parse_clock(getattr(self.config, "schedule_start", "")),
            _parse_clock(getattr(self.config, "schedule_stop", "")),
        )

    def _pause_for_schedule(self) -> None:
        """Pause everything that would otherwise run until the window reopens."""
        active_statuses = (
            TaskStatus.QUEUED,
            TaskStatus.CONNECTING,
            TaskStatus.DOWNLOADING,
            TaskStatus.PROCESSING,
        )
        with self._guard():
            snapshot = list(self.tasks.values())
        for task in snapshot:
            if task.status in active_statuses and self.pause_task(task.id):
                self._schedule_paused_ids.add(task.id)

    def _resume_scheduled_tasks(self) -> None:
        """Resume only the tasks the scheduler paused, never user-paused ones."""
        with self._guard():
            ids = list(self._schedule_paused_ids)
        for task_id in ids:
            with self._guard():
                task = self.tasks.get(task_id)
            if task is not None and task.status == TaskStatus.PAUSED:
                self.start_task(task_id)
        with self._guard():
            self._schedule_paused_ids.clear()

    async def shutdown(self, timeout: float = 1.5) -> None:
        """Stop scheduler, pause active engines, and wait briefly so resume metadata flushes."""
        self._queue_running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self.pause_all()
        with self._guard():
            pending = [t for t in self.active_tasks.values() if not t.done()]
        if pending:
            try:
                await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        self.save_tasks()

    def start_scheduler(self) -> None:
        """Start the background queue scheduler."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._scheduler_loop())

    async def _scheduler_loop(self) -> None:
        """Start QUEUED tasks while slots and the daily schedule window allow it."""
        while self._queue_running:
            await asyncio.sleep(0.5)
            if not self._queue_running:
                break
            allowed = self._schedule_allows_now()
            if allowed != self._schedule_allowed:
                self._schedule_allowed = allowed
                if allowed:
                    logger.info("Schedule window opened; resuming downloads")
                    self._resume_scheduled_tasks()
                else:
                    logger.info("Schedule window closed; pausing downloads")
                    self._pause_for_schedule()
            if not allowed:
                continue
            async with self._lock:
                # Snapshot: the GUI thread may add/remove tasks concurrently.
                with self._guard():
                    tasks = list(self.tasks.values())
                running_count = sum(
                    1 for t in tasks
                    if t.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING, TaskStatus.PROCESSING)
                )
                slots_available = self.config.max_concurrent_tasks - running_count

                if slots_available > 0:
                    queued_tasks = [
                        t for t in tasks
                        if t.status == TaskStatus.QUEUED
                    ]
                    for task in queued_tasks[:slots_available]:
                        self._launch_task_coroutine(task)

    def _launch_task_coroutine(self, task: DownloadTask) -> None:
        """Internal helper to create DownloadEngine and spawn async task."""
        with self._guard():
            if task.id in self.active_tasks and not self.active_tasks[task.id].done():
                return

            engine = DownloadEngine(
                task=task,
                on_progress=self._handle_task_progress,
                on_chunk_update=self._handle_chunk_update,
                min_chunk_size=getattr(self.config, "min_chunk_size", 1048576),
                speed_limit_kbps=getattr(self.config, "speed_limit_kbps", 0),
                proxy_url=getattr(self.config, "proxy_url", ""),
                credentials=find_site_credentials(
                    getattr(self.config, "site_credentials", {}), task.url
                ),
            )
            self.active_engines[task.id] = engine

        async def run_wrapper() -> bool:
            completed_already_notified = False
            try:
                success = await engine.run()
                if success and task.status == TaskStatus.COMPLETED:
                    completed_already_notified = True
                return success
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Task {task.id} crashed: {e}")
                task.status = TaskStatus.ERROR
                task.error_message = str(e)
                return False
            finally:
                with self._guard():
                    if self.active_engines.get(task.id) is engine:
                        del self.active_engines[task.id]
                    self.active_tasks.pop(task.id, None)
                    requeue = task.id in self._requeue_set()
                    if requeue:
                        self._requeue_set().discard(task.id)
                        if task.id in self.tasks and task.status not in (
                            TaskStatus.COMPLETED,
                            TaskStatus.CANCELLED,
                        ):
                            task.status = TaskStatus.QUEUED
                            task.error_message = ""
                if not completed_already_notified:
                    self._handle_task_progress(task)
                self.save_tasks()

        with self._guard():
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
        manifest: Optional[str] = None,
    ) -> DownloadTask:
        """Create and queue a new download task."""
        if not filename:
            filename = extract_filename_from_url(url)
        filename = clean_filename(filename)

        # Determine category with format & quality prioritization
        final_category: FileCategory
        if category:
            try:
                final_category = FileCategory(category)
            except ValueError:
                final_category = get_category_for_filename(filename)
        elif quality in ("128", "192", "320"):
            final_category = FileCategory.AUDIO
        elif manifest:
            final_category = FileCategory.VIDEO
        elif quality in ("1080", "720", "480", "360"):
            final_category = FileCategory.VIDEO
        elif is_streaming_url(url):
            final_category = FileCategory.VIDEO
        else:
            final_category = get_category_for_filename(filename)

        if not save_dir:
            save_dir = resolve_download_dir(self.config.default_save_dir)
            if self.config.auto_categorize:
                save_dir = get_category_subfolder(final_category, save_dir)

        os.makedirs(save_dir, exist_ok=True)
        filename = get_unique_filename(save_dir, filename)
        filename = self._avoid_active_name(save_dir, filename)

        if not connections or connections <= 0:
            connections = self.config.default_connections

        should_start = auto_start if auto_start is not None else self.config.auto_start

        merged_headers: Dict[str, str] = {}
        if headers:
            merged_headers.update(headers)
        if not any(k.lower() == "user-agent" for k in merged_headers):
            merged_headers["User-Agent"] = self.config.user_agent

        with self._guard():
            filename = get_unique_filename(save_dir, filename)
            filename = self._avoid_active_name(save_dir, filename)

            task = DownloadTask(
                url=url,
                filename=filename,
                save_dir=save_dir,
                headers=merged_headers,
                num_connections=connections,
                category=final_category.value,
                quality=quality or "",
                manifest=manifest or "",
                status=TaskStatus.QUEUED if should_start else TaskStatus.PAUSED,
            )

            self.tasks[task.id] = task
        self.save_tasks()

        if self.on_task_added:
            self.on_task_added(task)

        return task

    def _avoid_active_name(self, save_dir: str, filename: str) -> str:
        """In-flight downloads keep their partial data in .hdm_tmp, not beside the
        target, so an identical name would only collide at completion time."""
        target_dir = os.path.normcase(os.path.abspath(save_dir))
        with self._guard():
            snapshot = list(self.tasks.values())
        busy = {
            os.path.normcase(t.filename)
            for t in snapshot
            if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
            and os.path.normcase(os.path.abspath(t.save_dir)) == target_dir
        }
        if os.path.normcase(filename) not in busy:
            return filename
        stem, ext = os.path.splitext(filename)
        stem = re.sub(r"\s*\(\d+\)$", "", stem)
        counter = 1
        while os.path.normcase(f"{stem} ({counter}){ext}") in busy:
            counter += 1
        return f"{stem} ({counter}){ext}"

    def start_task(self, task_id: str) -> bool:
        """Set task status to QUEUED so scheduler picks it up."""
        with self._guard():
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status in (TaskStatus.QUEUED, TaskStatus.PAUSED, TaskStatus.ERROR, TaskStatus.CANCELLED):
                task.status = TaskStatus.QUEUED
                task.error_message = ""
                active = self.active_tasks.get(task_id)
                if active is not None and not active.done():
                    self._requeue_set().add(task_id)
            else:
                return False
        if self.on_task_updated:
            self.on_task_updated(task)
        self.save_tasks()
        return True

    def pause_task(self, task_id: str) -> bool:
        """Pause an active downloading task."""
        with self._guard():
            task = self.tasks.get(task_id)
            if not task:
                return False
            self._requeue_set().discard(task_id)
            if task.status in (TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED):
                return False

            engine = self.active_engines.get(task.id)
            if engine is not None:
                engine.pause()
                task.status = TaskStatus.PAUSED
                task.speed = 0.0
            elif task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.PAUSED
            else:
                return False
        if self.on_task_updated:
            self.on_task_updated(task)
        self.save_tasks()
        return True

    def pause_all(self) -> None:
        """Pause all currently active tasks."""
        with self._guard():
            ids = list(self.tasks.keys())
        for task_id in ids:
            self.pause_task(task_id)

    def resume_all(self) -> None:
        """Resume all paused tasks."""
        with self._guard():
            tasks = list(self.tasks.values())
        for task in tasks:
            if task.status == TaskStatus.PAUSED:
                self.start_task(task.id)

    def clear_completed(self) -> int:
        """Remove all completed tasks from the list without deleting files on disk."""
        with self._guard():
            completed_ids = [
                tid for tid, t in self.tasks.items()
                if t.status == TaskStatus.COMPLETED
            ]
        for tid in completed_ids:
            self.delete_task(tid, delete_file=False)
        return len(completed_ids)

    def delete_task(self, task_id: str, delete_file: bool = True) -> bool:
        """Remove task from queue and delete files from disk."""
        with self._guard():
            task = self.tasks.get(task_id)
            if not task:
                return False
            self._requeue_set().discard(task_id)
            engine = self.active_engines.get(task.id)
            if engine:
                engine.cancel()
            del self.tasks[task_id]

        if delete_file:
            paths_to_delete = [
                task.full_path,
                task.temp_path,
                task.meta_path,
                task.stream_temp_dir,
                task.legacy_temp_path,
                task.legacy_meta_path,
                f"{task.full_path}.crdownload",
                f"{task.full_path}.part",
            ]
            # Deletion retries run off the GUI thread so the window never freezes
            # while the engine releases its file handle.
            threading.Thread(
                target=self._delete_files_with_retry,
                args=(paths_to_delete, task.temp_dir),
                daemon=True,
            ).start()

        self.save_tasks()

        if self.on_task_removed:
            self.on_task_removed(task_id)
        return True

    @staticmethod
    def _delete_files_with_retry(paths: List[str], temp_dir: str = "") -> None:
        time.sleep(0.15)  # Let the engine release its file handle
        for path in paths:
            for attempt in range(12):
                if not os.path.exists(path):
                    break
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=False)
                    else:
                        os.remove(path)
                    logger.info(f"Deleted file from disk: {path}")
                    break
                except Exception as e:
                    logger.warning(f"Failed attempt {attempt + 1} deleting {path}: {e}")
                    time.sleep(0.25)
        if temp_dir:
            try:
                os.rmdir(temp_dir)  # Only succeeds when no other task uses it
            except OSError:
                pass

    def get_total_speed(self) -> float:
        """Calculate aggregate download speed across all active tasks."""
        with self._guard():
            tasks = list(self.tasks.values())
        return sum(
            t.speed for t in tasks
            if t.status == TaskStatus.DOWNLOADING
        )

    def get_active_count(self) -> int:
        """Return number of actively running tasks."""
        with self._guard():
            tasks = list(self.tasks.values())
        return sum(
            1 for t in tasks
            if t.status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING, TaskStatus.PROCESSING)
        )

    def save_tasks(self) -> None:
        """Persist task list atomically (safe against concurrent/crashed writes)."""
        try:
            with self._guard():
                data = [t.to_dict() for t in list(self.tasks.values())]
            payload = json.dumps(data, indent=2, ensure_ascii=False)
            tmp_file = f"{self.storage_file}.tmp"
            with self._save_lock:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp_file, self.storage_file)
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
