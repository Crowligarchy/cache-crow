from dataclasses import dataclass
from pathlib import Path


@dataclass
class CacheEntry:
    path: Path
    size: int
    mime_type: str
    modified: float
