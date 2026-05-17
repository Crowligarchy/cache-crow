from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import struct
import logging

logger = logging.getLogger(__name__)

# Chrome Simple Cache index magic — observed values in the wild.
# The canonical value per Chromium source (simple_index_file.cc) is the one below.
INDEX_MAGIC = 0xF7CA3B1A209C7E7B

# Alternate magic seen in some Chrome/Chromium builds; accepted as valid.
INDEX_MAGIC_ALT = 0xF3D4C5B6A7E8F9C0

ACCEPTED_MAGICS = frozenset({INDEX_MAGIC, INDEX_MAGIC_ALT})

INDEX_HEADER_FMT = "<QIIQqI"   # magic(Q) ver(I) n_entries(I) cache_size(Q) reason(q) pad(I)
INDEX_HEADER_SIZE = struct.calcsize(INDEX_HEADER_FMT)  # should be 36

INDEX_ENTRY_FMT = "<QiiII"     # hash(Q) entry_size(i) trailer(i) last_used(I) last_mod(I)
INDEX_ENTRY_SIZE = struct.calcsize(INDEX_ENTRY_FMT)    # should be 24

assert INDEX_HEADER_SIZE == 36, f"Header size mismatch: {INDEX_HEADER_SIZE}"
assert INDEX_ENTRY_SIZE == 24, f"Entry size mismatch: {INDEX_ENTRY_SIZE}"


@dataclass
class IndexEntry:
    hash: int
    entry_size_blocks: int      # raw entry_size field (size in 256-byte blocks + file count)
    last_used_time: int         # raw uint32 timestamp
    last_modified_time: int     # raw uint32 timestamp


@dataclass
class CacheIndex:
    version: int
    num_entries: int
    cache_size_bytes: int
    entries: list[IndexEntry]


def parse_index(index_path: Path) -> Optional[CacheIndex]:
    """
    Parse a Chrome Simple Cache index file.

    Returns CacheIndex on success, None if the file is missing, has an
    invalid magic, or is too truncated to contain even the header.
    If num_entries exceeds the number of complete records in the file the
    parser returns however many complete entries are actually present.
    """
    try:
        data = index_path.read_bytes()
    except FileNotFoundError:
        logger.debug("Index file not found: %s", index_path)
        return None
    except OSError as exc:
        logger.warning("Cannot read index file %s: %s", index_path, exc)
        return None

    if len(data) < INDEX_HEADER_SIZE:
        logger.warning(
            "Index file too short for header (%d bytes): %s", len(data), index_path
        )
        return None

    magic, version, num_entries, cache_size, _reason, _pad = struct.unpack_from(
        INDEX_HEADER_FMT, data, 0
    )

    if magic not in ACCEPTED_MAGICS:
        logger.warning(
            "Index file has unexpected magic 0x%016X (path: %s)", magic, index_path
        )
        return None

    payload = data[INDEX_HEADER_SIZE:]
    max_entries = len(payload) // INDEX_ENTRY_SIZE

    if max_entries < num_entries:
        logger.warning(
            "Index claims %d entries but file only holds %d complete records; "
            "reading %d entries from %s",
            num_entries,
            max_entries,
            max_entries,
            index_path,
        )
        entries_to_read = max_entries
    else:
        entries_to_read = num_entries

    entries: list[IndexEntry] = []
    for i in range(entries_to_read):
        offset = i * INDEX_ENTRY_SIZE
        hash_val, entry_size, _trailer, last_used, last_mod = struct.unpack_from(
            INDEX_ENTRY_FMT, payload, offset
        )
        entries.append(
            IndexEntry(
                hash=hash_val,
                entry_size_blocks=entry_size,
                last_used_time=last_used,
                last_modified_time=last_mod,
            )
        )

    return CacheIndex(
        version=version,
        num_entries=num_entries,
        cache_size_bytes=cache_size,
        entries=entries,
    )


def read_cache_index(cache_dir: Path) -> Optional[CacheIndex]:
    """
    Locate and parse the index file inside a Chrome Simple Cache directory.

    Chrome stores the index at one of two locations relative to cache_dir:
      1. <cache_dir>/index               (common layout)
      2. <cache_dir>/index-dir/the-real-index  (alternate layout)

    Returns CacheIndex on success, None if no index file can be found or
    parsed.
    """
    candidates = [
        cache_dir / "index",
        cache_dir / "index-dir" / "the-real-index",
    ]
    for candidate in candidates:
        if candidate.exists():
            result = parse_index(candidate)
            if result is not None:
                return result
    logger.debug("No valid index found in cache directory: %s", cache_dir)
    return None
