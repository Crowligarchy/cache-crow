"""Cache clearing logic for cache-crow.

Provides two public functions:

- ``select_for_clearing`` — filter a list of CacheEntry objects by age,
  size, and/or MIME type using AND semantics.
- ``clear_cache`` — remove selected entries from disk (or simulate removal
  when *dry_run* is True) and return a summary dict.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from .models import CacheEntry

if TYPE_CHECKING:
    pass  # kept for future type-only imports


def select_for_clearing(
    entries: list[CacheEntry],
    older_than_days: int | None = None,
    smaller_than_bytes: int | None = None,
    larger_than_bytes: int | None = None,
    mime_types: list[str] | None = None,
) -> list[CacheEntry]:
    """Return the subset of *entries* that match ALL supplied filters.

    Parameters
    ----------
    entries:
        Full list of scanned cache entries.
    older_than_days:
        Include only entries whose ``modified`` timestamp is more than this
        many days in the past.  ``None`` means no age filter.
    smaller_than_bytes:
        Include only entries whose ``size`` is strictly less than this value.
        ``None`` means no lower-size filter.
    larger_than_bytes:
        Include only entries whose ``size`` is strictly greater than this value.
        ``None`` means no upper-size filter.
    mime_types:
        Include only entries whose ``mime_type`` contains at least one of the
        supplied strings (partial / prefix match, e.g. ``"video"`` matches
        ``"video/mp4"`` and ``"video/webm"``).  ``None`` means no type filter.

    Returns
    -------
    list[CacheEntry]
        Entries satisfying every active filter.
    """
    now = time.time()
    result: list[CacheEntry] = []

    for entry in entries:
        if older_than_days is not None:
            cutoff = now - older_than_days * 86400
            if entry.modified >= cutoff:
                continue

        if smaller_than_bytes is not None:
            if entry.size >= smaller_than_bytes:
                continue

        if larger_than_bytes is not None:
            if entry.size <= larger_than_bytes:
                continue

        if mime_types is not None:
            if not any(mt in entry.mime_type for mt in mime_types):
                continue

        result.append(entry)

    return result


def clear_cache(
    cache_dir: Path,  # noqa: ARG001 — kept for API consistency / future use
    entries_to_remove: list[CacheEntry],
    dry_run: bool = True,
) -> dict:
    """Remove *entries_to_remove* from disk and return a summary.

    Parameters
    ----------
    cache_dir:
        The cache directory these entries originate from.  Accepted for API
        consistency and may be used for safety checks in future versions.
    entries_to_remove:
        Entries that should be (or would be) deleted.
    dry_run:
        When ``True`` (the default), no files are touched; the returned dict
        reflects what *would* happen.  When ``False``, each entry's path is
        unlinked.

    Returns
    -------
    dict with keys:
        ``removed``     — number of files successfully removed (0 on dry run).
        ``freed_bytes`` — total bytes freed (or that would be freed).
        ``errors``      — list of error strings encountered during deletion.
    """
    removed = 0
    freed_bytes = 0
    errors: list[str] = []

    for entry in entries_to_remove:
        if dry_run:
            freed_bytes += entry.size
            # We count *would-remove* items in freed_bytes only; removed stays 0.
        else:
            try:
                entry.path.unlink()
                removed += 1
                freed_bytes += entry.size
            except OSError as exc:
                errors.append(f"{entry.path.name}: {exc}")

    return {
        "removed": removed,
        "freed_bytes": freed_bytes,
        "errors": errors,
    }
