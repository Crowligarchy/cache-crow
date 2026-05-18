import json
import logging
import shutil
from pathlib import Path
from .scanner import scan_cache, MIME_EXTENSIONS, _classify_bytes
from .simple_cache import extract_stream1

logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/flac",
    "application/json",
}

# Map broad category names to MIME types (for --type filter)
TYPE_CATEGORIES: dict[str, set[str]] = {
    "image": {"image/png", "image/jpeg", "image/gif", "image/webp"},
    "video": {"video/mp4", "video/webm"},
    "audio": {"audio/mpeg", "audio/mp3", "audio/ogg", "audio/flac"},
    "sticker": {"application/json"},
    "all": MEDIA_TYPES,
}


def _identify_bytes(data: bytes) -> str:
    """Return a MIME type string from raw bytes using magic-byte detection.

    Delegates to the scanner's _classify_bytes so both modules stay in sync.
    """
    return _classify_bytes(data)


def _parse_sticker_json(data: bytes) -> dict | None:
    """Try to parse sticker JSON metadata from raw bytes.

    Returns a dict with 'asset_url' and optionally 'name'/'type' if the JSON
    looks like a Discord sticker descriptor; returns None otherwise.
    """
    try:
        text = data.decode("utf-8", errors="replace")
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(obj, dict):
        return None

    # Discord sticker JSON has an 'asset' field (CDN hash) or 'url' field.
    info: dict = {}
    if "asset" in obj:
        # Build CDN URL from hash
        asset_hash = obj["asset"]
        sticker_id = obj.get("id", "")
        info["asset_url"] = f"https://media.discordapp.net/stickers/{sticker_id}/{asset_hash}.png"
    elif "url" in obj:
        info["asset_url"] = obj["url"]
    elif "lottie_url" in obj:
        info["asset_url"] = obj["lottie_url"]
        info["format"] = "lottie"

    if not info:
        return None

    if "name" in obj:
        info["name"] = obj["name"]
    if "type" in obj:
        info["format_type"] = obj["type"]

    return info


def extract_media(
    cache_dir: Path,
    output_dir: Path,
    min_size: int = 1024,
    type_filter: str = "all",
) -> dict:
    """Extract media files from a Chrome Simple Cache directory.

    Args:
        cache_dir: Source cache directory to scan.
        output_dir: Destination directory for extracted files.
        min_size: Minimum file size in bytes to extract (default 1024).
        type_filter: Category filter — one of 'image', 'video', 'audio',
                     'sticker', or 'all' (default).

    Returns:
        Stats dict with keys: total_scanned, extracted, skipped, by_type,
        by_category, sticker_assets (list of parsed sticker asset info).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which MIME types to allow through
    allowed_types = TYPE_CATEGORIES.get(type_filter, MEDIA_TYPES)

    stats: dict = {
        "total_scanned": 0,
        "extracted": 0,
        "skipped": 0,
        "by_type": {},
        "by_category": {},
        "sticker_assets": [],
    }

    entries = scan_cache(cache_dir)
    stats["total_scanned"] = len(entries)

    for entry in entries:
        if entry.mime_type not in MEDIA_TYPES or entry.mime_type not in allowed_types:
            stats["skipped"] += 1
            continue
        if entry.size < min_size:
            stats["skipped"] += 1
            continue

        # Attempt to strip the Chrome Simple Cache wrapper from the file.
        # extract_stream1 returns the raw media bytes when the file is a
        # wrapped cache entry, or None when the file is already raw media.
        stream_bytes = extract_stream1(entry.path)
        if stream_bytes is not None:
            body = stream_bytes
            # Re-detect MIME from actual stream body (more accurate than scanner)
            detected_mime = _identify_bytes(body)
            if detected_mime == "application/octet-stream":
                # Fall back to scanner's classification
                detected_mime = entry.mime_type
                logger.warning(
                    "Extracted stream1 from %s has no recognised media magic "
                    "(expected %s); using scanner classification.",
                    entry.path.name,
                    entry.mime_type,
                )
        else:
            # Not a Simple Cache wrapper — read raw file bytes for re-detection
            try:
                raw = entry.path.read_bytes()
            except (OSError, PermissionError):
                stats["skipped"] += 1
                continue
            body = raw
            detected_mime = _identify_bytes(body) if body else entry.mime_type
            if detected_mime == "application/octet-stream":
                detected_mime = entry.mime_type

        # Use correct extension based on detected MIME (not scanner's guess)
        ext = MIME_EXTENSIONS.get(detected_mime, MIME_EXTENSIONS.get(entry.mime_type, ".bin"))
        dest = output_dir / (entry.path.name + ext)

        counter = 1
        while dest.exists():
            dest = output_dir / (entry.path.name + f"_{counter}" + ext)
            counter += 1

        if stream_bytes is not None:
            dest.write_bytes(body)
        else:
            shutil.copy2(entry.path, dest)

        # Determine category for stats
        category = "other"
        for cat, mimes in TYPE_CATEGORIES.items():
            if cat == "all":
                continue
            if detected_mime in mimes:
                category = cat
                break

        stats["extracted"] += 1
        stats["by_type"][detected_mime] = stats["by_type"].get(detected_mime, 0) + 1
        cat_stats = stats["by_category"].setdefault(category, {"count": 0, "bytes": 0})
        cat_stats["count"] += 1
        cat_stats["bytes"] += len(body)

        # JSON sticker: parse and record asset URL
        if detected_mime == "application/json":
            sticker_info = _parse_sticker_json(body)
            if sticker_info:
                sticker_info["cache_file"] = entry.path.name
                stats["sticker_assets"].append(sticker_info)
                logger.info(
                    "Sticker JSON extracted from %s — asset_url: %s",
                    entry.path.name,
                    sticker_info.get("asset_url"),
                )

    return stats
