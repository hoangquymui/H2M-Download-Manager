"""Data models for HDM: Task, Chunk, Status, and serialization.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from hdm.utils.category import FileCategory, get_category_for_filename


class TaskStatus(str, Enum):
    QUEUED = "Hàng đợi"
    CONNECTING = "Đang kết nối"
    DOWNLOADING = "Đang tải"
    PAUSED = "Tạm dừng"
    COMPLETED = "Hoàn thành"
    ERROR = "Lỗi"
    CANCELLED = "Đã hủy"


@dataclass
class Chunk:
    """Represents a discrete byte-range segment of the download."""
    chunk_id: int
    start_byte: int
    end_byte: int
    current_pos: int
    status: str = "pending"  # "pending", "downloading", "completed", "failed"
    speed: float = 0.0

    @property
    def total_bytes(self) -> int:
        return max(0, self.end_byte - self.start_byte + 1)

    @property
    def downloaded_bytes(self) -> int:
        return max(0, self.current_pos - self.start_byte)

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.end_byte - self.current_pos + 1)

    @property
    def progress_percent(self) -> float:
        if self.total_bytes <= 0:
            return 100.0 if self.status == "completed" else 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "current_pos": self.current_pos,
            "status": self.status,
            "speed": self.speed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Chunk:
        return cls(
            chunk_id=int(data["chunk_id"]),
            start_byte=int(data["start_byte"]),
            end_byte=int(data["end_byte"]),
            current_pos=int(data["current_pos"]),
            status=data.get("status", "pending"),
            speed=float(data.get("speed", 0.0)),
        )


@dataclass
class DownloadTask:
    """Represents a download task with all metadata, state, and chunks."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    filename: str = ""
    save_dir: str = ""
    total_bytes: int = -1
    downloaded_bytes: int = 0
    speed: float = 0.0
    status: TaskStatus = TaskStatus.QUEUED
    error_message: str = ""
    supports_range: bool = False
    etag: str = ""
    content_type: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    num_connections: int = 8
    category: str = FileCategory.OTHERS.value
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    chunks: List[Chunk] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.category or self.category == FileCategory.OTHERS.value:
            if self.filename:
                self.category = get_category_for_filename(self.filename).value

    @property
    def full_path(self) -> str:
        return os.path.join(self.save_dir, self.filename)

    @property
    def temp_path(self) -> str:
        return self.full_path + ".hdm_part"

    @property
    def meta_path(self) -> str:
        return self.full_path + ".hdm_meta"

    @property
    def progress_percent(self) -> float:
        if self.total_bytes <= 0:
            return 100.0 if self.status == TaskStatus.COMPLETED else 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)

    @property
    def eta(self) -> Optional[float]:
        if self.status != TaskStatus.DOWNLOADING or self.speed <= 0 or self.total_bytes <= 0:
            return None
        remaining = self.total_bytes - self.downloaded_bytes
        if remaining <= 0:
            return 0.0
        return remaining / self.speed

    def update_downloaded_from_chunks(self) -> None:
        """Recalculate total downloaded bytes from all chunks."""
        if self.chunks:
            self.downloaded_bytes = sum(c.downloaded_bytes for c in self.chunks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.filename,
            "save_dir": self.save_dir,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "speed": self.speed,
            "status": self.status.value,
            "error_message": self.error_message,
            "supports_range": self.supports_range,
            "etag": self.etag,
            "content_type": self.content_type,
            "headers": self.headers,
            "num_connections": self.num_connections,
            "category": self.category,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "chunks": [c.to_dict() for c in self.chunks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DownloadTask:
        status_val = data.get("status", TaskStatus.QUEUED.value)
        try:
            status = TaskStatus(status_val)
        except ValueError:
            status = TaskStatus.QUEUED

        # If it was downloading when the app closed, revert to PAUSED
        if status in (TaskStatus.DOWNLOADING, TaskStatus.CONNECTING):
            status = TaskStatus.PAUSED

        chunks = [Chunk.from_dict(cd) for cd in data.get("chunks", [])]

        task = cls(
            id=data.get("id", str(uuid.uuid4())),
            url=data.get("url", ""),
            filename=data.get("filename", ""),
            save_dir=data.get("save_dir", ""),
            total_bytes=int(data.get("total_bytes", -1)),
            downloaded_bytes=int(data.get("downloaded_bytes", 0)),
            speed=0.0,
            status=status,
            error_message=data.get("error_message", ""),
            supports_range=bool(data.get("supports_range", False)),
            etag=data.get("etag", ""),
            content_type=data.get("content_type", ""),
            headers=data.get("headers", {}),
            num_connections=int(data.get("num_connections", 8)),
            category=data.get("category", FileCategory.OTHERS.value),
            created_at=float(data.get("created_at", time.time())),
            completed_at=data.get("completed_at"),
            chunks=chunks,
        )
        task.update_downloaded_from_chunks()
        return task
