"""
Tests for the cache-crow CLI (cache_crow.cli).

All tests use synthetic cache data — no real Discord installation required.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cache_crow.simple_cache import (
    SIMPLE_CACHE_EOF_MAGIC,
    SIMPLE_CACHE_HEADER_MAGIC,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000  # >1024 to pass default min_size
JPEG_BYTES = b"\xFF\xD8\xFF\xE0" + b"\x00" * 2000


def make_cache_entry(url: str, body: bytes) -> bytes:
    """Build a synthetic Chrome Simple Cache entry."""
    key = url.encode("utf-8")
    headers = b"HTTP/1.1 200 OK\r\n\r\n"
    eof1 = struct.pack("<QIIii", SIMPLE_CACHE_EOF_MAGIC, 0, 0, len(body), 0)
    eof0 = struct.pack("<QIIii", SIMPLE_CACHE_EOF_MAGIC, 0, 0, len(headers), 0)
    header = struct.pack("<QIIII", SIMPLE_CACHE_HEADER_MAGIC, 5, len(key), 0, 0)
    return header + key + body + eof1 + headers + eof0


def run_cli(*args: str) -> int:
    """Run cache-crow CLI with given args. Returns exit code."""
    from cache_crow import cli

    saved_argv = sys.argv[:]
    sys.argv = ["cache-crow", *args]
    try:
        cli.main()
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    finally:
        sys.argv = saved_argv


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


def test_version_flag(capsys):
    """--version prints the version string (exit code 0)."""
    from cache_crow import __version__

    # run_cli catches SystemExit internally and returns the code
    exit_code = run_cli("--version")
    captured = capsys.readouterr()
    assert __version__ in captured.out
    assert exit_code == 0


# ---------------------------------------------------------------------------
# --stats with synthetic cache dir
# ---------------------------------------------------------------------------


def test_stats_mode(tmp_path, capsys):
    """--stats prints a summary table without file listing."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_000001").write_bytes(PNG_BYTES)
    (cache_dir / "f_000002").write_bytes(JPEG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--stats")

    captured = capsys.readouterr()
    assert "Cache Stats" in captured.out
    assert "Media files found" in captured.out


# ---------------------------------------------------------------------------
# --format json
# ---------------------------------------------------------------------------


def test_format_json_outputs_json_lines(tmp_path, capsys):
    """--format json prints one JSON object per media file to stdout."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_000001").write_bytes(PNG_BYTES)
    (cache_dir / "f_000002").write_bytes(JPEG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 2, f"Expected 2 JSON lines, got {len(lines)}: {captured.out}"

    for line in lines:
        record = json.loads(line)
        assert "filename" in record
        assert "mime_type" in record
        assert "size" in record
        assert record["mime_type"] in ("image/png", "image/jpeg")


# ---------------------------------------------------------------------------
# --min-size
# ---------------------------------------------------------------------------


def test_min_size_filters_small_files(tmp_path, capsys):
    """Files below --min-size are skipped during extraction."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    # Write a tiny PNG — well below any min_size threshold
    small_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    (cache_dir / "f_000001").write_bytes(small_png)

    out_dir = tmp_path / "out"

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--output-dir", str(out_dir), "--min-size", "10000")

    # Nothing should be extracted (file is smaller than 10 000 bytes)
    assert not out_dir.exists() or len(list(out_dir.iterdir())) == 0


def test_min_size_zero_extracts_all(tmp_path, capsys):
    """--min-size 0 extracts all media regardless of size."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    tiny_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4
    (cache_dir / "f_000001").write_bytes(tiny_png)

    out_dir = tmp_path / "out"

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--output-dir", str(out_dir), "--min-size", "0")

    assert out_dir.exists()
    extracted = list(out_dir.iterdir())
    assert len(extracted) == 1
    assert extracted[0].suffix == ".png"


# ---------------------------------------------------------------------------
# Default table output
# ---------------------------------------------------------------------------


def test_default_table_output(tmp_path, capsys):
    """Default mode (no flags) prints a rich table of media files."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_000001").write_bytes(PNG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli()

    captured = capsys.readouterr()
    assert "image/png" in captured.out
    assert "f_000001" in captured.out
    assert "Media files found" in captured.out


# ---------------------------------------------------------------------------
# --output-dir extraction
# ---------------------------------------------------------------------------


def test_output_dir_extracts_files(tmp_path, capsys):
    """--output-dir extracts media files with correct extensions."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_000001").write_bytes(PNG_BYTES)
    (cache_dir / "f_000002").write_bytes(JPEG_BYTES)

    out_dir = tmp_path / "out"

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--output-dir", str(out_dir))

    assert out_dir.exists()
    extracted = {f.name for f in out_dir.iterdir()}
    # Both files should be extracted with their extensions
    png_files = [n for n in extracted if n.endswith(".png")]
    jpg_files = [n for n in extracted if n.endswith(".jpg")]
    assert len(png_files) == 1, f"Expected 1 PNG, got: {extracted}"
    assert len(jpg_files) == 1, f"Expected 1 JPEG, got: {extracted}"


# ---------------------------------------------------------------------------
# Missing cache dir
# ---------------------------------------------------------------------------


def test_missing_cache_dir_exits(tmp_path, capsys):
    """--cache-dir pointing to a non-existent path exits with code 1."""
    nonexistent = tmp_path / "no_such_dir"
    exit_code = run_cli("--cache-dir", str(nonexistent))
    assert exit_code == 1


# ---------------------------------------------------------------------------
# __version__ exposed from package
# ---------------------------------------------------------------------------


def test_version_string_format():
    """__version__ follows semver-ish format (x.y.z)."""
    from cache_crow import __version__

    parts = __version__.split(".")
    assert len(parts) == 3, f"Expected x.y.z, got: {__version__}"
    for part in parts:
        assert part.isdigit(), f"Non-numeric version component: {part!r}"
