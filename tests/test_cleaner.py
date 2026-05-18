"""Tests for cache_crow.cleaner — select_for_clearing and clear_cache."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cache_crow.cleaner import clear_cache, select_for_clearing
from cache_crow.models import CacheEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    path: Path,
    size: int = 1024,
    mime_type: str = "image/png",
    age_days: float = 0.0,
) -> CacheEntry:
    """Create a synthetic CacheEntry with a modified timestamp *age_days* in the past."""
    modified = time.time() - age_days * 86400
    return CacheEntry(
        path=path,
        size=size,
        mime_type=mime_type,
        modified=modified,
        mtime=modified,
        ctime=modified,
    )


# ---------------------------------------------------------------------------
# select_for_clearing — age filter
# ---------------------------------------------------------------------------


def test_select_older_than_keeps_old_entries(tmp_path: Path) -> None:
    """Entries older than the cutoff are selected; recent ones are not."""
    old = _entry(tmp_path / "old.bin", age_days=10)
    recent = _entry(tmp_path / "recent.bin", age_days=1)
    result = select_for_clearing([old, recent], older_than_days=7)
    assert result == [old]
    assert recent not in result


def test_select_older_than_boundary(tmp_path: Path) -> None:
    """Entries must be STRICTLY older than the cutoff to be selected.

    An entry that is only 6 days old when the cutoff is 7 days is NOT selected.
    An entry that is 8 days old IS selected.
    """
    not_old_enough = _entry(tmp_path / "six_days.bin", age_days=6)
    old_enough = _entry(tmp_path / "eight_days.bin", age_days=8)
    result = select_for_clearing([not_old_enough, old_enough], older_than_days=7)
    assert not_old_enough not in result
    assert old_enough in result


def test_select_no_age_filter_returns_all(tmp_path: Path) -> None:
    """When older_than_days is None, no age filter is applied."""
    entries = [_entry(tmp_path / f"{i}.bin", age_days=i) for i in range(5)]
    result = select_for_clearing(entries, older_than_days=None)
    assert result == entries


# ---------------------------------------------------------------------------
# select_for_clearing — size filters
# ---------------------------------------------------------------------------


def test_select_smaller_than(tmp_path: Path) -> None:
    """Only entries strictly smaller than the threshold are selected."""
    small = _entry(tmp_path / "small.bin", size=500)
    large = _entry(tmp_path / "large.bin", size=2000)
    result = select_for_clearing([small, large], smaller_than_bytes=1024)
    assert result == [small]


def test_select_larger_than(tmp_path: Path) -> None:
    """Only entries strictly larger than the threshold are selected."""
    small = _entry(tmp_path / "small.bin", size=500)
    large = _entry(tmp_path / "large.bin", size=2000)
    result = select_for_clearing([small, large], larger_than_bytes=1000)
    assert result == [large]


# ---------------------------------------------------------------------------
# select_for_clearing — MIME type filter (partial match)
# ---------------------------------------------------------------------------


def test_select_mime_exact_match(tmp_path: Path) -> None:
    """Exact MIME type string selects the matching entry."""
    img = _entry(tmp_path / "img.bin", mime_type="image/png")
    vid = _entry(tmp_path / "vid.bin", mime_type="video/mp4")
    result = select_for_clearing([img, vid], mime_types=["image/png"])
    assert result == [img]


def test_select_mime_partial_match(tmp_path: Path) -> None:
    """Partial string 'video' matches all video/* MIME types."""
    mp4 = _entry(tmp_path / "a.bin", mime_type="video/mp4")
    webm = _entry(tmp_path / "b.bin", mime_type="video/webm")
    png = _entry(tmp_path / "c.bin", mime_type="image/png")
    result = select_for_clearing([mp4, webm, png], mime_types=["video"])
    assert mp4 in result
    assert webm in result
    assert png not in result


def test_select_mime_multiple_types(tmp_path: Path) -> None:
    """Multiple MIME strings form an OR — any match is sufficient."""
    mp4 = _entry(tmp_path / "a.bin", mime_type="video/mp4")
    png = _entry(tmp_path / "b.bin", mime_type="image/png")
    gif = _entry(tmp_path / "c.bin", mime_type="image/gif")
    octet = _entry(tmp_path / "d.bin", mime_type="application/octet-stream")
    result = select_for_clearing([mp4, png, gif, octet], mime_types=["video", "image/gif"])
    assert mp4 in result
    assert gif in result
    assert png not in result
    assert octet not in result


# ---------------------------------------------------------------------------
# select_for_clearing — AND logic with multiple filters
# ---------------------------------------------------------------------------


def test_select_combined_and_logic(tmp_path: Path) -> None:
    """All filters must match simultaneously (AND semantics)."""
    # old + small image   → should be selected
    old_small_img = _entry(tmp_path / "a.bin", size=100, mime_type="image/png", age_days=10)
    # old + large image   → size filter kills it
    old_large_img = _entry(tmp_path / "b.bin", size=5000, mime_type="image/png", age_days=10)
    # recent + small image → age filter kills it
    new_small_img = _entry(tmp_path / "c.bin", size=100, mime_type="image/png", age_days=1)
    # old + small video   → type filter kills it
    old_small_vid = _entry(tmp_path / "d.bin", size=100, mime_type="video/mp4", age_days=10)

    result = select_for_clearing(
        [old_small_img, old_large_img, new_small_img, old_small_vid],
        older_than_days=7,
        smaller_than_bytes=1000,
        mime_types=["image"],
    )
    assert result == [old_small_img]


# ---------------------------------------------------------------------------
# clear_cache — dry_run=True
# ---------------------------------------------------------------------------


def test_clear_dry_run_does_not_delete(tmp_path: Path) -> None:
    """dry_run=True must not touch the filesystem."""
    f = tmp_path / "file.bin"
    f.write_bytes(b"\x89PNG" + b"\x00" * 100)
    entry = _entry(f, size=f.stat().st_size)

    result = clear_cache(tmp_path, [entry], dry_run=True)

    assert f.exists(), "File should NOT be deleted in dry-run mode"
    assert result["removed"] == 0
    assert result["freed_bytes"] == entry.size
    assert result["errors"] == []


def test_clear_dry_run_reports_would_free(tmp_path: Path) -> None:
    """freed_bytes in dry_run mode equals the sum of entry sizes."""
    files = []
    entries = []
    for i, size in enumerate([100, 200, 300]):
        f = tmp_path / f"file{i}.bin"
        f.write_bytes(b"\x00" * size)
        e = _entry(f, size=size)
        files.append(f)
        entries.append(e)

    result = clear_cache(tmp_path, entries, dry_run=True)

    assert result["removed"] == 0
    assert result["freed_bytes"] == 600
    assert all(f.exists() for f in files)


# ---------------------------------------------------------------------------
# clear_cache — dry_run=False
# ---------------------------------------------------------------------------


def test_clear_live_deletes_files(tmp_path: Path) -> None:
    """dry_run=False removes the files and reports correct stats."""
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"\x00" * 400)
    f2.write_bytes(b"\x00" * 600)
    e1 = _entry(f1, size=400)
    e2 = _entry(f2, size=600)

    result = clear_cache(tmp_path, [e1, e2], dry_run=False)

    assert not f1.exists()
    assert not f2.exists()
    assert result["removed"] == 2
    assert result["freed_bytes"] == 1000
    assert result["errors"] == []


def test_clear_live_handles_missing_file_gracefully(tmp_path: Path) -> None:
    """If a file is already gone, the error is captured and returned, not raised."""
    ghost = tmp_path / "ghost.bin"
    # Do NOT create the file — it doesn't exist on disk.
    entry = _entry(ghost, size=512)

    result = clear_cache(tmp_path, [entry], dry_run=False)

    assert result["removed"] == 0
    assert result["freed_bytes"] == 0
    assert len(result["errors"]) == 1
    assert "ghost.bin" in result["errors"][0]


def test_clear_live_partial_failure(tmp_path: Path) -> None:
    """Existing files are deleted even when one entry in the list is missing."""
    present = tmp_path / "present.bin"
    present.write_bytes(b"\x00" * 256)
    missing = tmp_path / "missing.bin"

    e_present = _entry(present, size=256)
    e_missing = _entry(missing, size=256)

    result = clear_cache(tmp_path, [e_present, e_missing], dry_run=False)

    assert not present.exists()
    assert result["removed"] == 1
    assert result["freed_bytes"] == 256
    assert len(result["errors"]) == 1


def test_clear_empty_list(tmp_path: Path) -> None:
    """Clearing an empty selection always returns zeroed stats with no errors."""
    result = clear_cache(tmp_path, [], dry_run=False)
    assert result == {"removed": 0, "freed_bytes": 0, "errors": []}

    result_dry = clear_cache(tmp_path, [], dry_run=True)
    assert result_dry == {"removed": 0, "freed_bytes": 0, "errors": []}
