"""
Tests for cache_crow.config — config file loading, saving, and defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cache_crow.config import (
    Config,
    VALID_KEYS,
    default_db_path,
    default_dump_dir,
    get_setting,
    load_config,
    save_config,
    set_setting,
)


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_config_defaults():
    """A Config with no data returns sensible defaults."""
    cfg = Config()
    assert cfg.default_app == "discord"
    assert cfg.min_size == 1024
    assert cfg.dump_dir is None
    assert cfg.pictures_dir is None
    assert cfg.db_path is None


def test_config_from_data():
    """Config picks up all supported keys from a dict."""
    cfg = Config(
        {
            "default_app": "slack",
            "min_size": 4096,
            "dump_dir": "/tmp/dump",
            "pictures_dir": "/tmp/pics",
            "db_path": "/tmp/state.db",
        }
    )
    assert cfg.default_app == "slack"
    assert cfg.min_size == 4096
    assert cfg.dump_dir == Path("/tmp/dump")
    assert cfg.pictures_dir == Path("/tmp/pics")
    assert cfg.db_path == Path("/tmp/state.db")


def test_config_as_dict():
    """as_dict returns all stored keys."""
    cfg = Config({"min_size": 2048})
    d = cfg.as_dict()
    assert "min_size" in d
    assert d["min_size"] == 2048


def test_config_get():
    """get() returns the value for a key, or a default."""
    cfg = Config({"default_app": "slack"})
    assert cfg.get("default_app") == "slack"
    assert cfg.get("nonexistent_key", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_missing_file(tmp_path):
    """load_config returns defaults when the file doesn't exist."""
    cfg = load_config(path=tmp_path / "nonexistent.toml")
    assert cfg.default_app == "discord"
    assert cfg.min_size == 1024


def test_load_config_valid_toml(tmp_path):
    """load_config parses a valid TOML file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'default_app = "slack"\nmin_size = 2048\n', encoding="utf-8"
    )
    cfg = load_config(path=config_file)
    assert cfg.default_app == "slack"
    assert cfg.min_size == 2048


def test_load_config_invalid_toml_returns_defaults(tmp_path):
    """load_config returns defaults when the TOML is malformed."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("this is not [ valid toml !!!", encoding="utf-8")
    cfg = load_config(path=config_file)
    assert cfg.default_app == "discord"


def test_load_config_strips_unknown_keys(tmp_path):
    """load_config silently ignores unknown keys."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'unknown_key = "should be ignored"\nmin_size = 512\n', encoding="utf-8"
    )
    cfg = load_config(path=config_file)
    assert "unknown_key" not in cfg.as_dict()
    assert cfg.min_size == 512


# ---------------------------------------------------------------------------
# save_config / set_setting
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    """save_config writes a file that load_config can read back."""
    config_file = tmp_path / "config.toml"
    save_config({"default_app": "slack", "min_size": 8192}, path=config_file)
    assert config_file.exists()

    cfg = load_config(path=config_file)
    assert cfg.default_app == "slack"
    assert cfg.min_size == 8192


def test_set_setting_string(tmp_path):
    """set_setting persists a string value."""
    config_file = tmp_path / "config.toml"
    set_setting("default_app", "slack", path=config_file)
    cfg = load_config(path=config_file)
    assert cfg.default_app == "slack"


def test_set_setting_int(tmp_path):
    """set_setting coerces an int value from string."""
    config_file = tmp_path / "config.toml"
    set_setting("min_size", "4096", path=config_file)
    cfg = load_config(path=config_file)
    assert cfg.min_size == 4096


def test_set_setting_unknown_key_raises(tmp_path):
    """set_setting raises ValueError for an unknown key."""
    config_file = tmp_path / "config.toml"
    with pytest.raises(ValueError, match="Unknown config key"):
        set_setting("bogus_key", "value", path=config_file)


def test_set_setting_bad_int_raises(tmp_path):
    """set_setting raises ValueError when coercion fails."""
    config_file = tmp_path / "config.toml"
    with pytest.raises(ValueError, match="Invalid value"):
        set_setting("min_size", "not-an-int", path=config_file)


def test_set_setting_preserves_existing(tmp_path):
    """set_setting does not erase other keys when updating one."""
    config_file = tmp_path / "config.toml"
    save_config({"default_app": "slack", "min_size": 1024}, path=config_file)
    set_setting("min_size", "4096", path=config_file)

    cfg = load_config(path=config_file)
    assert cfg.default_app == "slack"  # preserved
    assert cfg.min_size == 4096  # updated


def test_get_setting(tmp_path):
    """get_setting returns a single key."""
    config_file = tmp_path / "config.toml"
    save_config({"default_app": "slack"}, path=config_file)
    assert get_setting("default_app", path=config_file) == "slack"
    assert get_setting("min_size", path=config_file) == 1024  # default


# ---------------------------------------------------------------------------
# Defaults helpers
# ---------------------------------------------------------------------------


def test_default_db_path_is_under_home():
    """default_db_path returns a path under ~/.cache."""
    p = default_db_path()
    assert "cache-crow" in str(p)
    assert p.suffix == ".db"


def test_default_dump_dir_is_under_home():
    """default_dump_dir returns a path under home."""
    p = default_dump_dir()
    assert Path.home() in p.parents or p.parent == Path.home()
    assert "cache-crow" in str(p)


# ---------------------------------------------------------------------------
# valid_keys set
# ---------------------------------------------------------------------------


def test_valid_keys_contains_all_expected():
    expected = {"dump_dir", "default_app", "min_size", "pictures_dir", "db_path"}
    assert expected == VALID_KEYS
