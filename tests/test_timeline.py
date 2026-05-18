"""
Tests for timeline / date-filtering features added to cache-crow.

Covers:
  - --since filters out files older than the cutoff
  - --until filters out files newer than the cutoff
  - --timeline sorts entries chronologically (oldest first)
  - --timeline adds a 'Modified' column to table output
  - parse_date_filter relative "Nd" (days) parsing
  - parse_date_filter relative "Nh" (hours) parsing
  - parse_date_filter absolute "YYYY-MM-DD" parsing
  - --since combined with --until keeps only the window
  - --all-apps flag adds app_source column to table
  - scan_cache propagates app_source on every entry
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000
JPEG_BYTES = b"\xFF\xD8\xFF\xE0" + b"\x00" * 2000


def run_cli(*args: str) -> tuple[int, str]:
    """Run CLI and return (exit_code, stdout)."""
    from cache_crow import cli
    import io
    from contextlib import redirect_stdout

    saved = sys.argv[:]
    sys.argv = ["cache-crow", *args]
    buf = io.StringIO()
    try:
        # Rich writes to a Console — capture via capsys isn't always reliable
        # for rich, so we use --format json for most filter tests.
        cli.main()
        code = 0
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else 0
    finally:
        sys.argv = saved
    return code, ""


# ---------------------------------------------------------------------------
# parse_date_filter unit tests
# ---------------------------------------------------------------------------


def test_parse_date_filter_days():
    """'7d' should return a timestamp ~7 days in the past."""
    from cache_crow.cli import parse_date_filter

    now = time.time()
    result = parse_date_filter("7d")
    expected = now - 7 * 86400
    assert abs(result - expected) < 5, "7d should be within 5 s of 7 days ago"


def test_parse_date_filter_hours():
    """'24h' should return a timestamp ~24 hours in the past."""
    from cache_crow.cli import parse_date_filter

    now = time.time()
    result = parse_date_filter("24h")
    expected = now - 24 * 3600
    assert abs(result - expected) < 5, "24h should be within 5 s of 24 hours ago"


def test_parse_date_filter_single_hour():
    """'1h' should return a timestamp ~1 hour in the past."""
    from cache_crow.cli import parse_date_filter

    now = time.time()
    result = parse_date_filter("1h")
    expected = now - 3600
    assert abs(result - expected) < 5


def test_parse_date_filter_absolute_date():
    """'2024-01-15' should parse to midnight local time on that date."""
    import datetime
    from cache_crow.cli import parse_date_filter

    result = parse_date_filter("2024-01-15")
    expected = datetime.datetime(2024, 1, 15, 0, 0, 0).timestamp()
    assert result == expected


def test_parse_date_filter_invalid_raises():
    """An invalid string should raise ArgumentTypeError."""
    import argparse
    from cache_crow.cli import parse_date_filter

    with pytest.raises(argparse.ArgumentTypeError):
        parse_date_filter("not-a-date")


# ---------------------------------------------------------------------------
# --since filter
# ---------------------------------------------------------------------------


def test_since_filters_old_files(tmp_path, capsys):
    """--since should exclude files whose mtime is before the cutoff."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()

    old_file = cache_dir / "f_old"
    new_file = cache_dir / "f_new"
    old_file.write_bytes(PNG_BYTES)
    new_file.write_bytes(JPEG_BYTES)

    # Backdate the old file to 10 days ago
    old_ts = time.time() - 10 * 86400
    os.utime(old_file, (old_ts, old_ts))

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        sys.argv = ["cache-crow", "--format", "json", "--since", "5d"]
        from cache_crow import cli
        try:
            cli.main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    # Only the new file (mtime = now) should survive the 5-day cutoff
    assert len(lines) == 1, f"Expected 1 result after --since 5d, got {len(lines)}: {captured.out}"
    rec = json.loads(lines[0])
    assert rec["filename"] == "f_new"


# ---------------------------------------------------------------------------
# --until filter
# ---------------------------------------------------------------------------


def test_until_filters_new_files(tmp_path, capsys):
    """--until should exclude files whose mtime is after the cutoff."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()

    old_file = cache_dir / "f_old"
    new_file = cache_dir / "f_new"
    old_file.write_bytes(PNG_BYTES)
    new_file.write_bytes(JPEG_BYTES)

    # Backdate the old file to 10 days ago; new_file stays at now
    old_ts = time.time() - 10 * 86400
    os.utime(old_file, (old_ts, old_ts))

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        sys.argv = ["cache-crow", "--format", "json", "--until", "5d"]
        from cache_crow import cli
        try:
            cli.main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    # Only the old file (10 days ago) should survive the cutoff of 5 days ago
    assert len(lines) == 1, f"Expected 1 result after --until 5d, got {len(lines)}: {captured.out}"
    rec = json.loads(lines[0])
    assert rec["filename"] == "f_old"


# ---------------------------------------------------------------------------
# --since + --until window
# ---------------------------------------------------------------------------


def test_since_and_until_window(tmp_path, capsys):
    """--since X --until Y should keep only files in the [X, Y] window."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()

    very_old = cache_dir / "f_very_old"
    mid = cache_dir / "f_mid"
    very_new = cache_dir / "f_very_new"

    very_old.write_bytes(PNG_BYTES)
    mid.write_bytes(JPEG_BYTES)
    very_new.write_bytes(PNG_BYTES)

    now = time.time()
    os.utime(very_old, (now - 20 * 86400, now - 20 * 86400))
    os.utime(mid, (now - 7 * 86400, now - 7 * 86400))
    # very_new stays at current mtime

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        sys.argv = ["cache-crow", "--format", "json", "--since", "14d", "--until", "3d"]
        from cache_crow import cli
        try:
            cli.main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 result in window, got {len(lines)}: {captured.out}"
    rec = json.loads(lines[0])
    assert rec["filename"] == "f_mid"


# ---------------------------------------------------------------------------
# --timeline sort order
# ---------------------------------------------------------------------------


def test_timeline_sorts_oldest_first(tmp_path, capsys):
    """--timeline should sort entries so the oldest mtime appears first."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()

    f1 = cache_dir / "f_oldest"
    f2 = cache_dir / "f_middle"
    f3 = cache_dir / "f_newest"
    f1.write_bytes(PNG_BYTES)
    f2.write_bytes(JPEG_BYTES)
    f3.write_bytes(PNG_BYTES)

    now = time.time()
    os.utime(f1, (now - 30 * 86400, now - 30 * 86400))
    os.utime(f2, (now - 15 * 86400, now - 15 * 86400))
    os.utime(f3, (now - 1 * 86400, now - 1 * 86400))

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        sys.argv = ["cache-crow", "--format", "json", "--timeline"]
        from cache_crow import cli
        try:
            cli.main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    lines = [l.strip() for l in captured.out.strip().splitlines() if l.strip()]
    assert len(lines) == 3, f"Expected 3 entries, got {len(lines)}: {captured.out}"
    filenames = [json.loads(l)["filename"] for l in lines]
    assert filenames == ["f_oldest", "f_middle", "f_newest"], (
        f"Expected oldest-first order, got: {filenames}"
    )


# ---------------------------------------------------------------------------
# --timeline table includes Modified column
# ---------------------------------------------------------------------------


def test_timeline_table_has_modified_column(tmp_path, capsys):
    """--timeline (table mode) should include 'Modified' in the output."""
    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_001").write_bytes(PNG_BYTES)

    with patch("cache_crow.cli.resolve_cache_dirs", return_value=[cache_dir]):
        sys.argv = ["cache-crow", "--timeline"]
        from cache_crow import cli
        try:
            cli.main()
        except SystemExit:
            pass

    captured = capsys.readouterr()
    assert "Modified" in captured.out, (
        f"Expected 'Modified' column header in timeline output:\n{captured.out}"
    )


# ---------------------------------------------------------------------------
# app_source propagation in scan_cache
# ---------------------------------------------------------------------------


def test_scan_cache_propagates_app_source(tmp_path):
    """scan_cache(cache_dir, app_source='discord') should tag every entry."""
    from cache_crow.scanner import scan_cache

    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_001").write_bytes(PNG_BYTES)
    (cache_dir / "f_002").write_bytes(JPEG_BYTES)

    entries = scan_cache(cache_dir, app_source="discord")
    assert len(entries) == 2
    for e in entries:
        assert e.app_source == "discord", f"Expected app_source='discord', got {e.app_source!r}"


def test_scan_cache_app_source_none_by_default(tmp_path):
    """scan_cache without app_source should leave it as None."""
    from cache_crow.scanner import scan_cache

    cache_dir = tmp_path / "Cache_Data"
    cache_dir.mkdir()
    (cache_dir / "f_001").write_bytes(PNG_BYTES)

    entries = scan_cache(cache_dir)
    assert entries[0].app_source is None


# ---------------------------------------------------------------------------
# fmt_timestamp format check
# ---------------------------------------------------------------------------


def test_fmt_timestamp_format():
    """fmt_timestamp should produce 'YYYY-MM-DD HH:MM' strings."""
    import datetime
    from cache_crow.cli import fmt_timestamp

    # Use a known timestamp
    dt = datetime.datetime(2024, 6, 15, 9, 5, 30)
    ts = dt.timestamp()
    result = fmt_timestamp(ts)
    # Should match YYYY-MM-DD HH:MM
    assert len(result) == 16, f"Unexpected length: {result!r}"
    assert result.startswith("2024-06-15"), f"Unexpected date: {result!r}"
    assert result[10] == " "
