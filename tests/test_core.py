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
from hdm.core.engine import _needs_browser_headers, _stream_format_spec, is_streaming_url
from hdm.core.models import Chunk, DownloadTask, TaskStatus
from hdm.core.sparse_file import preallocate_file
from hdm.utils.category import (
    FileCategory,
    get_category_for_filename,
    get_category_subfolder,
    set_custom_category_extensions,
    set_custom_category_folders,
)
from hdm.utils.formatters import (
    clean_filename,
    extract_filename_from_url,
    format_bytes,
    format_speed,
    get_unique_filename,
)


def test_formatters():
    assert format_bytes(0) == "0 B"
    assert "KB" in format_bytes(1024 * 50)
    assert "MB" in format_bytes(1024 * 1024 * 5)
    assert "GB" in format_bytes(1024 * 1024 * 1024 * 2)

    assert "KB/s" in format_speed(500 * 1024)
    assert "MB/s" in format_speed(5 * 1024 * 1024)

    assert clean_filename('test:file*name?.zip') == 'test_file_name_.zip'
    assert extract_filename_from_url('https://example.com/archive.tar.gz?v=1') == 'archive.tar.gz'

    # Signed CDN URL: Content-Disposition suggests an opaque UUID while the
    # real filename only exists in the URL path.
    signed = (
        "https://cdn.example.net/github-production-release-asset/1/eb63edc0-0780-43b4-9976-97685c9e3a9e"
        "?sp=r&response-content-disposition=attachment%3B%20filename%3D%22WSA_2407.7z%22"
        "&response-content-type=application%2Foctet-stream"
    )
    assert extract_filename_from_url(
        signed, 'attachment; filename="eb63edc0-0780-43b4-9976-97685c9e3a9e"'
    ) == "WSA_2407.7z"
    # Same URL with the real name in the path and a UUID disposition.
    path_named = "https://cdn.example.net/files/WSA_2407.7z?token=abc"
    assert extract_filename_from_url(
        path_named, 'attachment; filename="eb63edc0-0780-43b4-9976-97685c9e3a9e"'
    ) == "WSA_2407.7z"
    # A proper Content-Disposition still wins over the URL.
    assert extract_filename_from_url(
        "https://example.com/random/segment", 'attachment; filename="archive.zip"'
    ) == "archive.zip"
    # RFC 5987 filename* is supported.
    assert extract_filename_from_url(
        "https://example.com/x", "attachment; filename*=UTF-8''b%C3%A1o%20c%C3%A1o.pdf"
    ) == "báo cáo.pdf"
    # Plain filename query parameter.
    assert extract_filename_from_url("https://example.com/dl?filename=setup.msi") == "setup.msi"

    with tempfile.TemporaryDirectory() as td:
        f1 = os.path.join(td, "myfile.mp4")
        with open(f1, "w") as f:
            f.write("test")
        # Since myfile.mp4 exists, next candidate should be myfile (1).mp4
        assert get_unique_filename(td, "myfile.mp4") == "myfile (1).mp4"
        # If both exist, next candidate should be myfile (2).mp4
        f2 = os.path.join(td, "myfile (1).mp4")
        with open(f2, "w") as f:
            f.write("test")
        assert get_unique_filename(td, "myfile.mp4") == "myfile (2).mp4"
        # Non-existing file keeps name
        assert get_unique_filename(td, "other.mp4") == "other.mp4"

    print("✅ test_formatters passed!")


def test_categories():
    assert get_category_for_filename("document.pdf") == FileCategory.DOCUMENTS
    assert get_category_for_filename("installer.exe") == FileCategory.PROGRAMS
    assert get_category_for_filename("movie.mp4") == FileCategory.VIDEO
    assert get_category_for_filename("music.mp3") == FileCategory.AUDIO
    assert get_category_for_filename("data.zip") == FileCategory.COMPRESSED
    assert get_category_for_filename("photo.jpg") == FileCategory.IMAGES
    assert get_category_subfolder(FileCategory.PROGRAMS, "C:\\Downloads") == os.path.join("C:\\Downloads", "Programs")
    assert get_category_subfolder(FileCategory.VIDEO, "C:\\Downloads") == os.path.join("C:\\Downloads", "Video")

    # Test custom extension override
    set_custom_category_extensions({"Programs": "exe, msi, custompkg"})
    assert get_category_for_filename("app.custompkg") == FileCategory.PROGRAMS

    # Test custom folder override
    set_custom_category_folders({"Music": "MyCustomMusic", "Other": "MyOther"})
    assert get_category_subfolder(FileCategory.AUDIO, "C:\\Downloads") == os.path.join("C:\\Downloads", "MyCustomMusic")
    assert get_category_subfolder(FileCategory.OTHERS, "C:\\Downloads") == os.path.join("C:\\Downloads", "MyOther")

    # Reset back to default
    set_custom_category_extensions(None)
    set_custom_category_folders(None)
    assert get_category_for_filename("installer.msi") == FileCategory.PROGRAMS
    assert get_category_subfolder(FileCategory.AUDIO, "C:\\Downloads") == os.path.join("C:\\Downloads", "Music")
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


def test_stream_format_spec():
    # Audio-only sources never try to merge video.
    assert _stream_format_spec("192", True) == "bestaudio/best"

    # Captured media playlist is a single rendition: no height filtering.
    media = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:3.0,\nseg.ts\n#EXT-X-ENDLIST\n"
    assert _stream_format_spec("1080", False, media) == "best"

    # Master playlist keeps the requested rendition and can merge split A/V.
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n360.m3u8\n"
    assert _stream_format_spec("360", False, master) == (
        "b[height<=360]/bv*[height<=360]+ba/b[height<=360]/b"
    )
    assert _stream_format_spec("", False, master) == "b/bv*+ba/b"

    # Direct stream URL: height filter plus avc1/m4a preference for playback.
    spec = _stream_format_spec("720", False)
    assert spec.startswith("bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]"), spec
    assert "avc1" in _stream_format_spec("", False)
    assert _stream_format_spec("", False).endswith("/bv*+ba/b")

    # Unknown quality labels must not leak into the selector.
    assert "height<=" not in _stream_format_spec("captured:1", False)
    print("✅ test_stream_format_spec passed!")


def test_needs_browser_headers():
    # YouTube-family hosts manage their own signing/session.
    assert not _needs_browser_headers("https://www.youtube.com/watch?v=x")
    assert not _needs_browser_headers("https://www.youtube-nocookie.com/embed/x")
    assert not _needs_browser_headers("https://youtu.be/x")
    assert not _needs_browser_headers("https://rr3---sn-abc.googlevideo.com/videoplayback")
    assert _needs_browser_headers("https://youtube.com.evil.test/x")
    # Other CDNs still get the captured Referer/Cookie.
    assert _needs_browser_headers("https://cdn.example.net/video.m3u8")
    assert _needs_browser_headers("not a url")

    # Streaming detection covers embeds and manifest URLs from every source.
    assert is_streaming_url("https://www.youtube.com/watch?v=x")
    assert is_streaming_url("https://www.youtube-nocookie.com/embed/x")
    assert is_streaming_url("https://cdn.example.net/live/index.m3u8?token=1")
    assert is_streaming_url("https://cdn.example.net/vod/manifest.mpd")
    assert is_streaming_url("https://example.com/file.zip") is False
    print("✅ test_needs_browser_headers passed!")


def test_server_qualities():
    from hdm.core.server import BrowserIntegrationServer

    low = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=600000,RESOLUTION=640x360\n360.m3u8\n"
    high = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080\n1080.m3u8\n"

    cleaned = BrowserIntegrationServer._sanitize_qualities(
        [
            {"label": "360p", "height": "360", "manifest": low},
            {"label": "x" * 40, "height": "1080", "manifest": high},
            {"label": "bad", "height": "720", "manifest": "nope"},
            "garbage",
        ]
    )
    # Highest rendition first, invalid entries dropped, labels capped.
    assert [q["height"] for q in cleaned] == ["1080", "360"], cleaned
    assert len(cleaned[0]["label"]) == 24

    blob_master = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nblob:http://x.test/low\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=5000000\nblob:http://x.test/high\n"
    )
    assert BrowserIntegrationServer._has_blob_uris(blob_master)
    assert not BrowserIntegrationServer._has_blob_uris(low)
    assert not BrowserIntegrationServer._has_blob_uris("#EXTM3U\n# notes about blob:\n")
    assert BrowserIntegrationServer._highest_quality_manifest(cleaned) == high.strip()
    print("✅ test_server_qualities passed!")


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
    test_stream_format_spec()
    test_needs_browser_headers()
    test_server_qualities()
    test_sparse_file()
    print("\n🎉 ALL UNIT TESTS PASSED SUCCESSFULLY!")
