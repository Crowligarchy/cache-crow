from pathlib import Path
from unittest.mock import patch

import pytest

from cache_crow.scanner import find_cache_dirs, identify_file_type, scan_cache
from cache_crow.models import CacheEntry


PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPEG_MAGIC = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100
GIF_MAGIC = b"GIF89a" + b"\x00" * 100
WEBP_MAGIC = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
MP4_MAGIC = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 100
WEBM_MAGIC = b"\x1A\x45\xDF\xA3" + b"\x00" * 100
UNKNOWN_MAGIC = b"\x00\x01\x02\x03" + b"\x00" * 100


def write_file(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_identify_png(tmp_path):
    p = write_file(tmp_path, "file1", PNG_MAGIC)
    assert identify_file_type(p) == "image/png"


def test_identify_jpeg(tmp_path):
    p = write_file(tmp_path, "file2", JPEG_MAGIC)
    assert identify_file_type(p) == "image/jpeg"


def test_identify_gif(tmp_path):
    p = write_file(tmp_path, "file3", GIF_MAGIC)
    assert identify_file_type(p) == "image/gif"


def test_identify_webp(tmp_path):
    p = write_file(tmp_path, "file4", WEBP_MAGIC)
    assert identify_file_type(p) == "image/webp"


def test_identify_mp4(tmp_path):
    p = write_file(tmp_path, "file5", MP4_MAGIC)
    assert identify_file_type(p) == "video/mp4"


def test_identify_webm(tmp_path):
    p = write_file(tmp_path, "file6", WEBM_MAGIC)
    assert identify_file_type(p) == "video/webm"


def test_identify_unknown(tmp_path):
    p = write_file(tmp_path, "file7", UNKNOWN_MAGIC)
    assert identify_file_type(p) == "application/octet-stream"


def test_identify_too_short(tmp_path):
    p = write_file(tmp_path, "file8", b"\x89P")
    assert identify_file_type(p) == "application/octet-stream"


def test_scan_cache_returns_entries(tmp_path):
    write_file(tmp_path, "a", PNG_MAGIC)
    write_file(tmp_path, "b", JPEG_MAGIC)
    write_file(tmp_path, "c", UNKNOWN_MAGIC)

    entries = scan_cache(tmp_path)

    assert len(entries) == 3
    assert all(isinstance(e, CacheEntry) for e in entries)

    mimes = {e.mime_type for e in entries}
    assert "image/png" in mimes
    assert "image/jpeg" in mimes
    assert "application/octet-stream" in mimes


def test_scan_cache_skips_directories(tmp_path):
    write_file(tmp_path, "img", PNG_MAGIC)
    (tmp_path / "subdir").mkdir()

    entries = scan_cache(tmp_path)
    assert len(entries) == 1


def test_scan_cache_entry_fields(tmp_path):
    p = write_file(tmp_path, "testfile", PNG_MAGIC)
    entries = scan_cache(tmp_path)

    assert len(entries) == 1
    e = entries[0]
    assert e.path == p
    assert e.size == len(PNG_MAGIC)
    assert e.mime_type == "image/png"
    assert isinstance(e.modified, float)


def test_find_cache_dirs_returns_existing(tmp_path):
    fake_cache = tmp_path / "discord" / "Cache" / "Cache_Data"
    fake_cache.mkdir(parents=True)

    fake_paths = [fake_cache, tmp_path / "nonexistent" / "Cache" / "Cache_Data"]

    with patch("cache_crow.scanner.CACHE_PATHS", {"discord": fake_paths}):
        result = find_cache_dirs("discord")

    assert result == [fake_cache]


def test_find_cache_dirs_unknown_app():
    result = find_cache_dirs("unknown_app_xyz")
    assert result == []


def test_find_cache_dirs_none_exist(tmp_path):
    fake_paths = [tmp_path / "nonexistent1", tmp_path / "nonexistent2"]

    with patch("cache_crow.scanner.CACHE_PATHS", {"discord": fake_paths}):
        result = find_cache_dirs("discord")

    assert result == []


# ---------------------------------------------------------------------------
# Task 1 — Enhanced file metadata: mtime, ctime, relative_time
# ---------------------------------------------------------------------------

def test_scan_cache_entry_has_mtime_and_ctime(tmp_path):
    """CacheEntry.mtime and .ctime are populated as floats from os.stat."""
    p = write_file(tmp_path, "testfile", PNG_MAGIC)
    entries = scan_cache(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert isinstance(e.mtime, float)
    assert isinstance(e.ctime, float)
    assert e.mtime > 0
    assert e.ctime > 0
    # mtime should match os.stat().st_mtime
    assert e.mtime == pytest.approx(p.stat().st_mtime)
    assert e.ctime == pytest.approx(p.stat().st_ctime)


def test_relative_time_just_now():
    """relative_time returns 'just now' for timestamps within the last minute."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts) == "just now"
    assert relative_time(ts - 30) == "just now"
    assert relative_time(ts - 59) == "just now"


def test_relative_time_minutes():
    """relative_time returns 'N minute(s) ago' for 1–59 minutes."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts - 60) == "1 minute ago"
    assert relative_time(ts - 300) == "5 minutes ago"
    assert relative_time(ts - 3540) == "59 minutes ago"


def test_relative_time_hours():
    """relative_time returns 'N hour(s) ago' for 1–23 hours."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts - 3600) == "1 hour ago"
    assert relative_time(ts - 7200) == "2 hours ago"
    assert relative_time(ts - 82800) == "23 hours ago"


def test_relative_time_days():
    """relative_time returns 'N day(s) ago' for 1–6 days."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts - 86400) == "1 day ago"
    assert relative_time(ts - 3 * 86400) == "3 days ago"
    assert relative_time(ts - 6 * 86400) == "6 days ago"


def test_relative_time_weeks():
    """relative_time returns 'N week(s) ago' for 1–4 weeks."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts - 7 * 86400) == "1 week ago"
    assert relative_time(ts - 14 * 86400) == "2 weeks ago"


def test_relative_time_months():
    """relative_time returns 'N month(s) ago' for 1–11 months."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts - 65 * 86400) == "2 months ago"


def test_relative_time_years():
    """relative_time returns 'N year(s) ago' for >= 1 year."""
    import time as _t
    from cache_crow.models import relative_time
    ts = _t.time()
    assert relative_time(ts - 400 * 86400) == "1 year ago"
    assert relative_time(ts - 800 * 86400) == "2 years ago"


# ---------------------------------------------------------------------------
# Task 2 — Multi-app support: new app names in CACHE_PATHS
# ---------------------------------------------------------------------------

def test_all_apps_present_in_cache_paths():
    """All required apps are registered in CACHE_PATHS."""
    from cache_crow.scanner import CACHE_PATHS
    required = {
        "discord", "discord-canary", "discord-ptb",
        "chrome", "chromium", "brave", "edge", "slack",
    }
    assert required.issubset(set(CACHE_PATHS.keys())), (
        f"Missing apps: {required - set(CACHE_PATHS.keys())}"
    )


def test_find_cache_dirs_all_mode(tmp_path):
    """find_cache_dirs('all') returns directories from every app."""
    discord_dir = tmp_path / "discord_cache"
    chrome_dir = tmp_path / "chrome_cache"
    discord_dir.mkdir()
    chrome_dir.mkdir()

    fake_paths = {
        "discord": [discord_dir],
        "discord-canary": [tmp_path / "nonexistent"],
        "chrome": [chrome_dir],
    }

    with patch("cache_crow.scanner.CACHE_PATHS", fake_paths):
        result = find_cache_dirs("all")

    assert discord_dir in result
    assert chrome_dir in result
    assert len(result) == 2  # nonexistent excluded


def test_find_cache_dirs_all_deduplicates(tmp_path):
    """find_cache_dirs('all') deduplicates shared paths across apps."""
    shared_dir = tmp_path / "shared_cache"
    shared_dir.mkdir()

    fake_paths = {
        "discord": [shared_dir],
        "chrome": [shared_dir],  # same path
    }

    with patch("cache_crow.scanner.CACHE_PATHS", fake_paths):
        result = find_cache_dirs("all")

    assert result.count(shared_dir) == 1


def test_discord_linux_cache_path():
    """Discord cache path on Linux points to ~/.config/discord/Cache/Cache_Data."""
    home = Path.home()
    with patch("platform.system", return_value="Linux"):
        from cache_crow import scanner as sc
        import importlib
        paths = sc._get_cache_paths()
    assert any(
        "discord" in str(p) and "Cache_Data" in str(p)
        for p in paths.get("discord", [])
    )


def test_discord_canary_linux_cache_path():
    """Discord Canary cache path on Linux points to discordcanary."""
    with patch("platform.system", return_value="Linux"):
        from cache_crow import scanner as sc
        paths = sc._get_cache_paths()
    assert any(
        "discordcanary" in str(p)
        for p in paths.get("discord-canary", [])
    )


def test_discord_ptb_linux_cache_path():
    """Discord PTB cache path on Linux points to discordptb."""
    with patch("platform.system", return_value="Linux"):
        from cache_crow import scanner as sc
        paths = sc._get_cache_paths()
    assert any(
        "discordptb" in str(p)
        for p in paths.get("discord-ptb", [])
    )


def test_chrome_linux_cache_path():
    """Chrome cache path on Linux points to google-chrome."""
    with patch("platform.system", return_value="Linux"):
        from cache_crow import scanner as sc
        paths = sc._get_cache_paths()
    assert any(
        "google-chrome" in str(p)
        for p in paths.get("chrome", [])
    )


def test_brave_linux_cache_path():
    """Brave cache path on Linux points to BraveSoftware."""
    with patch("platform.system", return_value="Linux"):
        from cache_crow import scanner as sc
        paths = sc._get_cache_paths()
    assert any(
        "BraveSoftware" in str(p)
        for p in paths.get("brave", [])
    )


def test_discord_macos_cache_path():
    """Discord cache path on macOS points to Application Support/discord."""
    with patch("platform.system", return_value="Darwin"):
        from cache_crow import scanner as sc
        paths = sc._get_cache_paths()
    assert any(
        "discord" in str(p) and "Application Support" in str(p)
        for p in paths.get("discord", [])
    )


def test_discord_windows_cache_path():
    """Discord cache path on Windows uses APPDATA or LOCALAPPDATA."""
    import os
    fake_env = {"APPDATA": "C:\\Users\\test\\AppData\\Roaming",
                "LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local"}
    with patch("platform.system", return_value="Windows"), \
         patch.dict("os.environ", fake_env, clear=False):
        from cache_crow import scanner as sc
        paths = sc._get_cache_paths()
    discord_paths = [str(p) for p in paths.get("discord", [])]
    assert any("discord" in p.lower() for p in discord_paths)
