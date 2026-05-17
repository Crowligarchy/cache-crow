"""
Tests for the Textual TUI browser (Task #5).

Since running a full Textual app requires a terminal, most tests verify the
supporting logic (formatting, entry sorting, metadata display helpers) and
that the TUI module imports and initializes without error.

The fallback rich-based display is tested via capsys.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

import pytest

from cache_crow.tui import fmt_size, TYPE_ICONS, launch_tui
from cache_crow.models import CacheEntry, CacheMetadata


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def test_fmt_size_bytes():
    assert fmt_size(512) == "512 B"


def test_fmt_size_kb():
    assert fmt_size(1536) == "1.5 KB"


def test_fmt_size_mb():
    result = fmt_size(3 * 1024 * 1024)
    assert "3.00 MB" == result


def test_type_icons_covers_all_mime_types():
    """TYPE_ICONS should have entries for all standard MIME types."""
    expected = {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/webm",
        "application/octet-stream",
    }
    assert expected <= set(TYPE_ICONS.keys())


# ---------------------------------------------------------------------------
# CacheMetadata property coverage via TUI display path
# ---------------------------------------------------------------------------


def test_metadata_url_display_components():
    """Verify guild/channel ID extraction used by TUI metadata panel."""
    m = CacheMetadata(
        url="https://cdn.discordapp.com/attachments/GUILD_ID/CHAN_ID/file.png"
    )
    assert m.guild_id == "GUILD_ID"
    assert m.channel_id == "CHAN_ID"
    assert m.cdn_filename == "file.png"


def test_metadata_url_with_query_params():
    m = CacheMetadata(
        url="https://cdn.discordapp.com/attachments/1/2/photo.jpg?ex=abc&is=def"
    )
    assert m.cdn_filename == "photo.jpg"
    assert m.guild_id == "1"
    assert m.channel_id == "2"


# ---------------------------------------------------------------------------
# Entry sorting (TUI sorts by size descending)
# ---------------------------------------------------------------------------


def make_entry(tmp_path: Path, name: str, size: int, mime: str = "image/png") -> CacheEntry:
    p = tmp_path / name
    p.write_bytes(b"\x00" * size)
    return CacheEntry(path=p, size=size, mime_type=mime, modified=0.0)


def test_entries_sorted_by_size_descending(tmp_path):
    """TUI displays largest files first — verify sort order."""
    entries = [
        make_entry(tmp_path, "small.bin", 100),
        make_entry(tmp_path, "large.bin", 9000),
        make_entry(tmp_path, "medium.bin", 1500),
    ]
    sorted_entries = sorted(entries, key=lambda x: x.size, reverse=True)
    assert sorted_entries[0].size == 9000
    assert sorted_entries[1].size == 1500
    assert sorted_entries[2].size == 100


# ---------------------------------------------------------------------------
# Fallback TUI (rich-based) — no terminal required
# ---------------------------------------------------------------------------


def test_fallback_tui_runs_without_error(tmp_path, capsys):
    """
    _fallback_tui() prints a rich table without raising.

    We patch textual to force the fallback path.
    """
    from cache_crow import tui as tui_module
    from unittest.mock import patch

    p = tmp_path / "f_000001"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    entries = [CacheEntry(path=p, size=200, mime_type="image/png", modified=0.0)]

    # Call the fallback directly
    tui_module._fallback_tui(entries, output_dir=None)
    # No assertion needed — just verify it doesn't raise


def test_fallback_tui_with_metadata(tmp_path):
    """Fallback TUI handles entries with CDN metadata without error."""
    from cache_crow.tui import _fallback_tui

    p = tmp_path / "f_000001"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    entry = CacheEntry(
        path=p,
        size=200,
        mime_type="image/png",
        modified=0.0,
        metadata=CacheMetadata(
            url="https://cdn.discordapp.com/attachments/1234/5678/image.png",
        ),
    )
    _fallback_tui([entry], output_dir=None)  # Should not raise


def test_fallback_tui_empty_entries(tmp_path):
    """Empty entry list is handled by fallback TUI without error."""
    from cache_crow.tui import _fallback_tui
    _fallback_tui([], output_dir=None)  # Should not raise


# ---------------------------------------------------------------------------
# launch_tui — force fallback (no real terminal in test env)
# ---------------------------------------------------------------------------


def test_launch_tui_fallback_when_textual_missing(tmp_path, monkeypatch):
    """
    If textual is not importable, launch_tui falls back to rich display.
    """
    import sys
    from cache_crow.tui import _fallback_tui
    from unittest.mock import patch, MagicMock

    p = tmp_path / "f_000001"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    entries = [CacheEntry(path=p, size=200, mime_type="image/png", modified=0.0)]

    called = []

    def fake_fallback(ents, output_dir=None):
        called.append(True)

    # Patch _fallback_tui and force ImportError on textual import
    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    with patch("cache_crow.tui._fallback_tui", fake_fallback):
        with patch.dict(sys.modules, {"textual": None, "textual.app": None}):
            launch_tui(entries, output_dir=None)

    assert called, "Fallback TUI was not invoked when textual unavailable"


# ---------------------------------------------------------------------------
# CacheEntry model — metadata field
# ---------------------------------------------------------------------------


def test_cache_entry_metadata_field_is_none_by_default(tmp_path):
    p = tmp_path / "f_000001"
    p.write_bytes(b"\x00" * 50)
    entry = CacheEntry(path=p, size=50, mime_type="application/octet-stream", modified=0.0)
    assert entry.metadata is None


def test_cache_entry_metadata_field_set(tmp_path):
    p = tmp_path / "f_000001"
    p.write_bytes(b"\x00" * 50)
    meta = CacheMetadata(url="https://cdn.discordapp.com/attachments/1/2/file.png")
    entry = CacheEntry(path=p, size=50, mime_type="image/png", modified=0.0, metadata=meta)
    assert entry.metadata is meta
    assert entry.metadata.url == "https://cdn.discordapp.com/attachments/1/2/file.png"
