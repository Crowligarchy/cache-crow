"""
Deduplication support for cache-crow.

Groups CacheEntry objects by SHA-256 of their actual media content.
For Chrome Simple Cache entries the wrapper is stripped before hashing
so that two cached copies of the same resource — regardless of where
they sit in the cache hierarchy — are recognised as duplicates.
"""

import hashlib
from pathlib import Path

from .models import CacheEntry
from .simple_cache import extract_stream1


def _content_hash(path: Path) -> str | None:
    """Return the SHA-256 hex digest of the *media* bytes inside path.

    If the file is a Chrome Simple Cache entry the stream-1 body (actual
    response content) is hashed rather than the raw on-disk bytes, so two
    cache files that wrap the same resource compare equal.

    Returns None if the file cannot be read.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    stream = extract_stream1(path)
    payload = stream if stream is not None else raw

    return hashlib.sha256(payload).hexdigest()


def find_duplicates(entries: list[CacheEntry]) -> dict[str, list[CacheEntry]]:
    """Group entries by content hash; return only groups with 2+ members.

    Args:
        entries: List of CacheEntry objects to examine.

    Returns:
        A dict mapping SHA-256 hex digest → list[CacheEntry].
        Only hashes with two or more entries are included.
    """
    groups: dict[str, list[CacheEntry]] = {}
    for entry in entries:
        digest = _content_hash(entry.path)
        if digest is None:
            continue
        groups.setdefault(digest, []).append(entry)

    return {h: members for h, members in groups.items() if len(members) >= 2}


def pick_keeper(group: list[CacheEntry], strategy: str) -> CacheEntry:
    """Select the single entry to *keep* from a duplicate group.

    Args:
        group: Two or more CacheEntry objects with identical content.
        strategy: One of "first", "largest", or "newest".

    Returns:
        The chosen CacheEntry.

    Raises:
        ValueError: If strategy is not recognised or group is empty.
    """
    if not group:
        raise ValueError("group must not be empty")

    if strategy == "first":
        return group[0]
    if strategy == "largest":
        return max(group, key=lambda e: e.size)
    if strategy == "newest":
        return max(group, key=lambda e: e.modified)

    raise ValueError(f"Unknown dedupe strategy: {strategy!r}")
