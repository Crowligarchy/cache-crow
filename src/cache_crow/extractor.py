import logging
import shutil
from pathlib import Path
from .scanner import scan_cache, MIME_EXTENSIONS
from .simple_cache import extract_stream1

logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
}

# Magic bytes for each known media type (used to validate extracted bytes)
_MAGIC_MAP: list[tuple[str, bytes, int]] = [
    ("image/png",   b"\x89PNG",      0),
    ("image/jpeg",  b"\xFF\xD8\xFF", 0),
    ("image/gif",   b"GIF8",         0),
    ("image/webp",  b"WEBP",         8),
    ("video/mp4",   b"ftyp",         4),
    ("video/webm",  b"\x1A\x45\xDF\xA3", 0),
]


def _identify_bytes(data: bytes) -> str:
    """Return a MIME type string from raw bytes using magic-byte detection."""
    if len(data) < 4:
        return "application/octet-stream"
    for mime, magic, offset in _MAGIC_MAP:
        end = offset + len(magic)
        if len(data) >= end and data[offset:end] == magic:
            return mime
    return "application/octet-stream"


def extract_media(
    cache_dir: Path,
    output_dir: Path,
    min_size: int = 1024,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    stats: dict = {
        "total_scanned": 0,
        "extracted": 0,
        "skipped": 0,
        "by_type": {},
    }

    entries = scan_cache(cache_dir)
    stats["total_scanned"] = len(entries)

    for entry in entries:
        if entry.mime_type not in MEDIA_TYPES or entry.size < min_size:
            stats["skipped"] += 1
            continue

        ext = MIME_EXTENSIONS.get(entry.mime_type, ".bin")
        dest = output_dir / (entry.path.name + ext)

        counter = 1
        while dest.exists():
            dest = output_dir / (entry.path.name + f"_{counter}" + ext)
            counter += 1

        # Attempt to strip the Chrome Simple Cache wrapper from the file.
        # extract_stream1 returns the raw media bytes when the file is a
        # wrapped cache entry, or None when the file is already raw media.
        stream_bytes = extract_stream1(entry.path)
        if stream_bytes is not None:
            # Validate that the unwrapped bytes look like a known media type.
            detected = _identify_bytes(stream_bytes)
            if detected == "application/octet-stream":
                logger.warning(
                    "Extracted stream1 from %s has no recognised media magic "
                    "(expected %s); writing anyway.",
                    entry.path.name,
                    entry.mime_type,
                )
            dest.write_bytes(stream_bytes)
        else:
            # Not a Simple Cache wrapper — copy the raw file as-is.
            shutil.copy2(entry.path, dest)

        stats["extracted"] += 1
        stats["by_type"][entry.mime_type] = stats["by_type"].get(entry.mime_type, 0) + 1

    return stats
