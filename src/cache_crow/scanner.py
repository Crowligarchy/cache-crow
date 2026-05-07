from pathlib import Path
from .models import CacheEntry

CACHE_PATHS: dict[str, list[Path]] = {
    "discord": [
        Path.home() / ".config" / "discord" / "Cache" / "Cache_Data",
        Path.home() / ".config" / "discordcanary" / "Cache" / "Cache_Data",
        Path.home() / ".config" / "discordptb" / "Cache" / "Cache_Data",
    ],
    "slack": [
        Path.home() / ".config" / "Slack" / "Cache" / "Cache_Data",
    ],
}

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


def identify_file_type(path: Path) -> str:
    try:
        data = path.read_bytes()
    except (OSError, PermissionError):
        return "application/octet-stream"

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
