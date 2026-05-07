import shutil
from pathlib import Path
from .scanner import scan_cache, MIME_EXTENSIONS

MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
}


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

        shutil.copy2(entry.path, dest)
        stats["extracted"] += 1
        stats["by_type"][entry.mime_type] = stats["by_type"].get(entry.mime_type, 0) + 1

    return stats
