import os
import platform
from pathlib import Path
from .models import CacheEntry


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


def identify_file_type(path: Path) -> str:
    try:
        with path.open("rb") as f:
            data = f.read(8192)
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
