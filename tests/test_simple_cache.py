"""Tests for Chrome Simple Cache entry file parser."""

import struct
import tempfile
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
