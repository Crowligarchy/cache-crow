"""
Config file support for cache-crow.

Reads ~/.config/cache-crow/config.toml on startup.
Uses tomllib (stdlib 3.11+) with tomli fallback for older Python.

Supported keys:
  dump_dir      = "/path/to/dump"       # permanent archive directory
  default_app   = "discord"             # default --app value
  min_size      = 1024                  # default --min-size in bytes
  pictures_dir  = "/path/to/Pictures"  # base for dump_dir auto-detection
  db_path       = "/path/to/state.db"  # SQLite DB path override
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# tomllib is stdlib in 3.11+; fall back to tomli for older Pythons
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

try:
    if sys.version_info >= (3, 11):
        import tomllib as _tomllib_write  # noqa: F401 — used only to confirm stdlib presence
    # tomli_w for writing; gracefully absent
    import tomli_w as _tomli_w  # type: ignore
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

CONFIG_DIR = Path.home() / ".config" / "cache-crow"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# Keys that are valid in the config file
VALID_KEYS = {"dump_dir", "default_app", "min_size", "pictures_dir", "db_path"}

# Types for each key (used in set/show validation)
KEY_TYPES: dict[str, type] = {
    "dump_dir": str,
    "default_app": str,
    "min_size": int,
    "pictures_dir": str,
    "db_path": str,
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "default_app": "discord",
    "min_size": 1024,
}


class Config:
    """
    Loaded configuration. Values come from the TOML file; CLI flags override them.
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        merged = dict(_DEFAULT_CONFIG)
        if data:
            merged.update(data)
        self._data: dict[str, Any] = merged

    # ------------------------------------------------------------------ #
    # Accessors                                                            #
    # ------------------------------------------------------------------ #

    @property
    def dump_dir(self) -> Path | None:
        v = self._data.get("dump_dir")
        return Path(v).expanduser() if v else None

    @property
    def default_app(self) -> str:
        return str(self._data.get("default_app", "discord"))

    @property
    def min_size(self) -> int:
        return int(self._data.get("min_size", 1024))

    @property
    def pictures_dir(self) -> Path | None:
        v = self._data.get("pictures_dir")
        return Path(v).expanduser() if v else None

    @property
    def db_path(self) -> Path | None:
        v = self._data.get("db_path")
        return Path(v).expanduser() if v else None

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Config({self._data!r})"


def load_config(path: Path | None = None) -> Config:
    """
    Load configuration from disk. Returns a Config with defaults if the file
    does not exist or cannot be parsed.

    Parameters
    ----------
    path:
        Override the config file path (useful in tests).
    """
    config_path = path or CONFIG_FILE

    if not config_path.exists():
        return Config()

    if tomllib is None:
        # tomli not installed and Python < 3.11 — return defaults
        return Config()

    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return Config()

    # Strip unknown keys silently
    filtered = {k: v for k, v in data.items() if k in VALID_KEYS}
    return Config(filtered)


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    """
    Write a config dict to the TOML file. Raises RuntimeError if tomli_w is
    unavailable (Python < 3.11 without the optional dep).

    For Python 3.11+ we write the file manually since tomllib is read-only;
    we use tomli_w when available, otherwise fall back to a simple key = value
    writer that handles the types we care about.
    """
    config_path = path or CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if _HAS_TOMLI_W:
        with config_path.open("wb") as fh:
            _tomli_w.dump(data, fh)
        return

    # Minimal hand-rolled TOML writer for string/int values
    lines: list[str] = []
    for key, value in sorted(data.items()):
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        elif isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        else:
            # Skip unsupported types
            continue
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_setting(key: str, path: Path | None = None) -> Any:
    """Return a single config value by key."""
    cfg = load_config(path)
    return cfg.get(key)


def set_setting(key: str, value: str, path: Path | None = None) -> None:
    """
    Persist a single config value. The raw string `value` is coerced to the
    expected type for that key.

    Raises ValueError for unknown keys or bad values.
    """
    if key not in VALID_KEYS:
        raise ValueError(f"Unknown config key: {key!r}. Valid keys: {sorted(VALID_KEYS)}")

    expected_type = KEY_TYPES[key]
    try:
        if expected_type is int:
            coerced: Any = int(value)
        else:
            coerced = value
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid value for {key!r}: {value!r} — expected {expected_type.__name__}") from exc

    config_path = path or CONFIG_FILE
    existing: dict[str, Any] = {}

    if config_path.exists() and tomllib is not None:
        try:
            with config_path.open("rb") as fh:
                existing = tomllib.load(fh)
        except Exception:
            existing = {}

    existing[key] = coerced
    save_config(existing, config_path)


def default_dump_dir() -> Path:
    """
    Return the default dump directory.

    Prefers ~/Pictures/cache-crow/ when ~/Pictures exists (Desktop Linux /
    macOS / Windows). Falls back to ~/cache-crow-dump/ on headless systems.
    """
    pictures = Path.home() / "Pictures"
    if pictures.exists() and pictures.is_dir():
        return pictures / "cache-crow"
    return Path.home() / "cache-crow-dump"


def default_db_path() -> Path:
    """Return the default SQLite DB path."""
    return Path.home() / ".cache" / "cache-crow" / "state.db"
