import time as _time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CacheMetadata:
    url: str | None = None
    size: int | None = None
    content_type: str | None = None

    @property
    def guild_id(self) -> str | None:
        """Extract guild ID from Discord CDN URL."""
        if not self.url:
            return None
        # https://cdn.discordapp.com/attachments/{guild_id}/{channel_id}/{filename}
        try:
            parts = self.url.split("/attachments/")
            if len(parts) < 2:
                return None
            segments = parts[1].split("/")
            return segments[0] if segments else None
        except Exception:
            return None

    @property
    def channel_id(self) -> str | None:
        """Extract channel ID from Discord CDN URL."""
        if not self.url:
            return None
        try:
            parts = self.url.split("/attachments/")
            if len(parts) < 2:
                return None
            segments = parts[1].split("/")
            return segments[1] if len(segments) > 1 else None
        except Exception:
            return None

    @property
    def cdn_filename(self) -> str | None:
        """Extract original filename from Discord CDN URL."""
        if not self.url:
            return None
        try:
            parts = self.url.split("/attachments/")
            if len(parts) < 2:
                return None
            segments = parts[1].split("/")
            # Filename may have query params
            name = segments[2] if len(segments) > 2 else None
            if name:
                return name.split("?")[0]
            return None
        except Exception:
            return None


def relative_time(ts: float) -> str:
    """Return a human-readable relative time string for a Unix timestamp.

    Examples: "just now", "5 minutes ago", "2 hours ago", "3 days ago".
    """
    now = _time.time()
    diff = now - ts
    if diff < 0:
        diff = 0

    if diff < 60:
        return "just now"
    if diff < 3600:
        minutes = int(diff // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if diff < 86400:
        hours = int(diff // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if diff < 86400 * 7:
        days = int(diff // 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    if diff < 86400 * 30:
        weeks = int(diff // (86400 * 7))
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    if diff < 86400 * 365:
        months = int(diff // (86400 * 30))
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = int(diff // (86400 * 365))
    return f"{years} year{'s' if years != 1 else ''} ago"


@dataclass
class CacheEntry:
    path: Path
    size: int
    mime_type: str
    modified: float
    mtime: float = 0.0
    ctime: float = 0.0
    metadata: CacheMetadata | None = field(default=None, compare=False)
    app_source: str | None = field(default=None, compare=False)
