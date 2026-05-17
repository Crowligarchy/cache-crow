import os
import platform
import struct
from pathlib import Path
from .models import CacheEntry

# Chrome Simple Cache entry header magic (net/disk_cache/simple/simple_entry_format.h)
_SIMPLE_CACHE_HEADER_MAGIC: int = 0xF27BC9AC443AAB97
_SIMPLE_CACHE_HEADER_SIZE: int = 24
_SIMPLE_CACHE_EOF_MAGIC: int = 0xF4FA6F7EFAF3F4F9
_SIMPLE_CACHE_EOF_SIZE: int = 24


def _extract_stream1_bytes(data: bytes) -> bytes | None:
    """
    Return the raw stream-1 body from in-memory Simple Cache entry bytes,
    or None if *data* is not a valid Simple Cache entry.

    This mirrors the logic in simple_cache.extract_stream1 but operates on
    an already-loaded bytes object so the scanner does not open files twice.
    """
    min_size = _SIMPLE_CACHE_HEADER_SIZE + 2 * _SIMPLE_CACHE_EOF_SIZE
    if len(data) < min_size:
        return None

    # Validate header magic
    magic = struct.unpack_from("<Q", data, 0)[0]
    if magic != _SIMPLE_CACHE_HEADER_MAGIC:
        return None

    # key_length is the third field of the header (uint32 at offset 12)
    key_length = struct.unpack_from("<I", data, 12)[0]
    stream1_start = _SIMPLE_CACHE_HEADER_SIZE + key_length
    if stream1_start + 2 * _SIMPLE_CACHE_EOF_SIZE > len(data):
        return None

    # EOF0 is always the last 24 bytes; stream0_size tells us how big stream0 is
    eof0_magic, _flags0, _crc0, stream0_size, _pad0 = struct.unpack_from(
        "<QIIii", data, len(data) - _SIMPLE_CACHE_EOF_SIZE
    )
    if eof0_magic != _SIMPLE_CACHE_EOF_MAGIC or stream0_size < 0:
        return None

    # EOF1 sits immediately before stream0 data
    eof1_offset = len(data) - _SIMPLE_CACHE_EOF_SIZE - stream0_size - _SIMPLE_CACHE_EOF_SIZE
    if eof1_offset < stream1_start:
        return None

    eof1_magic, _flags1, _crc1, stream1_size, _pad1 = struct.unpack_from(
        "<QIIii", data, eof1_offset
    )
    if eof1_magic != _SIMPLE_CACHE_EOF_MAGIC or stream1_size < 0:
        return None

    stream1_end = stream1_start + stream1_size
    if stream1_end > len(data):
        return None

    return data[stream1_start:stream1_end]


def _get_cache_paths() -> dict[str, list[Path]]:
    system = platform.system()

    if system == "Darwin":
        app_support = Path.home() / "Library" / "Application Support"
        return {
            "discord": [
                app_support / "discord" / "Cache" / "Cache_Data",
                app_support / "discordcanary" / "Cache" / "Cache_Data",
                app_support / "discordptb" / "Cache" / "Cache_Data",
            ],
            "slack": [
                app_support / "Slack" / "Cache" / "Cache_Data",
            ],
        }

    if system == "Windows":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return {
            "discord": [
                appdata / "discord" / "Cache" / "Cache_Data",
                appdata / "discordcanary" / "Cache" / "Cache_Data",
                appdata / "discordptb" / "Cache" / "Cache_Data",
                localappdata / "discord" / "Cache" / "Cache_Data",
                localappdata / "discordcanary" / "Cache" / "Cache_Data",
                localappdata / "discordptb" / "Cache" / "Cache_Data",
            ],
            "slack": [
                appdata / "Slack" / "Cache" / "Cache_Data",
                localappdata / "Slack" / "Cache" / "Cache_Data",
            ],
        }

    # Linux (default)
    config = Path.home() / ".config"
    return {
        "discord": [
            config / "discord" / "Cache" / "Cache_Data",
            config / "discordcanary" / "Cache" / "Cache_Data",
            config / "discordptb" / "Cache" / "Cache_Data",
        ],
        "slack": [
            config / "Slack" / "Cache" / "Cache_Data",
        ],
    }


CACHE_PATHS: dict[str, list[Path]] = _get_cache_paths()

MIME_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/octet-stream": ".bin",
}


def find_cache_dirs(app: str = "discord") -> list[Path]:
    candidates = CACHE_PATHS.get(app.lower(), [])
    return [p for p in candidates if p.exists() and p.is_dir()]


def _classify_bytes(data: bytes) -> str:
    """Return a MIME type string from magic-byte inspection of raw media bytes."""
    if len(data) < 4:
        return "application/octet-stream"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"\xFF\xD8\xFF":
        return "image/jpeg"
    if data[:4] in (b"GIF8", b"GIF9"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "video/mp4"
    if data[:4] == b"\x1A\x45\xDF\xA3":
        return "video/webm"
    return "application/octet-stream"


def identify_file_type(path: Path) -> str:
    try:
        with path.open("rb") as f:
            data = f.read(8192)
    except (OSError, PermissionError):
        return "application/octet-stream"

    # If the file is a Chrome Simple Cache entry, inspect stream 1 (the response
    # body) rather than the raw file bytes, which start with a binary header and
    # would otherwise classify as 'application/octet-stream'.
    stream1 = _extract_stream1_bytes(data)
    if stream1 is not None:
        return _classify_bytes(stream1)

    return _classify_bytes(data)


def scan_cache(cache_dir: Path) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    for path in cache_dir.iterdir():
        if not path.is_file():
            continue
        stat = path.stat()
        mime = identify_file_type(path)
        entries.append(CacheEntry(
            path=path,
            size=stat.st_size,
            mime_type=mime,
            modified=stat.st_mtime,
        ))
    return entries
