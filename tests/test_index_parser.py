"""Tests for cache_crow.index_parser — all synthetic, no real cache files required."""
import struct
import tempfile
from pathlib import Path

import pytest

from cache_crow.index_parser import (
    INDEX_ENTRY_FMT,
    INDEX_ENTRY_SIZE,
    INDEX_HEADER_FMT,
    INDEX_HEADER_SIZE,
    INDEX_MAGIC,
    CacheIndex,
    IndexEntry,
    parse_index,
    read_cache_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_index(
    entries: list[tuple[int, int, int, int]],
    *,
    version: int = 8,
    magic: int = INDEX_MAGIC,
    cache_size: int = 0,
    truncate_after_entries: int | None = None,
) -> bytes:
    """
    Build a synthetic Chrome Simple Cache index binary.

    entries: list of (hash, entry_size_blocks, last_used_time, last_modified_time)
    truncate_after_entries: if set, only serialise this many entries (header still
                            claims len(entries) so the file appears truncated).
    """
    num_entries = len(entries)
    reason = 0
    pad = 0
    header = struct.pack(
        INDEX_HEADER_FMT,
        magic,
        version,
        num_entries,
        cache_size,
        reason,
        pad,
    )

    n_to_write = truncate_after_entries if truncate_after_entries is not None else num_entries
    body = b""
    for hash_val, entry_size, last_used, last_mod in entries[:n_to_write]:
        body += struct.pack(INDEX_ENTRY_FMT, hash_val, entry_size, 0, last_used, last_mod)

    return header + body


def write_tmp(data: bytes, filename: str = "index") -> Path:
    """Write bytes to a named temp file and return the Path."""
    tmp = tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False)
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# parse_index tests
# ---------------------------------------------------------------------------

def test_parse_index_nonexistent_file():
    result = parse_index(Path("/nonexistent/path/index"))
    assert result is None


def test_parse_index_empty_file():
    path = write_tmp(b"")
    try:
        result = parse_index(path)
        assert result is None
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_wrong_magic():
    data = make_index([], magic=0xDEADBEEFCAFEBABE)
    path = write_tmp(data)
    try:
        result = parse_index(path)
        assert result is None
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_valid_no_entries():
    data = make_index([])
    path = write_tmp(data)
    try:
        result = parse_index(path)
        assert result is not None
        assert isinstance(result, CacheIndex)
        assert result.num_entries == 0
        assert result.entries == []
        assert result.version == 8
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_valid_single_entry():
    entry_hash = 0xABCD1234EF015678  # valid uint64
    last_used = 1_000_000
    last_mod = 2_000_000
    entry_size = 42
    data = make_index([(entry_hash, entry_size, last_used, last_mod)])
    path = write_tmp(data)
    try:
        result = parse_index(path)
        assert result is not None
        assert result.num_entries == 1
        assert len(result.entries) == 1
        e = result.entries[0]
        assert e.hash == entry_hash
        assert e.last_used_time == last_used
        assert e.last_modified_time == last_mod
        assert e.entry_size_blocks == entry_size
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_valid_multiple_entries():
    entries = [
        (0x0000000000000001, 10, 100, 200),
        (0x0000000000000002, 20, 300, 400),
        (0x0000000000000003, 30, 500, 600),
        (0x0000000000000004, 40, 700, 800),
        (0x0000000000000005, 50, 900, 1000),
    ]
    data = make_index(entries)
    path = write_tmp(data)
    try:
        result = parse_index(path)
        assert result is not None
        assert result.num_entries == 5
        assert len(result.entries) == 5
    finally:
        path.unlink(missing_ok=True)


def test_parse_index_truncated_entries():
    """Header declares 10 entries but file only contains 3 — should return 3, no crash."""
    all_entries = [(i, i * 5, i * 100, i * 200) for i in range(1, 11)]
    # Build binary that only serialises 3 entries despite header claiming 10
    data = make_index(all_entries, truncate_after_entries=3)
    path = write_tmp(data)
    try:
        result = parse_index(path)
        assert result is not None
        # num_entries reflects what the header says
        assert result.num_entries == 10
        # entries list reflects what was actually present
        assert len(result.entries) == 3
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# read_cache_index tests
# ---------------------------------------------------------------------------

def test_read_cache_index_finds_index_file():
    """read_cache_index should find and parse an 'index' file in cache_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        index_data = make_index([(0xDEADBEEF00000001, 7, 111, 222)])
        (cache_dir / "index").write_bytes(index_data)

        result = read_cache_index(cache_dir)
        assert result is not None
        assert len(result.entries) == 1
        assert result.entries[0].hash == 0xDEADBEEF00000001


def test_read_cache_index_finds_index_dir_variant():
    """read_cache_index should also check index-dir/the-real-index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        index_dir = cache_dir / "index-dir"
        index_dir.mkdir()
        index_data = make_index([(0xCAFEBABE12345678, 3, 555, 666)])
        (index_dir / "the-real-index").write_bytes(index_data)

        result = read_cache_index(cache_dir)
        assert result is not None
        assert result.entries[0].hash == 0xCAFEBABE12345678


def test_read_cache_index_missing():
    """No index file present → None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = read_cache_index(Path(tmpdir))
        assert result is None


# ---------------------------------------------------------------------------
# Field-level correctness
# ---------------------------------------------------------------------------

def test_index_entry_fields():
    """Verify every field of a parsed IndexEntry matches the synthesised input."""
    h = 0x123456789ABCDEF0
    sz = 99
    lu = 0xDEAD_BEEF
    lm = 0xCAFE_BABE

    data = make_index([(h, sz, lu, lm)], version=9, cache_size=131072)
    path = write_tmp(data)
    try:
        result = parse_index(path)
        assert result is not None
        assert result.version == 9
        assert result.cache_size_bytes == 131072
        e = result.entries[0]
        assert isinstance(e, IndexEntry)
        assert e.hash == h
        assert e.entry_size_blocks == sz
        assert e.last_used_time == lu
        assert e.last_modified_time == lm
    finally:
        path.unlink(missing_ok=True)
