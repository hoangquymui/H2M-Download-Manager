"""Automated unit and integration test for HDM core components.
"""

import asyncio
import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hdm.core.config import Config, ConfigManager
from hdm.core.models import Chunk, DownloadTask, TaskStatus
from hdm.core.sparse_file import preallocate_file
from hdm.utils.category import FileCategory, get_category_for_filename
from hdm.utils.formatters import clean_filename, extract_filename_from_url, format_bytes, format_speed


def test_formatters():
    assert format_bytes(0) == "0 B"
    assert "KB" in format_bytes(1024 * 50)
    assert "MB" in format_bytes(1024 * 1024 * 5)
    assert "GB" in format_bytes(1024 * 1024 * 1024 * 2)

    assert "KB/s" in format_speed(500 * 1024)
    assert "MB/s" in format_speed(5 * 1024 * 1024)

    assert clean_filename('test:file*name?.zip') == 'test_file_name_.zip'
    assert extract_filename_from_url('https://example.com/archive.tar.gz?v=1') == 'archive.tar.gz'
    print("✅ test_formatters passed!")


def test_categories():
    assert get_category_for_filename("document.pdf") == FileCategory.DOCUMENTS
    assert get_category_for_filename("installer.exe") == FileCategory.PROGRAMS
    assert get_category_for_filename("movie.mp4") == FileCategory.VIDEO
    assert get_category_for_filename("music.mp3") == FileCategory.AUDIO
    assert get_category_for_filename("data.zip") == FileCategory.COMPRESSED
    assert get_category_for_filename("photo.jpg") == FileCategory.IMAGES
    print("✅ test_categories passed!")


def test_models():
    chunk = Chunk(chunk_id=1, start_byte=0, end_byte=1023, current_pos=512, status="downloading")
    assert chunk.total_bytes == 1024
    assert chunk.downloaded_bytes == 512
    assert chunk.progress_percent == 50.0

    task = DownloadTask(
        url="https://example.com/test.zip",
        filename="test.zip",
        save_dir=tempfile.gettempdir(),
        total_bytes=2048,
        chunks=[chunk]
    )
    task.update_downloaded_from_chunks()
    assert task.downloaded_bytes == 512
    assert task.progress_percent == 25.0

    # Serialization test
    d = task.to_dict()
    restored = DownloadTask.from_dict(d)
    assert restored.filename == "test.zip"
    assert restored.total_bytes == 2048
    assert len(restored.chunks) == 1
    assert restored.chunks[0].current_pos == 512
    print("✅ test_models passed!")


def test_sparse_file():
    with tempfile.TemporaryDirectory() as td:
        test_file = os.path.join(td, "sparse_test.bin")
        success = preallocate_file(test_file, 1024 * 1024 * 10)  # 10 MB
        assert success
        assert os.path.exists(test_file)
        assert os.path.getsize(test_file) == 1024 * 1024 * 10
    print("✅ test_sparse_file passed!")


if __name__ == "__main__":
    test_formatters()
    test_categories()
    test_models()
    test_sparse_file()
    print("\n🎉 ALL UNIT TESTS PASSED SUCCESSFULLY!")
