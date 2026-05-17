"""Tests for extract_media — Chrome Simple Cache wrapper stripping."""

import struct
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cache_crow.extractor import extract_media
from cache_crow.models import CacheEntry
from cache_crow.simple_cache import (
    SIMPLE_CACHE_EOF_MAGIC,
    SIMPLE_CACHE_HEADER_MAGIC,
    HEADER_SIZE,
    EOF_SIZE,
)

# ---------------------------------------------------------------------------
# Synthetic media payloads (valid magic bytes, not real images)
# ---------------------------------------------------------------------------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG_BYTES = b"\xFF\xD8\xFF\xE0" + b"\x00" * 200
GIF_BYTES = b"GIF89a" + b"\x00" * 200
UNKNOWN_BYTES = b"\xDE\xAD\xBE\xEF" + b"\x00" * 200


def make_entry(
    url: str,
    body: bytes,
    headers: bytes = b"HTTP/1.1 200 OK\r\n\r\n",
) -> bytes:
    """Build a synthetic Chrome Simple Cache entry file."""
    key = url.encode("utf-8")
    eof1 = struct.pack("<QIIii", SIMPLE_CACHE_EOF_MAGIC, 0, 0, len(body), 0)
    eof0 = struct.pack("<QIIii", SIMPLE_CACHE_EOF_MAGIC, 0, 0, len(headers), 0)
    header = struct.pack("<QIIII", SIMPLE_CACHE_HEADER_MAGIC, 5, len(key), 0, 0)
    return header + key + body + eof1 + headers + eof0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_cache_file(cache_dir: Path, name: str, data: bytes) -> Path:
    p = cache_dir / name
    p.write_bytes(data)
    return p


def _make_cache_entry(path: Path, mime_type: str) -> CacheEntry:
    return CacheEntry(
        path=path,
        size=path.stat().st_size,
        mime_type=mime_type,
        modified=time.time(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extract_wrapped_png_produces_clean_file(tmp_path):
    """Wrapped PNG entry is unwrapped; output starts with PNG magic, not cache magic."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    entry_file = _write_cache_file(cache_dir, "f_000001", make_entry("https://cdn.example.com/a.png", PNG_BYTES))
    entry = _make_cache_entry(entry_file, "image/png")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        extract_media(cache_dir, out_dir, min_size=0)

    outputs = list(out_dir.iterdir())
    assert len(outputs) == 1
    result = outputs[0].read_bytes()
    assert result[:4] == b"\x89PNG", "Expected PNG magic at start of extracted file"
    assert result[:8] == PNG_BYTES[:8]


def test_extract_wrapped_jpeg_produces_clean_file(tmp_path):
    """Wrapped JPEG entry is unwrapped; output starts with JPEG magic."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    entry_file = _write_cache_file(cache_dir, "f_000002", make_entry("https://cdn.example.com/b.jpg", JPEG_BYTES))
    entry = _make_cache_entry(entry_file, "image/jpeg")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        extract_media(cache_dir, out_dir, min_size=0)

    outputs = list(out_dir.iterdir())
    assert len(outputs) == 1
    result = outputs[0].read_bytes()
    assert result[:3] == b"\xFF\xD8\xFF", "Expected JPEG magic at start of extracted file"


def test_extract_raw_png_passes_through(tmp_path):
    """Raw PNG file (no wrapper) is copied as-is via shutil fallback."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    # Raw PNG file — no Simple Cache wrapper; scanner will classify correctly
    entry_file = _write_cache_file(cache_dir, "f_000003", PNG_BYTES)
    entry = _make_cache_entry(entry_file, "image/png")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        extract_media(cache_dir, out_dir, min_size=0)

    outputs = list(out_dir.iterdir())
    assert len(outputs) == 1
    assert outputs[0].read_bytes() == PNG_BYTES


def test_extract_stats_counts_extracted(tmp_path):
    """stats['extracted'] is 1 for a single valid media entry."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    entry_file = _write_cache_file(cache_dir, "f_000010", make_entry("https://cdn.example.com/x.png", PNG_BYTES))
    entry = _make_cache_entry(entry_file, "image/png")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        stats = extract_media(cache_dir, out_dir, min_size=0)

    assert stats["extracted"] == 1
    assert stats["skipped"] == 0
    assert stats["total_scanned"] == 1


def test_extract_skips_small_files(tmp_path):
    """Files smaller than min_size are counted as skipped, not extracted."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    small_data = PNG_BYTES[:50]  # well under default min_size=1024
    entry_file = _write_cache_file(cache_dir, "f_000020", small_data)
    entry = _make_cache_entry(entry_file, "image/png")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        stats = extract_media(cache_dir, out_dir, min_size=1024)

    assert stats["skipped"] == 1
    assert stats["extracted"] == 0
    assert not any(out_dir.iterdir()) if out_dir.exists() else True


def test_extract_skips_non_media_types(tmp_path):
    """Files whose MIME type is not in MEDIA_TYPES are skipped."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    entry_file = _write_cache_file(cache_dir, "f_000030", UNKNOWN_BYTES)
    entry = _make_cache_entry(entry_file, "application/octet-stream")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        stats = extract_media(cache_dir, out_dir, min_size=0)

    assert stats["skipped"] == 1
    assert stats["extracted"] == 0


def test_extract_multiple_entries(tmp_path):
    """Three wrapped files (PNG, JPEG, GIF) are all extracted and all clean."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "out"

    files_and_mimes = [
        ("f_000041", make_entry("https://cdn.example.com/p.png", PNG_BYTES), "image/png",  b"\x89PNG"),
        ("f_000042", make_entry("https://cdn.example.com/j.jpg", JPEG_BYTES), "image/jpeg", b"\xFF\xD8\xFF\xE0"),
        ("f_000043", make_entry("https://cdn.example.com/g.gif", GIF_BYTES), "image/gif",  b"GIF8"),
    ]

    entries = []
    for name, data, mime, _ in files_and_mimes:
        p = _write_cache_file(cache_dir, name, data)
        entries.append(_make_cache_entry(p, mime))

    with patch("cache_crow.extractor.scan_cache", return_value=entries):
        stats = extract_media(cache_dir, out_dir, min_size=0)

    assert stats["extracted"] == 3
    assert stats["skipped"] == 0

    outputs = {p.name: p.read_bytes() for p in out_dir.iterdir()}
    assert len(outputs) == 3

    # Each output file must start with its respective media magic
    for name, _data, _mime, expected_magic in files_and_mimes:
        # Output filename is the cache filename + extension
        matching = [v for k, v in outputs.items() if k.startswith(name)]
        assert len(matching) == 1, f"Expected one output for {name}"
        n = len(expected_magic)
        assert matching[0][:n] == expected_magic, (
            f"{name}: expected {expected_magic!r}, got {matching[0][:n]!r}"
        )


def test_extract_creates_output_dir(tmp_path):
    """extract_media creates output_dir if it does not exist."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out_dir = tmp_path / "deeply" / "nested" / "output"

    assert not out_dir.exists()

    entry_file = _write_cache_file(cache_dir, "f_000050", make_entry("https://cdn.example.com/c.png", PNG_BYTES))
    entry = _make_cache_entry(entry_file, "image/png")

    with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
        extract_media(cache_dir, out_dir, min_size=0)

    assert out_dir.exists() and out_dir.is_dir()
    assert len(list(out_dir.iterdir())) == 1
