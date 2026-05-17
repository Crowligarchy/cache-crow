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


@dataclass
class CacheEntry:
    path: Path
    size: int
    mime_type: str
    modified: float
    metadata: CacheMetadata | None = field(default=None, compare=False)
