"""Tests for cache_crow.dedup — content-based deduplication."""

import struct
from pathlib import Path

import pytest

from cache_crow.dedup import find_duplicates, pick_keeper
from cache_crow.models import CacheEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal Chrome Simple Cache header magic + EOF magic constants
_HEADER_MAGIC = 0xF27BC9AC443AAB97
_EOF_MAGIC = 0xF4FA6F7EFAF3F4F9


def _make_entry(tmp_path: Path, name: str, content: bytes, mime: str = "image/png") -> CacheEntry:
    """Write *content* to a file and return a CacheEntry for it."""
    p = tmp_path / name
    p.write_bytes(content)
    stat = p.stat()
    return CacheEntry(path=p, size=len(content), mime_type=mime, modified=stat.st_mtime)


def _make_simple_cache_entry(payload: bytes, key: str = "https://example.com/img.png") -> bytes:
    """
    Build a minimal (valid) Chrome Simple Cache file wrapping *payload* as stream 1.

    Layout:
        [Header 24B][Key key_len B][Stream1 payload][EOF1 24B][Stream0 0B][EOF0 24B]
    """
    key_bytes = key.encode("utf-8")
    key_length = len(key_bytes)

    # EOF1: stream1_size = len(payload), flags=0, crc=0, padding=0
    eof1 = struct.pack("<QIIii", _EOF_MAGIC, 0, 0, len(payload), 0)
    # EOF0: stream0_size = 0
    eof0 = struct.pack("<QIIii", _EOF_MAGIC, 0, 0, 0, 0)

    # Header: magic, version=9, key_length, key_hash=0, padding=0
    header = struct.pack("<QIIII", _HEADER_MAGIC, 9, key_length, 0, 0)

    return header + key_bytes + payload + eof1 + eof0


# ---------------------------------------------------------------------------
# Tests: find_duplicates
# ---------------------------------------------------------------------------

class TestFindDuplicates:
    def test_identical_raw_files_are_grouped(self, tmp_path):
        content = b"\x89PNG\r\n\x1a\n" + b"shared content"
        e1 = _make_entry(tmp_path, "file_a.png", content)
        e2 = _make_entry(tmp_path, "file_b.png", content)

        groups = find_duplicates([e1, e2])

        assert len(groups) == 1
        members = next(iter(groups.values()))
        assert len(members) == 2
        paths = {m.path.name for m in members}
        assert paths == {"file_a.png", "file_b.png"}

    def test_different_content_files_not_grouped(self, tmp_path):
        e1 = _make_entry(tmp_path, "alpha.png", b"\x89PNG unique alpha content")
        e2 = _make_entry(tmp_path, "beta.png",  b"\x89PNG unique beta content!")

        groups = find_duplicates([e1, e2])

        assert len(groups) == 0

    def test_simple_cache_wrappers_with_same_payload_grouped(self, tmp_path):
        """Two Simple Cache entries wrapping the same payload are duplicates."""
        payload = b"\x89PNG\r\n\x1a\n" + b"real png data here"
        sc1 = _make_simple_cache_entry(payload, key="https://cdn.example.com/a.png")
        sc2 = _make_simple_cache_entry(payload, key="https://cdn.example.com/b.png")

        e1 = _make_entry(tmp_path, "f_000001", sc1, "image/png")
        e2 = _make_entry(tmp_path, "f_000002", sc2, "image/png")

        groups = find_duplicates([e1, e2])

        # Both entries contain the same underlying payload → 1 duplicate group
        assert len(groups) == 1

    def test_empty_list_returns_no_groups(self):
        assert find_duplicates([]) == {}

    def test_single_entry_returns_no_groups(self, tmp_path):
        e = _make_entry(tmp_path, "lone.png", b"\x89PNG lonely")
        assert find_duplicates([e]) == {}

    def test_three_identical_files_in_one_group(self, tmp_path):
        content = b"\xFF\xD8\xFF" + b"jpeg shared"
        entries = [
            _make_entry(tmp_path, f"img_{i}.jpg", content, "image/jpeg")
            for i in range(3)
        ]
        groups = find_duplicates(entries)
        assert len(groups) == 1
        members = next(iter(groups.values()))
        assert len(members) == 3

    def test_multiple_distinct_duplicate_groups(self, tmp_path):
        content_a = b"\x89PNG group A"
        content_b = b"GIF89a group B"
        entries = [
            _make_entry(tmp_path, "a1.png", content_a),
            _make_entry(tmp_path, "a2.png", content_a),
            _make_entry(tmp_path, "b1.gif", content_b, "image/gif"),
            _make_entry(tmp_path, "b2.gif", content_b, "image/gif"),
            _make_entry(tmp_path, "unique.png", b"\x89PNG uniqueXXX"),
        ]
        groups = find_duplicates(entries)
        assert len(groups) == 2
        for members in groups.values():
            assert len(members) == 2


# ---------------------------------------------------------------------------
# Tests: pick_keeper
# ---------------------------------------------------------------------------

class TestPickKeeper:
    def _make_group(self, tmp_path: Path) -> list[CacheEntry]:
        """Three entries: first (small+old), middle (big+mid), newest (mid+new)."""
        import time as _time
        base = _time.time()

        e_first  = _make_entry(tmp_path, "first.png",   b"\x89PNG" + b"A" * 100)
        e_large  = _make_entry(tmp_path, "large.png",   b"\x89PNG" + b"B" * 1000)
        e_newest = _make_entry(tmp_path, "newest.png",  b"\x89PNG" + b"C" * 200)

        # Manually adjust modified times so ordering is deterministic
        e_first.modified  = base - 300
        e_large.modified  = base - 150
        e_newest.modified = base

        return [e_first, e_large, e_newest]

    def test_keep_first(self, tmp_path):
        group = self._make_group(tmp_path)
        keeper = pick_keeper(group, "first")
        assert keeper.path.name == "first.png"

    def test_keep_largest(self, tmp_path):
        group = self._make_group(tmp_path)
        keeper = pick_keeper(group, "largest")
        assert keeper.path.name == "large.png"

    def test_keep_newest(self, tmp_path):
        group = self._make_group(tmp_path)
        keeper = pick_keeper(group, "newest")
        assert keeper.path.name == "newest.png"

    def test_invalid_strategy_raises(self, tmp_path):
        group = self._make_group(tmp_path)
        with pytest.raises(ValueError, match="Unknown dedupe strategy"):
            pick_keeper(group, "random")

    def test_empty_group_raises(self):
        with pytest.raises(ValueError, match="empty"):
            pick_keeper([], "first")
