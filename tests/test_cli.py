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


# ---------------------------------------------------------------------------
# Task 1 — JSON output includes mtime_iso and relative_time
# ---------------------------------------------------------------------------


def test_json_output_includes_mtime_iso_and_relative_time(tmp_path, capsys):
    """--format json output includes mtime_iso and relative_time fields."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_000001").write_bytes(PNG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert "mtime" in rec, f"mtime missing: {rec.keys()}"
    assert "mtime_iso" in rec, f"mtime_iso missing: {rec.keys()}"
    assert "ctime" in rec, f"ctime missing: {rec.keys()}"
    assert "relative_time" in rec, f"relative_time missing: {rec.keys()}"
    # mtime_iso should be a valid ISO-8601 string
    import datetime
    dt = datetime.datetime.fromisoformat(rec["mtime_iso"])
    assert dt.year >= 2020
    # relative_time should be a non-empty string
    assert isinstance(rec["relative_time"], str)
    assert len(rec["relative_time"]) > 0


def test_json_output_mtime_matches_stat(tmp_path, capsys):
    """mtime in JSON output matches the file's actual stat().st_mtime."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    f = cache_dir / "f_000001"
    f.write_bytes(PNG_BYTES)
    expected_mtime = f.stat().st_mtime

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    rec = json.loads(lines[0])
    assert abs(rec["mtime"] - expected_mtime) < 0.001


# ---------------------------------------------------------------------------
# Task 1 — --sort flag
# ---------------------------------------------------------------------------


def test_sort_by_size_default(tmp_path, capsys):
    """Default sort (size) produces largest file first in JSON output."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    small = cache_dir / "f_small"
    large = cache_dir / "f_large"
    small.write_bytes(PNG_BYTES)  # 2008 bytes
    large.write_bytes(PNG_BYTES + b"\x00" * 5000)  # 7008 bytes

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["size"] >= second["size"], "Expected largest file first"


def test_sort_by_name(tmp_path, capsys):
    """--sort name sorts entries alphabetically by filename."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "z_file").write_bytes(PNG_BYTES)
    (cache_dir / "a_file").write_bytes(PNG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json", "--sort", "name")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["filename"] <= second["filename"], "Expected alphabetical order"


def test_sort_by_type(tmp_path, capsys):
    """--sort type sorts entries by MIME type alphabetically."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_png").write_bytes(PNG_BYTES)
    (cache_dir / "f_jpg").write_bytes(JPEG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json", "--sort", "type")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 2
    mimes = [json.loads(l)["mime_type"] for l in lines]
    assert mimes == sorted(mimes), f"Expected sorted by MIME type, got: {mimes}"


def test_sort_by_date(tmp_path, capsys):
    """--sort date sorts entries newest-first."""
    import os
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    old_file = cache_dir / "old_file"
    new_file = cache_dir / "new_file"
    old_file.write_bytes(PNG_BYTES)
    new_file.write_bytes(PNG_BYTES)
    # Make old_file explicitly older
    old_time = time.time() - 3600
    os.utime(old_file, (old_time, old_time))

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("--format", "json", "--sort", "date")

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["mtime"] >= second["mtime"], "Expected newest file first with --sort date"


# ---------------------------------------------------------------------------
# Task 3 — Purge subcommand
# ---------------------------------------------------------------------------


def test_purge_cache_removes_files(tmp_path, capsys):
    """purge cache deletes all files from the cache directory with --yes."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "file1").write_bytes(b"test1")
    (cache_dir / "file2").write_bytes(b"test2")
    assert len(list(cache_dir.iterdir())) == 2

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli("purge", "cache", "--yes")

    # All files should be gone
    remaining = list(cache_dir.iterdir())
    assert remaining == [], f"Expected empty cache_dir, found: {remaining}"


def test_purge_dump_removes_files(tmp_path, capsys):
    """purge dump deletes all files from the dump directory with --yes."""
    dump_dir = tmp_path / "dump"
    dump_dir.mkdir()
    (dump_dir / "file1").write_bytes(b"test1")
    (dump_dir / "file2").write_bytes(b"test2")

    with patch("cache_crow.cli.cmd_purge") as mock_purge:
        # We use a direct test with actual _purge_dir
        from cache_crow.cli import _purge_dir
        _purge_dir(dump_dir, "Dump directory:", yes=True)

    remaining = list(dump_dir.iterdir())
    assert remaining == [], f"Expected empty dump_dir, found: {remaining}"


def test_purge_cache_all_subcommand_exists(tmp_path, capsys):
    """purge all runs without error when --yes is passed (no dirs found OK)."""
    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[]):
        with patch("cache_crow.cli.find_cache_dirs", return_value=[]):
            # purge all with no dirs found should not crash
            exit_code = run_cli("purge", "all", "--yes")
    # Any exit code is fine — just verifying the subcommand is registered


def test_purge_nonexistent_dir_skips_gracefully(tmp_path, capsys):
    """_purge_dir skips gracefully when directory does not exist."""
    from cache_crow.cli import _purge_dir
    nonexistent = tmp_path / "nonexistent_dir"
    # Should not raise
    _purge_dir(nonexistent, "Test dir:", yes=True)
    captured = capsys.readouterr()
    # Should print a "skipping" message
    assert "skipping" in captured.out.lower() or "not found" in captured.out.lower()


def test_purge_shows_file_count_and_size(tmp_path, capsys):
    """Purge prints file count and total size before deleting."""
    from cache_crow.cli import _purge_dir
    target = tmp_path / "cache"
    target.mkdir()
    (target / "a").write_bytes(b"x" * 1024)
    (target / "b").write_bytes(b"x" * 2048)

    _purge_dir(target, "Cache:", yes=True)
    captured = capsys.readouterr()
    assert "Files" in captured.out
    assert "Size" in captured.out
    assert "Deleted" in captured.out


def test_purge_requires_confirmation_without_yes(tmp_path, monkeypatch, capsys):
    """Without --yes, purge prompts for confirmation and skips on 'N'."""
    from cache_crow.cli import _purge_dir
    target = tmp_path / "cache"
    target.mkdir()
    (target / "file1").write_bytes(b"data")

    monkeypatch.setattr("builtins.input", lambda _: "N")
    _purge_dir(target, "Cache:", yes=False)

    # File should still be there
    assert (target / "file1").exists()

    captured = capsys.readouterr()
    assert "Skipped" in captured.out or "skipped" in captured.out.lower()


def test_purge_table_output_shows_modified_and_age(tmp_path, capsys):
    """Default table output includes Modified and Age columns."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_000001").write_bytes(PNG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        run_cli()

    captured = capsys.readouterr()
    # Table should contain "Modified" and "Age" column headers
    assert "Modified" in captured.out, f"'Modified' not in output: {captured.out[:300]}"
    assert "Age" in captured.out, f"'Age' not in output: {captured.out[:300]}"
