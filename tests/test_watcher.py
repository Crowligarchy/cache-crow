"""
Tests for watch mode (Task #4).

These tests verify the CacheWatcher logic without requiring a real filesystem
event loop or running watchdog. We test the file-processing logic directly
by calling _handle_new_file() as if watchdog had triggered it.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from cache_crow.watcher import CacheWatcher, fmt_size


# ---------------------------------------------------------------------------
# fmt_size utility
# ---------------------------------------------------------------------------


def test_fmt_size_bytes():
    assert fmt_size(512) == "512 B"


def test_fmt_size_kilobytes():
    assert fmt_size(2048) == "2.0 KB"


def test_fmt_size_megabytes():
    result = fmt_size(2 * 1024 * 1024)
    assert "MB" in result
    assert "2.00" in result


# ---------------------------------------------------------------------------
# CacheWatcher construction
# ---------------------------------------------------------------------------


def test_watcher_initializes(tmp_path):
    watcher = CacheWatcher(cache_dir=tmp_path)
    assert watcher.cache_dir == tmp_path
    assert watcher.output_dir is None
    assert watcher._extracted_count == 0
    assert len(watcher._seen) == 0


def test_watcher_initializes_with_output_dir(tmp_path):
    out = tmp_path / "output"
    watcher = CacheWatcher(cache_dir=tmp_path, output_dir=out)
    assert watcher.output_dir == out


# ---------------------------------------------------------------------------
# File handling logic
# ---------------------------------------------------------------------------


PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048  # >1024 bytes to pass extraction threshold


def test_handle_new_png_file_is_tracked(tmp_path):
    """PNG file triggers an entry in _seen."""
    watcher = CacheWatcher(cache_dir=tmp_path, show_all=True)
    p = tmp_path / "f_000001"
    p.write_bytes(PNG_MAGIC)

    watcher._handle_new_file(p)

    assert "f_000001" in watcher._seen
    info = watcher._seen["f_000001"]
    assert info["mime"] == "image/png"
    assert info["is_media"] is True
    assert info["extracted"] is False


def test_handle_new_unknown_file_tracked_when_show_all(tmp_path):
    """Unknown file type tracked only when show_all=True."""
    watcher = CacheWatcher(cache_dir=tmp_path, show_all=True)
    p = tmp_path / "f_000099"
    p.write_bytes(b"\x00\x01\x02\x03" + b"\x00" * 200)

    watcher._handle_new_file(p)
    assert "f_000099" in watcher._seen


def test_handle_new_unknown_file_not_tracked_without_show_all(tmp_path):
    """Unknown file type NOT tracked when show_all=False (default)."""
    watcher = CacheWatcher(cache_dir=tmp_path, show_all=False)
    p = tmp_path / "f_000099"
    p.write_bytes(b"\x00\x01\x02\x03" + b"\x00" * 200)

    watcher._handle_new_file(p)
    assert "f_000099" not in watcher._seen


def test_handle_new_file_extracts_media_when_output_dir_set(tmp_path):
    """Media file is extracted to output_dir when it's configured."""
    out_dir = tmp_path / "extracted"
    watcher = CacheWatcher(cache_dir=tmp_path, output_dir=out_dir)

    p = tmp_path / "f_000002"
    p.write_bytes(PNG_MAGIC)  # >1024 bytes

    watcher._handle_new_file(p)

    assert watcher._extracted_count == 1
    assert watcher._seen["f_000002"]["extracted"] is True
    # Check output file was created
    extracted_files = list(out_dir.iterdir())
    assert len(extracted_files) == 1
    assert extracted_files[0].suffix == ".png"


def test_handle_new_file_skips_extraction_for_small_files(tmp_path):
    """Files < 1024 bytes are not extracted even when output_dir is set."""
    out_dir = tmp_path / "extracted"
    watcher = CacheWatcher(cache_dir=tmp_path, output_dir=out_dir)

    p = tmp_path / "f_000003"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)  # only ~58 bytes

    watcher._handle_new_file(p)

    # Not extracted (too small)
    assert watcher._extracted_count == 0


def test_handle_new_file_ignores_directories(tmp_path):
    """Directories passed to _handle_new_file are silently ignored."""
    watcher = CacheWatcher(cache_dir=tmp_path)
    sub = tmp_path / "subdir"
    sub.mkdir()

    watcher._handle_new_file(sub)  # Should not raise
    assert len(watcher._seen) == 0


def test_handle_new_file_ignores_nonexistent(tmp_path):
    """Non-existent files passed to _handle_new_file are silently ignored."""
    watcher = CacheWatcher(cache_dir=tmp_path)
    ghost = tmp_path / "ghost"

    watcher._handle_new_file(ghost)  # Should not raise
    assert len(watcher._seen) == 0


def test_handle_multiple_files_accumulate(tmp_path):
    """Multiple files accumulate in _seen dict."""
    watcher = CacheWatcher(cache_dir=tmp_path, show_all=True)

    for i in range(5):
        p = tmp_path / f"f_00000{i}"
        p.write_bytes(PNG_MAGIC)
        watcher._handle_new_file(p)

    assert len(watcher._seen) == 5


# ---------------------------------------------------------------------------
# Table building
# ---------------------------------------------------------------------------


def test_build_table_returns_table(tmp_path):
    """_build_table() returns a rich Table without error."""
    from rich.table import Table

    watcher = CacheWatcher(cache_dir=tmp_path)
    table = watcher._build_table()
    assert isinstance(table, Table)


def test_build_table_with_entries(tmp_path):
    """Table built correctly with seen entries."""
    from rich.table import Table

    watcher = CacheWatcher(cache_dir=tmp_path, show_all=True)
    p = tmp_path / "f_000001"
    p.write_bytes(PNG_MAGIC)
    watcher._handle_new_file(p)

    table = watcher._build_table()
    assert isinstance(table, Table)
    assert table.row_count == 1


def test_build_table_limits_to_max_rows(tmp_path):
    """Table shows at most max_rows entries."""
    from rich.table import Table

    watcher = CacheWatcher(cache_dir=tmp_path, show_all=True, max_rows=3)

    for i in range(10):
        p = tmp_path / f"f_00000{i}"
        p.write_bytes(PNG_MAGIC)
        watcher._handle_new_file(p)

    table = watcher._build_table()
    assert table.row_count <= 3


# ---------------------------------------------------------------------------
# Extraction deduplication
# ---------------------------------------------------------------------------


def test_extract_no_collision(tmp_path):
    """Two different files extract to different output filenames."""
    out_dir = tmp_path / "out"
    watcher = CacheWatcher(cache_dir=tmp_path, output_dir=out_dir)

    for i in range(1, 3):
        p = tmp_path / f"f_00000{i}"
        p.write_bytes(PNG_MAGIC)
        watcher._handle_new_file(p)

    assert watcher._extracted_count == 2
    files = list(out_dir.iterdir())
    assert len(files) == 2
    assert len({f.name for f in files}) == 2  # unique names
