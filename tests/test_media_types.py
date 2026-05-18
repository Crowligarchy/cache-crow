"""
Tests for full media type coverage: video, audio, sticker, embed thumbnails.

Uses synthetic cache entries (no real Discord installation required).
"""

import json
import struct
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cache_crow.scanner import identify_file_type, _classify_bytes, MIME_EXTENSIONS
from cache_crow.extractor import (
    extract_media,
    _parse_sticker_json,
    MEDIA_TYPES,
    TYPE_CATEGORIES,
)
from cache_crow.models import CacheEntry
from cache_crow.simple_cache import (
    SIMPLE_CACHE_EOF_MAGIC,
    SIMPLE_CACHE_HEADER_MAGIC,
    HEADER_SIZE,
    EOF_SIZE,
)


# ---------------------------------------------------------------------------
# Synthetic media payloads — valid magic bytes, not real files
# ---------------------------------------------------------------------------

# Video
MP4_BYTES = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 200
WEBM_BYTES = b"\x1A\x45\xDF\xA3" + b"\x00" * 200

# Audio
MP3_ID3_BYTES = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
MP3_SYNC_BYTES = b"\xFF\xFB\x90\x00" + b"\x00" * 200
OGG_BYTES = b"OggS\x00\x02" + b"\x00" * 200
FLAC_BYTES = b"fLaC\x00\x00\x00\x22" + b"\x00" * 200

# Sticker / JSON
STICKER_ASSET_JSON = json.dumps({
    "id": "123456789",
    "name": "pepe_smile",
    "asset": "abc123def456",
    "type": 1,
}).encode("utf-8")

STICKER_URL_JSON = json.dumps({
    "name": "fire_blob",
    "url": "https://media.discordapp.net/stickers/987/fire.png",
}).encode("utf-8")

STICKER_LOTTIE_JSON = json.dumps({
    "name": "lottie_star",
    "lottie_url": "https://discord.com/assets/lottie/star.json",
}).encode("utf-8")

PLAIN_JSON = json.dumps({"key": "value", "num": 42}).encode("utf-8")

# Images (for completeness / embed thumbnails)
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG_BYTES = b"\xFF\xD8\xFF\xE0" + b"\x00" * 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cache_entry(url: str, body: bytes, headers: bytes = b"HTTP/1.1 200 OK\r\n\r\n") -> bytes:
    """Build a synthetic Chrome Simple Cache entry file."""
    key = url.encode("utf-8")
    eof1 = struct.pack("<QIIii", SIMPLE_CACHE_EOF_MAGIC, 0, 0, len(body), 0)
    eof0 = struct.pack("<QIIii", SIMPLE_CACHE_EOF_MAGIC, 0, 0, len(headers), 0)
    header = struct.pack("<QIIII", SIMPLE_CACHE_HEADER_MAGIC, 5, len(key), 0, 0)
    return header + key + body + eof1 + headers + eof0


def write_cache_file(cache_dir: Path, name: str, data: bytes) -> Path:
    p = cache_dir / name
    p.write_bytes(data)
    return p


def make_entry_obj(path: Path, mime_type: str) -> CacheEntry:
    return CacheEntry(
        path=path,
        size=path.stat().st_size,
        mime_type=mime_type,
        modified=time.time(),
    )


# ---------------------------------------------------------------------------
# 1. Magic byte detection — _classify_bytes and identify_file_type
# ---------------------------------------------------------------------------

class TestMagicByteDetection:

    def test_classify_mp4(self):
        assert _classify_bytes(MP4_BYTES) == "video/mp4"

    def test_classify_webm(self):
        assert _classify_bytes(WEBM_BYTES) == "video/webm"

    def test_classify_mp3_id3(self):
        assert _classify_bytes(MP3_ID3_BYTES) == "audio/mpeg"

    def test_classify_mp3_sync(self):
        assert _classify_bytes(MP3_SYNC_BYTES) == "audio/mpeg"

    def test_classify_ogg(self):
        assert _classify_bytes(OGG_BYTES) == "audio/ogg"

    def test_classify_flac(self):
        assert _classify_bytes(FLAC_BYTES) == "audio/flac"

    def test_classify_json_object(self):
        data = b'{"key": "value"}'
        assert _classify_bytes(data) == "application/json"

    def test_classify_json_array(self):
        data = b'[1, 2, 3]'
        assert _classify_bytes(data) == "application/json"

    def test_classify_json_with_bom(self):
        data = b"\xef\xbb\xbf" + b'{"bom": true}'
        assert _classify_bytes(data) == "application/json"

    def test_classify_json_with_whitespace(self):
        data = b'  \n{"indented": true}'
        assert _classify_bytes(data) == "application/json"

    def test_classify_apng_same_as_png(self):
        # APNG uses same PNG magic — should be classified as image/png
        assert _classify_bytes(PNG_BYTES) == "image/png"

    def test_binary_data_not_classified_as_json(self):
        # Null bytes prevent JSON classification
        data = b"\x00{\"fake\": true}"
        assert _classify_bytes(data) != "application/json"

    def test_classify_returns_octet_stream_for_unknown(self):
        assert _classify_bytes(b"\xDE\xAD\xBE\xEF" + b"\x00" * 50) == "application/octet-stream"

    def test_identify_file_type_mp4(self, tmp_path):
        p = tmp_path / "video.mp4"
        p.write_bytes(MP4_BYTES)
        assert identify_file_type(p) == "video/mp4"

    def test_identify_file_type_webm(self, tmp_path):
        p = tmp_path / "video.webm"
        p.write_bytes(WEBM_BYTES)
        assert identify_file_type(p) == "video/webm"

    def test_identify_file_type_mp3(self, tmp_path):
        p = tmp_path / "audio.mp3"
        p.write_bytes(MP3_ID3_BYTES)
        assert identify_file_type(p) == "audio/mpeg"

    def test_identify_file_type_ogg(self, tmp_path):
        p = tmp_path / "voice.ogg"
        p.write_bytes(OGG_BYTES)
        assert identify_file_type(p) == "audio/ogg"

    def test_identify_file_type_flac(self, tmp_path):
        p = tmp_path / "audio.flac"
        p.write_bytes(FLAC_BYTES)
        assert identify_file_type(p) == "audio/flac"

    def test_identify_file_type_json(self, tmp_path):
        p = tmp_path / "sticker.json"
        p.write_bytes(STICKER_ASSET_JSON)
        assert identify_file_type(p) == "application/json"

    def test_identify_wrapped_mp4(self, tmp_path):
        """Chrome Simple Cache wrapped MP4 is correctly identified."""
        entry_data = make_cache_entry("https://cdn.discordapp.com/video.mp4", MP4_BYTES)
        p = tmp_path / "f_001000"
        p.write_bytes(entry_data)
        assert identify_file_type(p) == "video/mp4"

    def test_identify_wrapped_ogg(self, tmp_path):
        """Chrome Simple Cache wrapped OGG voice message is correctly identified."""
        entry_data = make_cache_entry("https://cdn.discordapp.com/voice.ogg", OGG_BYTES)
        p = tmp_path / "f_001001"
        p.write_bytes(entry_data)
        assert identify_file_type(p) == "audio/ogg"

    def test_identify_wrapped_json(self, tmp_path):
        """Chrome Simple Cache wrapped JSON sticker metadata is correctly identified."""
        entry_data = make_cache_entry("https://discord.com/stickers/123.json", STICKER_ASSET_JSON)
        p = tmp_path / "f_001002"
        p.write_bytes(entry_data)
        assert identify_file_type(p) == "application/json"


# ---------------------------------------------------------------------------
# 2. MIME_EXTENSIONS mapping
# ---------------------------------------------------------------------------

class TestMimeExtensions:

    def test_mp3_extension(self):
        assert MIME_EXTENSIONS.get("audio/mpeg") == ".mp3"

    def test_ogg_extension(self):
        assert MIME_EXTENSIONS.get("audio/ogg") == ".ogg"

    def test_flac_extension(self):
        assert MIME_EXTENSIONS.get("audio/flac") == ".flac"

    def test_json_extension(self):
        assert MIME_EXTENSIONS.get("application/json") == ".json"


# ---------------------------------------------------------------------------
# 3. MEDIA_TYPES and TYPE_CATEGORIES
# ---------------------------------------------------------------------------

class TestTypeCategories:

    def test_media_types_includes_audio(self):
        assert "audio/mpeg" in MEDIA_TYPES
        assert "audio/ogg" in MEDIA_TYPES
        assert "audio/flac" in MEDIA_TYPES

    def test_media_types_includes_json(self):
        assert "application/json" in MEDIA_TYPES

    def test_type_category_image(self):
        assert "image/png" in TYPE_CATEGORIES["image"]
        assert "image/jpeg" in TYPE_CATEGORIES["image"]
        assert "image/gif" in TYPE_CATEGORIES["image"]
        assert "image/webp" in TYPE_CATEGORIES["image"]

    def test_type_category_video(self):
        assert "video/mp4" in TYPE_CATEGORIES["video"]
        assert "video/webm" in TYPE_CATEGORIES["video"]

    def test_type_category_audio(self):
        assert "audio/mpeg" in TYPE_CATEGORIES["audio"]
        assert "audio/ogg" in TYPE_CATEGORIES["audio"]
        assert "audio/flac" in TYPE_CATEGORIES["audio"]

    def test_type_category_sticker(self):
        assert "application/json" in TYPE_CATEGORIES["sticker"]

    def test_type_category_all_is_superset(self):
        all_types = TYPE_CATEGORIES["all"]
        for cat, types in TYPE_CATEGORIES.items():
            if cat == "all":
                continue
            for t in types:
                assert t in all_types, f"{t} in category {cat!r} missing from 'all'"


# ---------------------------------------------------------------------------
# 4. Sticker JSON parsing
# ---------------------------------------------------------------------------

class TestStickerJsonParsing:

    def test_parse_sticker_with_asset_field(self):
        result = _parse_sticker_json(STICKER_ASSET_JSON)
        assert result is not None
        assert "asset_url" in result
        assert "123456789" in result["asset_url"]
        assert "abc123def456" in result["asset_url"]

    def test_parse_sticker_with_url_field(self):
        result = _parse_sticker_json(STICKER_URL_JSON)
        assert result is not None
        assert result["asset_url"] == "https://media.discordapp.net/stickers/987/fire.png"

    def test_parse_sticker_with_lottie_url(self):
        result = _parse_sticker_json(STICKER_LOTTIE_JSON)
        assert result is not None
        assert "lottie" in result["asset_url"]
        assert result.get("format") == "lottie"

    def test_parse_sticker_name_preserved(self):
        result = _parse_sticker_json(STICKER_URL_JSON)
        assert result is not None
        assert result.get("name") == "fire_blob"

    def test_parse_plain_json_returns_none(self):
        """Plain JSON without sticker fields should return None."""
        result = _parse_sticker_json(PLAIN_JSON)
        assert result is None

    def test_parse_invalid_json_returns_none(self):
        result = _parse_sticker_json(b"not json {{{ broken")
        assert result is None

    def test_parse_empty_bytes_returns_none(self):
        result = _parse_sticker_json(b"")
        assert result is None

    def test_parse_json_array_returns_none(self):
        result = _parse_sticker_json(b"[1, 2, 3]")
        assert result is None


# ---------------------------------------------------------------------------
# 5. extract_media — new media types extracted correctly
# ---------------------------------------------------------------------------

class TestExtractMediaNewTypes:

    def _setup(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"
        return cache_dir, out_dir

    def test_extract_mp4_from_wrapped_entry(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://cdn.discordapp.com/clip.mp4", MP4_BYTES)
        p = write_cache_file(cache_dir, "f_002001", data)
        entry = make_entry_obj(p, "video/mp4")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert len(outputs) == 1
        assert outputs[0].suffix == ".mp4"
        assert outputs[0].read_bytes()[:8] == MP4_BYTES[:8]

    def test_extract_webm_from_wrapped_entry(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://cdn.discordapp.com/clip.webm", WEBM_BYTES)
        p = write_cache_file(cache_dir, "f_002002", data)
        entry = make_entry_obj(p, "video/webm")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".webm"
        assert outputs[0].read_bytes()[:4] == b"\x1A\x45\xDF\xA3"

    def test_extract_mp3_from_wrapped_entry(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://cdn.discordapp.com/voice.mp3", MP3_ID3_BYTES)
        p = write_cache_file(cache_dir, "f_002003", data)
        entry = make_entry_obj(p, "audio/mpeg")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".mp3"
        assert outputs[0].read_bytes()[:3] == b"ID3"

    def test_extract_ogg_voice_message(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://cdn.discordapp.com/voice/msg.ogg", OGG_BYTES)
        p = write_cache_file(cache_dir, "f_002004", data)
        entry = make_entry_obj(p, "audio/ogg")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".ogg"
        assert outputs[0].read_bytes()[:4] == b"OggS"

    def test_extract_flac_audio(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://cdn.discordapp.com/track.flac", FLAC_BYTES)
        p = write_cache_file(cache_dir, "f_002005", data)
        entry = make_entry_obj(p, "audio/flac")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".flac"
        assert outputs[0].read_bytes()[:4] == b"fLaC"

    def test_extract_sticker_json_records_asset_url(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://discord.com/api/stickers/123", STICKER_URL_JSON)
        p = write_cache_file(cache_dir, "f_002006", data)
        entry = make_entry_obj(p, "application/json")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        assert len(stats["sticker_assets"]) == 1
        sa = stats["sticker_assets"][0]
        assert sa["asset_url"] == "https://media.discordapp.net/stickers/987/fire.png"
        assert sa["cache_file"] == "f_002006"

    def test_extract_sticker_json_with_asset_hash(self, tmp_path):
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://discord.com/api/stickers/123", STICKER_ASSET_JSON)
        p = write_cache_file(cache_dir, "f_002007", data)
        entry = make_entry_obj(p, "application/json")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        sa = stats["sticker_assets"][0]
        assert "123456789" in sa["asset_url"]

    def test_extract_plain_json_no_sticker_info(self, tmp_path):
        """Plain JSON is extracted but produces no sticker_assets entry."""
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://discord.com/api/something", PLAIN_JSON)
        p = write_cache_file(cache_dir, "f_002008", data)
        entry = make_entry_obj(p, "application/json")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        assert stats["sticker_assets"] == []

    def test_extract_embed_thumbnail_jpeg(self, tmp_path):
        """OpenGraph embed thumbnail (JPEG) is extracted correctly."""
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://i.imgur.com/embed_thumb.jpg", JPEG_BYTES)
        p = write_cache_file(cache_dir, "f_002009", data)
        entry = make_entry_obj(p, "image/jpeg")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".jpg"
        assert outputs[0].read_bytes()[:3] == b"\xFF\xD8\xFF"

    def test_extract_avatar_png(self, tmp_path):
        """Discord user avatar PNG is extracted correctly."""
        cache_dir, out_dir = self._setup(tmp_path)
        data = make_cache_entry("https://cdn.discordapp.com/avatars/1234/abcdef.png", PNG_BYTES)
        p = write_cache_file(cache_dir, "f_002010", data)
        entry = make_entry_obj(p, "image/png")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".png"


# ---------------------------------------------------------------------------
# 6. --type filter (TYPE_CATEGORIES filtering in extract_media)
# ---------------------------------------------------------------------------

class TestTypeFilter:

    def _entries(self, cache_dir: Path) -> list[CacheEntry]:
        """Create a mixed set of cache entries for filter tests."""
        entries = []
        for name, body, mime in [
            ("f_003001", MP4_BYTES, "video/mp4"),
            ("f_003002", OGG_BYTES, "audio/ogg"),
            ("f_003003", PNG_BYTES, "image/png"),
            ("f_003004", STICKER_URL_JSON, "application/json"),
        ]:
            p = cache_dir / name
            p.write_bytes(make_cache_entry(f"https://discord.com/{name}", body))
            entries.append(make_entry_obj(p, mime))
        return entries

    def test_filter_video_only(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"
        entries = self._entries(cache_dir)

        with patch("cache_crow.extractor.scan_cache", return_value=entries):
            stats = extract_media(cache_dir, out_dir, min_size=0, type_filter="video")

        assert stats["extracted"] == 1
        assert "video/mp4" in stats["by_type"]

    def test_filter_audio_only(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"
        entries = self._entries(cache_dir)

        with patch("cache_crow.extractor.scan_cache", return_value=entries):
            stats = extract_media(cache_dir, out_dir, min_size=0, type_filter="audio")

        assert stats["extracted"] == 1
        assert "audio/ogg" in stats["by_type"]

    def test_filter_image_only(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"
        entries = self._entries(cache_dir)

        with patch("cache_crow.extractor.scan_cache", return_value=entries):
            stats = extract_media(cache_dir, out_dir, min_size=0, type_filter="image")

        assert stats["extracted"] == 1
        assert "image/png" in stats["by_type"]

    def test_filter_sticker_only(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"
        entries = self._entries(cache_dir)

        with patch("cache_crow.extractor.scan_cache", return_value=entries):
            stats = extract_media(cache_dir, out_dir, min_size=0, type_filter="sticker")

        assert stats["extracted"] == 1
        assert "application/json" in stats["by_type"]

    def test_filter_all_extracts_everything(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"
        entries = self._entries(cache_dir)

        with patch("cache_crow.extractor.scan_cache", return_value=entries):
            stats = extract_media(cache_dir, out_dir, min_size=0, type_filter="all")

        assert stats["extracted"] == 4


# ---------------------------------------------------------------------------
# 7. Stats: by_category breakdown
# ---------------------------------------------------------------------------

class TestStatsByCategory:

    def test_by_category_populated(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"

        entries = []
        for name, body, mime in [
            ("f_004001", MP4_BYTES, "video/mp4"),
            ("f_004002", MP4_BYTES, "video/mp4"),
            ("f_004003", OGG_BYTES, "audio/ogg"),
            ("f_004004", PNG_BYTES, "image/png"),
        ]:
            p = cache_dir / name
            p.write_bytes(make_cache_entry(f"https://discord.com/{name}", body))
            entries.append(make_entry_obj(p, mime))

        with patch("cache_crow.extractor.scan_cache", return_value=entries):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        by_cat = stats["by_category"]
        assert by_cat["video"]["count"] == 2
        assert by_cat["audio"]["count"] == 1
        assert by_cat["image"]["count"] == 1

    def test_by_category_bytes_tracked(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"

        p = cache_dir / "f_004010"
        p.write_bytes(make_cache_entry("https://discord.com/x.mp4", MP4_BYTES))
        entry = make_entry_obj(p, "video/mp4")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["by_category"]["video"]["bytes"] == len(MP4_BYTES)
        assert stats["by_category"]["video"]["bytes"] > 0


# ---------------------------------------------------------------------------
# 8. Raw file (no wrapper) extraction for new types
# ---------------------------------------------------------------------------

class TestRawFileExtraction:

    def test_raw_ogg_extracted_correctly(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"

        p = cache_dir / "f_005001"
        p.write_bytes(OGG_BYTES)
        entry = make_entry_obj(p, "audio/ogg")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".ogg"

    def test_raw_flac_extracted_correctly(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        out_dir = tmp_path / "out"

        p = cache_dir / "f_005002"
        p.write_bytes(FLAC_BYTES)
        entry = make_entry_obj(p, "audio/flac")

        with patch("cache_crow.extractor.scan_cache", return_value=[entry]):
            stats = extract_media(cache_dir, out_dir, min_size=0)

        assert stats["extracted"] == 1
        outputs = list(out_dir.iterdir())
        assert outputs[0].suffix == ".flac"
