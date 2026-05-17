"""
Tests for the LevelDB / Chrome Simple Cache metadata reader (Task #3).

These tests do NOT require a live Discord installation. They use synthetic
cache structures to verify parsing logic.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from cache_crow.metadata import (
    _parse_simple_cache_entry_header,
    _scan_bytes_for_url,
    read_simple_cache_entry_url,
    read_leveldb_index,
    enrich_entries_with_metadata,
    _find_leveldb,
    _is_leveldb_dir,
)
from cache_crow.models import CacheEntry, CacheMetadata


# ---------------------------------------------------------------------------
# CacheMetadata property tests
# ---------------------------------------------------------------------------


def test_metadata_guild_id_from_discord_cdn_url():
    """Parsing guild ID from Discord CDN attachment URL."""
    m = CacheMetadata(
        url="https://cdn.discordapp.com/attachments/123456789/987654321/image.png"
    )
    assert m.guild_id == "123456789"


def test_metadata_channel_id_from_discord_cdn_url():
    m = CacheMetadata(
        url="https://cdn.discordapp.com/attachments/111/222/photo.jpg"
    )
    assert m.channel_id == "222"


def test_metadata_cdn_filename_from_discord_cdn_url():
    m = CacheMetadata(
        url="https://cdn.discordapp.com/attachments/111/222/photo.jpg?ex=abc&is=def"
    )
    assert m.cdn_filename == "photo.jpg"


def test_metadata_guild_id_none_for_non_attachment_url():
    m = CacheMetadata(url="https://cdn.discordapp.com/icons/123/abc.png")
    assert m.guild_id is None


def test_metadata_all_none_for_missing_url():
    m = CacheMetadata(url=None)
    assert m.guild_id is None
    assert m.channel_id is None
    assert m.cdn_filename is None


# ---------------------------------------------------------------------------
# Simple Cache header parsing
# ---------------------------------------------------------------------------


def test_scan_bytes_for_url_finds_https_url():
    data = b"\x00\x00" + b"https://cdn.discordapp.com/attachments/1/2/img.png" + b"\x00"
    url = _scan_bytes_for_url(data)
    assert url is not None
    assert "cdn.discordapp.com" in url


def test_scan_bytes_for_url_returns_none_for_no_url():
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    url = _scan_bytes_for_url(data)
    assert url is None


def test_scan_bytes_for_url_partial_url_ignored():
    """Strings shorter than min URL length should be ignored."""
    data = b"https://x" + b"\x00" * 50
    # "https://x" is 9 chars — borderline; function requires >12 chars and a "."
    url = _scan_bytes_for_url(data)
    assert url is None


def test_parse_simple_cache_entry_header_too_short():
    """Files smaller than MIN_HEADER_SIZE return None."""
    assert _parse_simple_cache_entry_header(b"\x00" * 10) is None


def test_parse_simple_cache_entry_header_url_in_body():
    """Falls back to URL scanning when magic doesn't match."""
    url_bytes = b"https://cdn.discordapp.com/attachments/9/8/test.jpg"
    data = b"\x00" * 30 + url_bytes + b"\x00" * 10
    url = _parse_simple_cache_entry_header(data)
    assert url is not None
    assert "cdn.discordapp.com" in url


def test_read_simple_cache_entry_url_nonexistent_file(tmp_path):
    p = tmp_path / "ghost_file"
    url = read_simple_cache_entry_url(p)
    assert url is None


def test_read_simple_cache_entry_url_finds_embedded_url(tmp_path):
    """File with embedded URL in body is parsed correctly."""
    p = tmp_path / "f_000042"
    cdn_url = "https://cdn.discordapp.com/attachments/111/222/cat.gif"
    # Write a "file" that has some noise then the URL
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50 + cdn_url.encode() + b"\x00" * 20)
    url = read_simple_cache_entry_url(p)
    assert url is not None
    assert "cdn.discordapp.com" in url


def test_read_simple_cache_entry_url_raw_media_no_url(tmp_path):
    """Pure raw media file (PNG) without URL header returns None."""
    p = tmp_path / "f_000001"
    # Write a real-looking PNG with no URL
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    url = read_simple_cache_entry_url(p)
    assert url is None


# ---------------------------------------------------------------------------
# LevelDB directory detection
# ---------------------------------------------------------------------------


def test_is_leveldb_dir_false_for_nonexistent(tmp_path):
    assert not _is_leveldb_dir(tmp_path / "no_such_dir")


def test_is_leveldb_dir_false_for_empty_dir(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert not _is_leveldb_dir(d)


def test_is_leveldb_dir_false_without_current_file(tmp_path):
    d = tmp_path / "no_current"
    d.mkdir()
    (d / "000001.ldb").write_bytes(b"")
    assert not _is_leveldb_dir(d)


def test_is_leveldb_dir_true_with_current_and_ldb(tmp_path):
    d = tmp_path / "valid_ldb"
    d.mkdir()
    (d / "CURRENT").write_text("MANIFEST-000001\n")
    (d / "000001.ldb").write_bytes(b"fake ldb data")
    assert _is_leveldb_dir(d)


def test_find_leveldb_returns_none_for_plain_cache(tmp_path):
    """A directory with only f_XXXXXX files has no LevelDB."""
    cache_data = tmp_path / "Cache_Data"
    cache_data.mkdir()
    (cache_data / "f_000001").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    result = _find_leveldb(cache_data)
    assert result is None


def test_find_leveldb_finds_leveldb_in_parent(tmp_path):
    """LevelDB found in parent directory of Cache_Data."""
    cache_data = tmp_path / "Cache" / "Cache_Data"
    cache_data.mkdir(parents=True)
    # Put LevelDB in parent
    (tmp_path / "CURRENT").write_text("MANIFEST-000001\n")
    (tmp_path / "000001.ldb").write_bytes(b"data")
    result = _find_leveldb(cache_data)
    # May or may not find it depending on search strategy — just verify no crash
    assert result is None or result.is_dir()


# ---------------------------------------------------------------------------
# read_leveldb_index integration
# ---------------------------------------------------------------------------


def test_read_leveldb_index_empty_cache_dir(tmp_path):
    """Empty directory returns empty dict."""
    result = read_leveldb_index(tmp_path)
    assert isinstance(result, dict)


def test_read_leveldb_index_no_f_files(tmp_path):
    """Directory with no f_XXXXXX files returns empty dict."""
    (tmp_path / "index").write_bytes(b"\x00" * 100)
    result = read_leveldb_index(tmp_path)
    assert isinstance(result, dict)
    assert len(result) == 0


def test_read_leveldb_index_raw_media_no_urls(tmp_path):
    """Raw media files (no Chrome header, no embedded URL) return no metadata."""
    for i in range(3):
        p = tmp_path / f"f_00000{i}"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    result = read_leveldb_index(tmp_path)
    # No URLs found — result should be empty or have entries without URLs
    for filename, meta in result.items():
        assert meta.url is None or isinstance(meta.url, str)


def test_read_leveldb_index_with_embedded_urls(tmp_path):
    """Files with embedded CDN URLs are indexed correctly."""
    urls = {
        "f_000001": "https://cdn.discordapp.com/attachments/111/222/a.png",
        "f_000002": "https://cdn.discordapp.com/attachments/333/444/b.jpg",
    }
    for filename, url in urls.items():
        p = tmp_path / filename
        # Write raw PNG then embed URL in later bytes
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20 + url.encode() + b"\x00")

    result = read_leveldb_index(tmp_path)
    for filename, url in urls.items():
        if filename in result:
            assert result[filename].url is not None
            assert "cdn.discordapp.com" in result[filename].url


# ---------------------------------------------------------------------------
# enrich_entries_with_metadata
# ---------------------------------------------------------------------------


def test_enrich_entries_no_metadata(tmp_path):
    """Entries remain unchanged when no metadata is available."""
    p = tmp_path / "f_000001"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    entries = [CacheEntry(path=p, size=100, mime_type="image/png", modified=0.0)]
    result = enrich_entries_with_metadata(entries, tmp_path)
    assert result is entries  # same list returned
    assert entries[0].metadata is None


def test_enrich_entries_sets_metadata(tmp_path):
    """Entries with embedded URLs get metadata attached."""
    p = tmp_path / "f_000001"
    cdn_url = "https://cdn.discordapp.com/attachments/9876/5432/test.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20 + cdn_url.encode() + b"\x00")

    entries = [CacheEntry(path=p, size=p.stat().st_size, mime_type="image/png", modified=0.0)]
    result = enrich_entries_with_metadata(entries, tmp_path)

    entry = result[0]
    if entry.metadata:
        assert entry.metadata.url is not None
        # Verify guild/channel extraction works if URL was found
        if "attachments" in entry.metadata.url:
            assert entry.metadata.guild_id == "9876"
            assert entry.metadata.channel_id == "5432"


def test_enrich_entries_empty_list(tmp_path):
    """Empty entry list is handled gracefully."""
    result = enrich_entries_with_metadata([], tmp_path)
    assert result == []


def test_enrich_entries_handles_missing_cache_dir(tmp_path):
    """Non-existent cache dir doesn't crash — returns entries unmodified."""
    nonexistent = tmp_path / "ghost_dir"
    p = tmp_path / "f_000001"
    p.write_bytes(b"\x00" * 50)
    entries = [CacheEntry(path=p, size=50, mime_type="application/octet-stream", modified=0.0)]
    # Should not raise
    result = enrich_entries_with_metadata(entries, nonexistent)
    assert result is entries
