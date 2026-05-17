"""
Chrome Simple Cache entry file parser.

Chrome's Simple Cache stores each cache entry as a single binary file named
f_XXXXXX. The file contains two streams: stream 1 (response body, i.e. the
actual media bytes) and stream 0 (HTTP response headers). Both streams are
described by EOF records that live in the last 48 bytes of the file.

File layout:
  [SimpleFileHeader 24B][Key key_len B][Stream1 body bytes][SimpleFileEOF1 24B][Stream0 header bytes][SimpleFileEOF0 24B]

The last 48 bytes are always the two EOF records:
  bytes[-48:-24] = EOF1  (describes stream 1 / response body)
  bytes[-24:]    = EOF0  (describes stream 0 / HTTP headers)
"""

import struct
from pathlib import Path

SIMPLE_CACHE_HEADER_MAGIC: int = 0xF27BC9AC443AAB97
SIMPLE_CACHE_EOF_MAGIC: int = 0xF4FA6F7EFAF3F4F9
HEADER_SIZE: int = 24
EOF_SIZE: int = 24

# Struct formats (little-endian):
#   SimpleFileHeader: uint64 magic, uint32 version, uint32 key_length, uint32 key_hash, uint32 padding
_HEADER_FMT = "<QIIII"
#   SimpleFileEOF:    uint64 magic, uint32 flags, uint32 data_crc32, int32 stream_size, int32 padding
_EOF_FMT = "<QIIii"


def parse_header(data: bytes) -> tuple[int, int] | None:
    """
    Parse the 24-byte SimpleFileHeader at the start of a Chrome Simple Cache entry.

    Returns (key_length, version) on success, or None if the data is too short
    or the magic number does not match.
    """
    if len(data) < HEADER_SIZE:
        return None
    magic, version, key_length, _key_hash, _padding = struct.unpack_from(_HEADER_FMT, data, 0)
    if magic != SIMPLE_CACHE_HEADER_MAGIC:
        return None
    return key_length, version


def parse_eof_record(data: bytes) -> tuple[int, int] | None:
    """
    Parse a 24-byte SimpleFileEOF record.

    Returns (stream_size, flags) on success, or None if the data is too short
    or the EOF magic number does not match.
    """
    if len(data) < EOF_SIZE:
        return None
    magic, flags, _crc32, stream_size, _padding = struct.unpack_from(_EOF_FMT, data, 0)
    if magic != SIMPLE_CACHE_EOF_MAGIC:
        return None
    return stream_size, flags


def extract_key(data: bytes) -> str | None:
    """
    Extract the URL key string from raw Simple Cache entry bytes.

    Returns the URL as a string, or None if the data is not a valid entry.
    """
    result = parse_header(data)
    if result is None:
        return None
    key_length, _version = result
    key_start = HEADER_SIZE
    key_end = key_start + key_length
    if len(data) < key_end:
        return None
    try:
        return data[key_start:key_end].decode("utf-8")
    except UnicodeDecodeError:
        return None


def extract_stream1(path: Path) -> bytes | None:
    """
    Extract stream 1 (response body / actual media bytes) from a Chrome Simple
    Cache entry file.

    File layout:
      [Header 24B][Key key_len B][Stream1][EOF1 24B][Stream0][EOF0 24B]

    EOF0 is always the last 24 bytes.  EOF1 immediately precedes stream0, so
    its position is: len(data) - EOF_SIZE - stream0_size - EOF_SIZE.

    Returns the raw media bytes on success.
    Returns None if:
      - the file cannot be read
      - the file does not start with a valid Simple Cache header (e.g. it is a
        raw media file — the caller should use the raw bytes directly)
      - the file is truncated or otherwise malformed

    Zero-length stream bodies are valid and return b"".
    """
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return None

    # Must have at least the header + two EOF records
    min_size = HEADER_SIZE + 2 * EOF_SIZE
    if len(data) < min_size:
        return None

    # Validate header and get key_length
    result = parse_header(data)
    if result is None:
        return None
    key_length, _version = result

    stream1_start = HEADER_SIZE + key_length
    # Need room for at least EOF1 + EOF0 after the key
    if stream1_start + 2 * EOF_SIZE > len(data):
        return None

    # EOF0 is always the last 24 bytes of the file
    eof0_data = data[-EOF_SIZE:]
    eof0_result = parse_eof_record(eof0_data)
    if eof0_result is None:
        return None
    stream0_size, _flags0 = eof0_result
    if stream0_size < 0:
        return None

    # EOF1 sits immediately before stream0
    eof1_offset = len(data) - EOF_SIZE - stream0_size - EOF_SIZE
    if eof1_offset < stream1_start:
        return None

    eof1_data = data[eof1_offset : eof1_offset + EOF_SIZE]
    eof1_result = parse_eof_record(eof1_data)
    if eof1_result is None:
        return None
    stream1_size, _flags1 = eof1_result
    if stream1_size < 0:
        return None

    stream1_end = stream1_start + stream1_size
    if stream1_end > len(data):
        return None

    return data[stream1_start:stream1_end]


def is_simple_cache_entry(data: bytes) -> bool:
    """
    Returns True if data starts with a valid Chrome Simple Cache header magic number.
    """
    return parse_header(data) is not None
