"""Tests for Chrome Simple Cache entry file parser."""

import io
import os
import struct
import tempfile
import zlib
from pathlib import Path

import pytest

from cache_crow.simple_cache import (
    EOF_SIZE,
    HEADER_SIZE,
    SIMPLE_CACHE_EOF_MAGIC as EOF_MAGIC,
    SIMPLE_CACHE_HEADER_MAGIC as HEADER_MAGIC,
    extract_key,
    extract_stream1,
    is_simple_cache_entry,
    parse_eof_record,
    parse_header,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_entry(
    url: str,
    body: bytes,
    headers: bytes = b"HTTP/1.1 200 OK\r\n\r\n",
) -> bytes:
    """Build a synthetic Chrome Simple Cache entry file."""
    key = url.encode("utf-8")
    key_len = len(key)

    eof1 = struct.pack("<QIIii", EOF_MAGIC, 0, 0, len(body), 0)
    eof0 = struct.pack("<QIIii", EOF_MAGIC, 0, 0, len(headers), 0)
    header = struct.pack("<QIIIi", HEADER_MAGIC, 5, key_len, 0, 0)

    return header + key + body + eof1 + headers + eof0


# Minimal synthetic image payloads (valid magic bytes only — not real images)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
JPEG_MAGIC = b"\xFF\xD8\xFF\xE0" + b"\x00" * 50

# ---------------------------------------------------------------------------
# is_simple_cache_entry
# ---------------------------------------------------------------------------

def test_is_simple_cache_entry_valid():
    data = make_entry("https://example.com/image.png", PNG_MAGIC)
    assert is_simple_cache_entry(data) is True


def test_is_simple_cache_entry_raw_png():
    assert is_simple_cache_entry(PNG_MAGIC) is False


# ---------------------------------------------------------------------------
# parse_header
# ---------------------------------------------------------------------------

def test_parse_header_valid():
    url = "https://cdn.discordapp.com/attachments/test.png"
    data = make_entry(url, PNG_MAGIC)
    result = parse_header(data)
    assert result is not None
    key_length, version = result
    assert key_length == len(url.encode("utf-8"))
    assert version == 5


def test_parse_header_invalid_magic():
    bad_data = b"\x00" * 24
    assert parse_header(bad_data) is None


def test_parse_header_too_short():
    assert parse_header(b"\x00" * 10) is None


# ---------------------------------------------------------------------------
# parse_eof_record
# ---------------------------------------------------------------------------

def test_parse_eof_record_valid():
    stream_size = 12345
    flags = 0b11
    record = struct.pack("<QIIii", EOF_MAGIC, flags, 0xDEADBEEF, stream_size, 0)
    result = parse_eof_record(record)
    assert result is not None
    assert result == (stream_size, flags)


def test_parse_eof_record_invalid():
    bad_record = struct.pack("<QIIii", 0xDEADBEEFCAFEBABE, 0, 0, 100, 0)
    assert parse_eof_record(bad_record) is None


# ---------------------------------------------------------------------------
# extract_key
# ---------------------------------------------------------------------------

def test_extract_key_valid():
    url = "https://cdn.discordapp.com/avatars/123456789/abc.png"
    data = make_entry(url, PNG_MAGIC)
    assert extract_key(data) == url


# ---------------------------------------------------------------------------
# extract_stream1
# ---------------------------------------------------------------------------

def test_extract_stream1_png_body(tmp_path):
    url = "https://example.com/image.png"
    entry_data = make_entry(url, PNG_MAGIC)
    entry_file = tmp_path / "f_000001"
    entry_file.write_bytes(entry_data)

    result = extract_stream1(entry_file)
    assert result == PNG_MAGIC


def test_extract_stream1_jpeg_body(tmp_path):
    url = "https://example.com/photo.jpg"
    entry_data = make_entry(url, JPEG_MAGIC)
    entry_file = tmp_path / "f_000002"
    entry_file.write_bytes(entry_data)

    result = extract_stream1(entry_file)
    assert result == JPEG_MAGIC


def test_extract_stream1_raw_file_returns_none(tmp_path):
    raw_file = tmp_path / "f_000003"
    raw_file.write_bytes(PNG_MAGIC)

    result = extract_stream1(raw_file)
    assert result is None


def test_extract_stream1_truncated_file(tmp_path):
    truncated = tmp_path / "f_000004"
    # Only write part of what would be a valid header — too short for any entry
    truncated.write_bytes(b"\x00" * 10)

    result = extract_stream1(truncated)
    assert result is None


def test_extract_stream1_zero_size_stream(tmp_path):
    url = "https://example.com/empty"
    entry_data = make_entry(url, b"")
    entry_file = tmp_path / "f_000005"
    entry_file.write_bytes(entry_data)

    result = extract_stream1(entry_file)
    assert result == b""


# ---------------------------------------------------------------------------
# Verified magic constant
# ---------------------------------------------------------------------------


def test_header_magic_matches_chromium_source():
    """
    SIMPLE_CACHE_HEADER_MAGIC must equal 0xF27BC9AC443AAB97 as defined in
    Chromium net/disk_cache/simple/simple_entry_format.h
    (kSimpleEntryMagicNumber).
    """
    assert HEADER_MAGIC == 0xF27BC9AC443AAB97, (
        f"Wrong header magic: got 0x{HEADER_MAGIC:016X}, "
        "expected 0xF27BC9AC443AAB97 (Chromium kSimpleEntryMagicNumber)"
    )


def test_eof_magic_matches_chromium_source():
    """
    SIMPLE_CACHE_EOF_MAGIC must equal 0xF4FA6F7EFAF3F4F9 as defined in
    Chromium net/disk_cache/simple/simple_entry_format.h
    (kSimpleEntryEofMagicNumber).
    """
    assert EOF_MAGIC == 0xF4FA6F7EFAF3F4F9, (
        f"Wrong EOF magic: got 0x{EOF_MAGIC:016X}, "
        "expected 0xF4FA6F7EFAF3F4F9 (Chromium kSimpleEntryEofMagicNumber)"
    )


# ---------------------------------------------------------------------------
# Synthetic f_XXXXXX file with known PNG payload — exact byte verification
# ---------------------------------------------------------------------------


def _make_real_png(width: int = 4, height: int = 4) -> bytes:
    """
    Generate a minimal but structurally valid PNG (not just magic bytes).
    Uses a single red pixel row repeated *height* times with RGB colour mode.
    The returned bytes pass a structural check: PNG signature + IHDR + IDAT + IEND.
    """

    def _chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        payload = tag + data
        crc = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        return length + payload + crc

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    raw_rows = b"".join(b"\x00" + b"\xFF\x00\x00" * width for _ in range(height))
    idat = _chunk(b"IDAT", zlib.compress(raw_rows))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def test_synthetic_f_file_png_exact_match(tmp_path):
    """
    Build a synthetic f_XXXXXX Simple Cache entry with a known PNG embedded as
    stream 1, write it to a temp file, run extract_stream1, and assert the
    result equals the original PNG bytes exactly (no header corruption, no
    off-by-one, no extra trailing bytes).
    """
    original_png = _make_real_png()
    assert original_png[:8] == b"\x89PNG\r\n\x1a\n", "Test PNG must start with PNG signature"

    http_headers = b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 999\r\n\r\n"
    url = "https://cdn.discordapp.com/attachments/111/222/avatar.png"
    entry_bytes = make_entry(url, original_png, headers=http_headers)

    cache_file = tmp_path / "f_ab12cd"
    cache_file.write_bytes(entry_bytes)

    extracted = extract_stream1(cache_file)

    assert extracted is not None, "extract_stream1 returned None for a valid synthetic entry"
    assert extracted == original_png, (
        f"Extracted bytes do not match original PNG exactly. "
        f"Expected {len(original_png)} bytes starting with {original_png[:8].hex()!r}, "
        f"got {len(extracted) if extracted else 0} bytes "
        f"starting with {(extracted[:8].hex() if extracted else 'N/A')!r}"
    )
    assert extracted[:8] == b"\x89PNG\r\n\x1a\n", (
        "Extracted stream1 does not start with PNG signature — "
        "Simple Cache envelope was not stripped correctly"
    )


def test_synthetic_f_file_no_header_bleed(tmp_path):
    """
    Verify that no bytes from the Simple Cache header, key, HTTP response
    headers, or EOF records leak into the extracted stream-1 payload.
    """
    # Use a distinctive sentinel body so any contamination is detectable.
    SENTINEL_START = b"\x89PNG\r\n\x1a\n"
    SENTINEL_BODY = b"\xAA\xBB\xCC\xDD" * 64  # 256 bytes, distinctive pattern
    body = SENTINEL_START + SENTINEL_BODY

    url = "https://example.com/sentinel.png"
    http_headers = b"HTTP/1.1 200 OK\r\n\r\n"
    entry_bytes = make_entry(url, body, headers=http_headers)

    cache_file = tmp_path / "f_sentinel"
    cache_file.write_bytes(entry_bytes)

    extracted = extract_stream1(cache_file)

    assert extracted is not None
    assert len(extracted) == len(body), (
        f"Extracted length {len(extracted)} != expected body length {len(body)}"
    )
    assert extracted == body, "Extracted bytes contain bleed from cache envelope"
    # Confirm none of the URL key bytes appear at the start of extracted data
    key_bytes = url.encode("utf-8")
    assert not extracted.startswith(key_bytes[:4]), (
        "Extracted stream1 appears to start with URL key data (off-by-one in key skip)"
    )


def test_synthetic_f_file_large_body(tmp_path):
    """
    Verify correct extraction when stream-1 body is large (>64KB).
    This exercises the offset arithmetic for non-trivial stream sizes.
    """
    large_body = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 512  # ~128KB
    url = "https://cdn.example.com/large_image.png"
    entry_bytes = make_entry(url, large_body)

    cache_file = tmp_path / "f_largebod"
    cache_file.write_bytes(entry_bytes)

    extracted = extract_stream1(cache_file)

    assert extracted is not None
    assert len(extracted) == len(large_body)
    assert extracted == large_body


def test_synthetic_f_file_scanner_identifies_wrapped_png(tmp_path):
    """
    The scanner's identify_file_type must return 'image/png' for a Simple Cache
    entry wrapping a PNG, not 'application/octet-stream'.  This is the end-to-end
    scanner integration check for wrapped entries.
    """
    from cache_crow.scanner import identify_file_type

    original_png = _make_real_png()
    url = "https://cdn.discordapp.com/avatars/123/abc.png"
    entry_bytes = make_entry(url, original_png)

    cache_file = tmp_path / "f_scanner01"
    cache_file.write_bytes(entry_bytes)

    mime = identify_file_type(cache_file)
    assert mime == "image/png", (
        f"Scanner classified wrapped PNG entry as {mime!r} instead of 'image/png'. "
        "The scanner must unwrap Simple Cache entries before classifying."
    )


# ---------------------------------------------------------------------------
# Real Discord cache files (skipped when cache directory absent)
# ---------------------------------------------------------------------------

DISCORD_CACHE_DIR = Path.home() / ".config" / "discord" / "Cache" / "Cache_Data"
_cache_files = sorted(DISCORD_CACHE_DIR.glob("f_??????")) if DISCORD_CACHE_DIR.exists() else []
skip_no_discord_cache = pytest.mark.skipif(
    not _cache_files,
    reason="No Discord f_XXXXXX cache files found at ~/.config/discord/Cache/Cache_Data/",
)


@skip_no_discord_cache
def test_real_discord_cache_files_parse_without_crash():
    """
    extract_stream1 must not raise an exception on any real Discord cache file.
    It may return None (for raw/non-wrapped files) or bytes (for wrapped entries).
    """
    for cache_file in _cache_files:
        result = extract_stream1(cache_file)
        # Accepting None (not a Simple Cache entry) or bytes (valid extraction)
        assert result is None or isinstance(result, bytes), (
            f"{cache_file.name}: extract_stream1 returned unexpected type {type(result)}"
        )


@skip_no_discord_cache
def test_real_discord_cache_files_extracted_bytes_valid_if_present():
    """
    For any real Discord cache entry that IS a Simple Cache entry, the extracted
    stream-1 bytes must begin with a known media magic signature.
    Any file returning bytes from extract_stream1 must look like real media.
    """
    from cache_crow.scanner import _classify_bytes

    wrapped_count = 0
    for cache_file in _cache_files:
        result = extract_stream1(cache_file)
        if result is None:
            continue  # raw file, not wrapped — skip
        wrapped_count += 1
        mime = _classify_bytes(result[:16])
        assert mime != "application/octet-stream" or len(result) == 0, (
            f"{cache_file.name}: extracted {len(result)} bytes from Simple Cache entry "
            f"but bytes have no recognised media magic (first 8: {result[:8].hex()})"
        )
