"""
LevelDB / Chrome Simple Cache metadata reader.

Chrome's Simple Cache (used by Electron/Discord) stores metadata in two ways:

1. Per-file headers: Each f_XXXXXX file begins with a Simple Cache Entry header
   that contains the original URL (key) before the response headers and body.

2. LevelDB index: The Cache_Data parent directory may contain a LevelDB database
   (CURRENT, MANIFEST-*, *.ldb files) with URL-to-entry mappings.

This module tries both approaches, falling back gracefully when data is unavailable.

Simple Cache Entry header layout (v5+):
  Offset  Size  Field
  0       8     Magic (0xF5A203C700000000 big-endian)
  8       4     Version
  12      4     Key length (bytes)
  16      4     Key hash (CRC32)
  20      4     Padding
  24      K     Key (URL string, UTF-8)
  24+K    ...   Response headers + body (stream 0 = headers, stream 1 = body)
"""

import struct
import logging
from pathlib import Path
from typing import Optional

from .models import CacheMetadata

log = logging.getLogger(__name__)

# Chrome Simple Cache magic bytes (little-endian uint64)
SIMPLE_CACHE_MAGIC = 0x00C7A203F5A26FE8
SIMPLE_CACHE_MAGIC_ALT = 0xF5A26FE8C7A20300  # older versions

# Minimum header size to attempt parsing
MIN_HEADER_SIZE = 24

# Recognized CDN domains for Discord media
DISCORD_CDN_PREFIXES = (
    "https://cdn.discordapp.com/",
    "https://media.discordapp.net/",
    "https://images-ext-",
    "https://cdn.discordapp.com/attachments/",
)


def _parse_simple_cache_entry_header(data: bytes) -> Optional[str]:
    """
    Attempt to parse a Chrome Simple Cache entry file header and extract the URL key.

    Returns the URL string if successfully parsed, else None.
    """
    if len(data) < MIN_HEADER_SIZE:
        return None

    # Check magic — Chrome Simple Cache magic is 8 bytes at offset 0.
    # The magic varies slightly by version; we check a few known values.
    # uint64 little-endian at offset 0:
    magic_raw = struct.unpack_from("<Q", data, 0)[0]

    # Also accept files where no magic is present but a valid URL appears early
    # (some Electron builds strip the header for small files).

    known_magic_values = {
        0xF5A26FE8C7A20300,
        0x00F5A26FE8C7A203,
        0xC7A203F5A26FE800,
        0xF5A203C700000000,
    }

    if magic_raw in known_magic_values:
        # Standard header: key_length at offset 8 (uint32 LE)
        if len(data) < 16:
            return None
        key_length = struct.unpack_from("<I", data, 8)[0]
        if 4 <= key_length <= 8192 and len(data) >= 24 + key_length:
            try:
                key = data[24 : 24 + key_length].decode("utf-8", errors="replace")
                if key.startswith("http"):
                    return key
            except Exception:
                pass

    # Fallback: scan the first 512 bytes for a Discord/CDN URL
    return _scan_bytes_for_url(data[:2048])


def _scan_bytes_for_url(data: bytes) -> Optional[str]:
    """Scan raw bytes for an embedded HTTP URL string."""
    try:
        text = data.decode("latin-1", errors="replace")
    except Exception:
        return None

    # Look for https:// occurrences
    search_start = 0
    while True:
        idx = text.find("https://", search_start)
        if idx == -1:
            break
        # Extract URL until first non-printable or whitespace char
        end = idx
        while end < len(text) and text[end] >= " " and text[end] != "\x7f":
            end += 1
        url = text[idx:end].strip()
        if len(url) > 12 and "." in url:
            return url
        search_start = idx + 1
        if search_start > 2048:
            break

    return None


def read_simple_cache_entry_url(cache_file: Path) -> Optional[str]:
    """
    Read the URL from a single Chrome Simple Cache entry file (f_XXXXXX).

    Returns the URL if found, else None.
    """
    try:
        # Only read the header portion — URLs are always in the first ~8KB
        with cache_file.open("rb") as fh:
            data = fh.read(8192)
        return _parse_simple_cache_entry_header(data)
    except (OSError, PermissionError) as exc:
        log.debug("Cannot read %s: %s", cache_file, exc)
        return None


def read_leveldb_index(cache_dir: Path) -> dict[str, CacheMetadata]:
    """
    Read Chrome cache metadata from LevelDB index and/or Simple Cache entry headers.

    Strategy:
      1. Look for a LevelDB database in cache_dir or its parent.
      2. If found, iterate keys to extract URL mappings.
      3. For each f_XXXXXX file, also attempt to extract the URL from the file header.
      4. Merge results — file header takes precedence (more reliable for our use case).

    Returns a dict mapping filename (e.g. "f_000001") -> CacheMetadata.
    """
    result: dict[str, CacheMetadata] = {}

    # --- Strategy 1: LevelDB index ---
    leveldb_dir = _find_leveldb(cache_dir)
    if leveldb_dir:
        ldb_entries = _read_leveldb(leveldb_dir)
        result.update(ldb_entries)
        log.debug("LevelDB: loaded %d entries from %s", len(ldb_entries), leveldb_dir)
    else:
        log.debug("No LevelDB index found in %s or parent", cache_dir)

    # --- Strategy 2: Per-file header scanning ---
    header_hits = 0
    for cache_file in cache_dir.iterdir():
        if not cache_file.is_file():
            continue
        name = cache_file.name
        if not (name.startswith("f_") or name.startswith("data_")):
            continue

        url = read_simple_cache_entry_url(cache_file)
        if url:
            existing = result.get(name)
            if existing is None:
                result[name] = CacheMetadata(url=url)
            else:
                # Fill in URL if not already set
                if not existing.url:
                    existing.url = url
            header_hits += 1

    log.debug("Header scan: found URLs in %d files", header_hits)
    return result


def _find_leveldb(cache_dir: Path) -> Optional[Path]:
    """
    Search for a LevelDB database near the cache directory.

    Chrome typically stores its LevelDB index in the parent of Cache_Data,
    or in a sibling directory called 'index' or 'Cache_Data'.
    """
    candidates = [
        cache_dir,
        cache_dir.parent,
        cache_dir.parent / "index",
        cache_dir.parent / "Cache",
    ]
    for candidate in candidates:
        if _is_leveldb_dir(candidate):
            return candidate
    return None


def _is_leveldb_dir(path: Path) -> bool:
    """Return True if path looks like a LevelDB database directory."""
    if not path.is_dir():
        return False
    current = path / "CURRENT"
    if not current.exists():
        return False
    # Must have at least one .ldb or .log file
    has_data = any(
        f.suffix in (".ldb", ".log") for f in path.iterdir() if f.is_file()
    )
    return has_data


def _read_leveldb(db_path: Path) -> dict[str, CacheMetadata]:
    """
    Read key-value pairs from a LevelDB database and extract cache URL mappings.

    Chrome cache LevelDB keys follow patterns like:
      - b"\x00" + url_bytes  -> response info
      - url bytes directly

    We decode all values looking for HTTP URLs and map them back to f_XXXXXX names
    using the CRC hash or sequential position.
    """
    entries: dict[str, CacheMetadata] = {}

    try:
        import plyvel  # type: ignore
    except ImportError:
        log.warning("plyvel not available — LevelDB index reading disabled")
        return entries

    try:
        db = plyvel.DB(str(db_path), create_if_missing=False)
    except Exception as exc:
        log.debug("Cannot open LevelDB at %s: %s", db_path, exc)
        return entries

    try:
        for raw_key, raw_value in db:
            try:
                # Try to decode the key as a URL
                key_str = raw_key.decode("utf-8", errors="replace")

                # Look for URL embedded in value (Chrome stores HTTP response headers)
                url = _extract_url_from_ldb_value(key_str, raw_value)
                filename = _extract_filename_from_ldb_value(raw_key, raw_value)

                if url and filename:
                    entries[filename] = CacheMetadata(
                        url=url,
                        content_type=_extract_content_type(raw_value),
                    )
                elif url and key_str.startswith("http"):
                    # Key is the URL itself — map to filename via hash
                    pass

            except Exception as exc:
                log.debug("Error parsing LevelDB entry: %s", exc)
                continue
    finally:
        try:
            db.close()
        except Exception:
            pass

    return entries


def _extract_url_from_ldb_value(key_str: str, value: bytes) -> Optional[str]:
    """Extract an HTTP URL from a LevelDB key or value."""
    # If the key itself is a URL
    if key_str.startswith("http://") or key_str.startswith("https://"):
        return key_str.split("\x00")[0].strip()

    # Scan value bytes for URL
    return _scan_bytes_for_url(value[:4096] if len(value) > 4096 else value)


def _extract_filename_from_ldb_value(raw_key: bytes, raw_value: bytes) -> Optional[str]:
    """
    Try to extract the f_XXXXXX filename from LevelDB key/value.

    Chrome cache LevelDB stores a CRC hash that maps to the filename.
    We look for patterns like 'f_' followed by hex digits in the encoded data.
    """
    for data in (raw_key, raw_value[:512]):
        try:
            text = data.decode("latin-1", errors="replace")
        except Exception:
            continue

        idx = text.find("f_")
        if idx != -1:
            name = text[idx : idx + 8]
            if len(name) == 8 and name[2:].isdigit():
                return name

    return None


def _extract_content_type(value: bytes) -> Optional[str]:
    """Extract Content-Type from HTTP response headers stored in LevelDB value."""
    try:
        text = value.decode("latin-1", errors="replace")
        # Look for content-type header
        for prefix in ("content-type: ", "Content-Type: "):
            idx = text.lower().find("content-type: ")
            if idx != -1:
                end = text.find("\n", idx)
                if end == -1:
                    end = idx + 64
                return text[idx + 14 : end].strip().split(";")[0]
    except Exception:
        pass
    return None


def enrich_entries_with_metadata(
    entries: list,
    cache_dir: Path,
) -> list:
    """
    Enrich a list of CacheEntry objects with metadata from LevelDB/file headers.

    Modifies entries in place and returns the list.
    """
    try:
        metadata_map = read_leveldb_index(cache_dir)
    except Exception as exc:
        log.warning("Metadata enrichment failed: %s", exc)
        return entries

    for entry in entries:
        meta = metadata_map.get(entry.path.name)
        if meta:
            entry.metadata = meta

    return entries
