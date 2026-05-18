"""
Tests for cache_crow.db — SQLite persistence layer.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cache_crow.db import CrowDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db(tmp_path: Path) -> CrowDB:
    return CrowDB(tmp_path / "test_state.db")


# ---------------------------------------------------------------------------
# open / close / context manager
# ---------------------------------------------------------------------------


def test_db_creates_file(tmp_path):
    """Opening a CrowDB creates the SQLite file and its parent dirs."""
    db_path = tmp_path / "sub" / "state.db"
    assert not db_path.exists()

    with CrowDB(db_path):
        pass

    assert db_path.exists()


def test_db_not_open_raises(tmp_path):
    """Accessing .conn before .open() raises RuntimeError."""
    db = make_db(tmp_path)
    with pytest.raises(RuntimeError, match="not open"):
        _ = db.conn


# ---------------------------------------------------------------------------
# mark_seen
# ---------------------------------------------------------------------------


def test_mark_seen_inserts_row(tmp_path):
    """mark_seen creates a new row for a previously unseen cache path."""
    with make_db(tmp_path) as db:
        inserted = db.mark_seen(
            "/path/to/f_000001",
            mime_type="image/png",
            size_bytes=4096,
        )
    assert inserted is True


def test_mark_seen_idempotent(tmp_path):
    """Calling mark_seen twice on the same path returns False the second time."""
    with make_db(tmp_path) as db:
        first = db.mark_seen("/path/to/f_000001", mime_type="image/png", size_bytes=100)
        second = db.mark_seen("/path/to/f_000001", mime_type="image/png", size_bytes=100)
    assert first is True
    assert second is False


def test_mark_seen_is_seen(tmp_path):
    """is_seen returns True after mark_seen is called."""
    with make_db(tmp_path) as db:
        assert db.is_seen("/path/to/f_abc") is False
        db.mark_seen("/path/to/f_abc")
        assert db.is_seen("/path/to/f_abc") is True


def test_mark_seen_not_extracted(tmp_path):
    """After mark_seen, is_extracted returns False (no extracted_at set yet)."""
    with make_db(tmp_path) as db:
        db.mark_seen("/path/to/f_000001", mime_type="image/jpeg", size_bytes=2048)
        assert db.is_extracted("/path/to/f_000001") is False


def test_mark_seen_with_cdn_url(tmp_path):
    """CDN URL is stored when provided."""
    with make_db(tmp_path) as db:
        db.mark_seen(
            "/path/to/f_000001",
            cdn_url="https://cdn.discordapp.com/attachments/123/456/photo.jpg",
        )
        rows = db.history(limit=10, only_extracted=False)
    assert len(rows) == 1
    assert "cdn.discordapp.com" in (rows[0]["cdn_url"] or "")


# ---------------------------------------------------------------------------
# mark_extracted
# ---------------------------------------------------------------------------


def test_mark_extracted_sets_extracted_at(tmp_path):
    """mark_extracted sets extracted_at and is_extracted returns True."""
    ts = time.time()
    with make_db(tmp_path) as db:
        db.mark_seen("/path/to/f_000001", mime_type="image/png", size_bytes=1024)
        db.mark_extracted(
            "/path/to/f_000001",
            extracted_path="/out/f_000001.png",
            now=ts,
        )
        assert db.is_extracted("/path/to/f_000001") is True


def test_mark_extracted_without_prior_seen(tmp_path):
    """mark_extracted works even if mark_seen was never called (upsert)."""
    with make_db(tmp_path) as db:
        db.mark_extracted("/path/to/f_new", extracted_path="/out/f_new.png")
        assert db.is_extracted("/path/to/f_new") is True


def test_mark_extracted_records_path(tmp_path):
    """Extracted path is stored and retrievable via history."""
    with make_db(tmp_path) as db:
        db.mark_extracted("/path/to/f_000001", extracted_path="/out/f_000001.jpg")
        rows = db.history(limit=5)

    assert len(rows) == 1
    assert rows[0]["extracted_path"] == "/out/f_000001.jpg"


# ---------------------------------------------------------------------------
# mark_dumped
# ---------------------------------------------------------------------------


def test_mark_dumped(tmp_path):
    """mark_dumped records a dump_path and sets extracted_at."""
    with make_db(tmp_path) as db:
        db.mark_seen("/path/to/f_000001", mime_type="image/gif", size_bytes=512)
        db.mark_dumped("/path/to/f_000001", "/dump/f_000001.gif")
        rows = db.history(limit=5)

    assert len(rows) == 1
    assert rows[0]["dump_path"] == "/dump/f_000001.gif"


def test_mark_dumped_without_prior_seen(tmp_path):
    """mark_dumped works even without a prior mark_seen call."""
    with make_db(tmp_path) as db:
        db.mark_dumped("/path/to/f_standalone", "/dump/f_standalone.png")
        assert db.is_extracted("/path/to/f_standalone") is True


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


def test_history_returns_recent_first(tmp_path):
    """history() returns rows in descending extracted_at order."""
    with make_db(tmp_path) as db:
        db.mark_extracted("/path/a", extracted_path="/out/a.png", now=1000.0)
        db.mark_extracted("/path/b", extracted_path="/out/b.png", now=2000.0)
        rows = db.history(limit=10)

    # Most recent first
    assert rows[0]["extracted_at"] >= rows[1]["extracted_at"]


def test_history_limit(tmp_path):
    """history(limit=N) returns at most N rows."""
    with make_db(tmp_path) as db:
        for i in range(10):
            db.mark_extracted(f"/path/f_{i:06d}", extracted_path=f"/out/f_{i:06d}.png")
        rows = db.history(limit=3)

    assert len(rows) == 3


def test_history_only_extracted_false(tmp_path):
    """history(only_extracted=False) includes rows with no extracted_at."""
    with make_db(tmp_path) as db:
        db.mark_seen("/path/seen_only", mime_type="image/png", size_bytes=100)
        db.mark_extracted("/path/extracted", extracted_path="/out/extracted.png")

        all_rows = db.history(limit=10, only_extracted=False)
        extracted_only = db.history(limit=10, only_extracted=True)

    assert len(all_rows) == 2
    assert len(extracted_only) == 1


def test_history_empty_db(tmp_path):
    """history() on an empty DB returns an empty list."""
    with make_db(tmp_path) as db:
        rows = db.history()
    assert rows == []


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats_total_seen(tmp_path):
    """stats() counts total seen rows correctly."""
    with make_db(tmp_path) as db:
        db.mark_seen("/path/a", mime_type="image/png", size_bytes=100)
        db.mark_seen("/path/b", mime_type="image/jpeg", size_bytes=200)
        s = db.stats()

    assert s["total_seen"] == 2
    assert s["total_extracted"] == 0


def test_stats_extracted_and_dumped(tmp_path):
    """stats() tracks extracted and dumped counts separately."""
    with make_db(tmp_path) as db:
        db.mark_extracted("/path/a", extracted_path="/out/a.png")
        db.mark_dumped("/path/b", "/dump/b.gif")
        s = db.stats()

    assert s["total_extracted"] == 2  # mark_extracted + mark_dumped both set extracted_at
    assert s["total_dumped"] == 1


def test_stats_empty_db(tmp_path):
    """stats() on an empty DB returns zeros."""
    with make_db(tmp_path) as db:
        s = db.stats()

    assert s.get("total_seen", 0) == 0


# ---------------------------------------------------------------------------
# count_by_mime
# ---------------------------------------------------------------------------


def test_count_by_mime(tmp_path):
    """count_by_mime returns per-MIME counts for extracted files."""
    with make_db(tmp_path) as db:
        db.mark_seen("/a", mime_type="image/png", size_bytes=1024)
        db.mark_seen("/b", mime_type="image/png", size_bytes=2048)
        db.mark_seen("/c", mime_type="video/mp4", size_bytes=4096)
        # Only mark /a and /c as extracted
        db.mark_extracted("/a", extracted_path="/out/a.png")
        db.mark_extracted("/c", extracted_path="/out/c.mp4")
        counts = db.count_by_mime()

    by_mime = {r["mime_type"]: r["count"] for r in counts}
    # /b was only seen, not extracted, so it should NOT appear
    assert by_mime.get("image/png", 0) == 1
    assert by_mime.get("video/mp4", 0) == 1


# ---------------------------------------------------------------------------
# Path types
# ---------------------------------------------------------------------------


def test_accepts_path_objects(tmp_path):
    """mark_seen/mark_extracted accept pathlib.Path as well as strings."""
    with make_db(tmp_path) as db:
        db.mark_seen(Path("/path/to/file"), mime_type="image/jpeg", size_bytes=512)
        db.mark_extracted(Path("/path/to/file"), extracted_path=Path("/out/file.jpg"))
        assert db.is_extracted(Path("/path/to/file")) is True
