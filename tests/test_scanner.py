from pathlib import Path
from unittest.mock import patch

import pytest

from cache_crow.scanner import find_cache_dirs, identify_file_type, scan_cache
from cache_crow.models import CacheEntry


PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPEG_MAGIC = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100
GIF_MAGIC = b"GIF89a" + b"\x00" * 100
WEBP_MAGIC = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
MP4_MAGIC = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100
WEBM_MAGIC = b"\x1A\x45\xDF\xA3" + b"\x00" * 100
UNKNOWN_MAGIC = b"\x00\x01\x02\x03" + b"\x00" * 100


def write_file(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_identify_png(tmp_path):
    p = write_file(tmp_path, "file1", PNG_MAGIC)
    assert identify_file_type(p) == "image/png"


def test_identify_jpeg(tmp_path):
    p = write_file(tmp_path, "file2", JPEG_MAGIC)
    assert identify_file_type(p) == "image/jpeg"


def test_identify_gif(tmp_path):
    p = write_file(tmp_path, "file3", GIF_MAGIC)
    assert identify_file_type(p) == "image/gif"


def test_identify_webp(tmp_path):
    p = write_file(tmp_path, "file4", WEBP_MAGIC)
    assert identify_file_type(p) == "image/webp"


def test_identify_mp4(tmp_path):
    p = write_file(tmp_path, "file5", MP4_MAGIC)
    assert identify_file_type(p) == "video/mp4"


def test_identify_webm(tmp_path):
    p = write_file(tmp_path, "file6", WEBM_MAGIC)
    assert identify_file_type(p) == "video/webm"


def test_identify_unknown(tmp_path):
    p = write_file(tmp_path, "file7", UNKNOWN_MAGIC)
    assert identify_file_type(p) == "application/octet-stream"


def test_identify_too_short(tmp_path):
    p = write_file(tmp_path, "file8", b"\x89P")
    assert identify_file_type(p) == "application/octet-stream"


def test_scan_cache_returns_entries(tmp_path):
    write_file(tmp_path, "a", PNG_MAGIC)
    write_file(tmp_path, "b", JPEG_MAGIC)
    write_file(tmp_path, "c", UNKNOWN_MAGIC)

    entries = scan_cache(tmp_path)

    assert len(entries) == 3
    assert all(isinstance(e, CacheEntry) for e in entries)

    mimes = {e.mime_type for e in entries}
    assert "image/png" in mimes
    assert "image/jpeg" in mimes
    assert "application/octet-stream" in mimes


def test_scan_cache_skips_directories(tmp_path):
    write_file(tmp_path, "img", PNG_MAGIC)
    (tmp_path / "subdir").mkdir()

    entries = scan_cache(tmp_path)
    assert len(entries) == 1


def test_scan_cache_entry_fields(tmp_path):
    p = write_file(tmp_path, "testfile", PNG_MAGIC)
    entries = scan_cache(tmp_path)

    assert len(entries) == 1
    e = entries[0]
    assert e.path == p
    assert e.size == len(PNG_MAGIC)
    assert e.mime_type == "image/png"
    assert isinstance(e.modified, float)


def test_find_cache_dirs_returns_existing(tmp_path):
    fake_cache = tmp_path / "discord" / "Cache" / "Cache_Data"
    fake_cache.mkdir(parents=True)

    fake_paths = [fake_cache, tmp_path / "nonexistent" / "Cache" / "Cache_Data"]

    with patch("cache_crow.scanner.CACHE_PATHS", {"discord": fake_paths}):
        result = find_cache_dirs("discord")

    assert result == [fake_cache]


def test_find_cache_dirs_unknown_app():
    result = find_cache_dirs("unknown_app_xyz")
    assert result == []


def test_find_cache_dirs_none_exist(tmp_path):
    fake_paths = [tmp_path / "nonexistent1", tmp_path / "nonexistent2"]

    with patch("cache_crow.scanner.CACHE_PATHS", {"discord": fake_paths}):
        result = find_cache_dirs("discord")

    assert result == []
