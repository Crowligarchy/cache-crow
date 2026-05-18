"""Tests for cache_crow.gallery — HTML gallery generation."""

from __future__ import annotations

import base64
import re
import time
from pathlib import Path

import pytest

from cache_crow.gallery import generate_gallery
from cache_crow.models import CacheEntry, CacheMetadata

# ---------------------------------------------------------------------------
# Minimal valid PNG (1x1 pixel, 67 bytes)
# ---------------------------------------------------------------------------
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"                  # PNG signature
    b"\x00\x00\x00\rIHDR"                  # IHDR chunk length + type
    b"\x00\x00\x00\x01"                    # width = 1
    b"\x00\x00\x00\x01"                    # height = 1
    b"\x08\x02"                            # bit depth=8, colour type=2 (RGB)
    b"\x00\x00\x00"                        # compression, filter, interlace
    b"\x90wS\xde"                          # CRC
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f" # IDAT chunk
    b"\x00\x00\x11\x00\x01"               # data
    b"\x82\x90\x05\xe8"                    # CRC
    b"\x00\x00\x00\x00IEND"               # IEND chunk
    b"\xaeB`\x82"                          # CRC
)


def _make_entry(
    tmp_path: Path,
    name: str = "testfile",
    mime: str = "image/png",
    data: bytes = _PNG_1X1,
    url: str | None = None,
) -> CacheEntry:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / name
    p.write_bytes(data)
    meta = CacheMetadata(url=url, size=len(data), content_type=mime) if url else None
    return CacheEntry(
        path=p,
        size=len(data),
        mime_type=mime,
        modified=time.time(),
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# 1. Gallery generates valid HTML (DOCTYPE, <head>, <body>, key landmarks)
# ---------------------------------------------------------------------------

def test_gallery_produces_valid_html_structure(tmp_path):
    entry = _make_entry(tmp_path / "files", "img.png")
    out = tmp_path / "gallery.html"
    generate_gallery([entry], out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in text
    assert "<html" in text
    assert "<head>" in text
    assert "<body>" in text
    assert "</html>" in text


# ---------------------------------------------------------------------------
# 2. Filter bar contains all expected group buttons
# ---------------------------------------------------------------------------

def test_filter_bar_buttons_present(tmp_path):
    entry = _make_entry(tmp_path / "files", "img.png")
    out = tmp_path / "gallery.html"
    generate_gallery([entry], out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    for group in ("all", "png", "jpeg", "gif", "webp", "video", "audio"):
        assert f'data-group="{group}"' in text, f"Missing filter button for group '{group}'"


# ---------------------------------------------------------------------------
# 3. Sort controls are present
# ---------------------------------------------------------------------------

def test_sort_controls_present(tmp_path):
    entry = _make_entry(tmp_path / "files", "img.png")
    out = tmp_path / "gallery.html"
    generate_gallery([entry], out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    assert 'id="sort-select"' in text
    assert "size-desc" in text
    assert "date-desc" in text
    assert "type" in text.lower()


# ---------------------------------------------------------------------------
# 4. Stats bar shows file count
# ---------------------------------------------------------------------------

def test_stats_bar_shows_file_count(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    entries = [_make_entry(files_dir, f"img{i}.png") for i in range(5)]
    out = tmp_path / "gallery.html"
    generate_gallery(entries, out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    # The total count appears as a strong element
    assert "<strong>5</strong>" in text


# ---------------------------------------------------------------------------
# 5. Base64 embedding encodes image bytes into the HTML
# ---------------------------------------------------------------------------

def test_base64_embedding(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    entry = _make_entry(files_dir, "photo.png", data=_PNG_1X1)
    out = tmp_path / "gallery.html"

    generate_gallery([entry], out, embed_images=True)
    text = out.read_text(encoding="utf-8")

    expected_b64 = base64.b64encode(_PNG_1X1).decode("ascii")
    assert expected_b64 in text, "base64-encoded image data not found in gallery"
    assert "data:image/png;base64," in text


# ---------------------------------------------------------------------------
# 6. Linked mode references relative path instead of data-URI
# ---------------------------------------------------------------------------

def test_linked_mode_uses_relative_path(tmp_path):
    output_dir = tmp_path / "recovered"
    output_dir.mkdir()
    entry = _make_entry(output_dir, "recovered_img.png")
    gallery_path = tmp_path / "gallery.html"

    generate_gallery([entry], gallery_path, embed_images=False, output_dir=output_dir)
    text = gallery_path.read_text(encoding="utf-8")

    # Should NOT embed base64
    assert "data:image/png;base64," not in text
    # Should contain a relative path to the file
    assert "recovered/recovered_img.png" in text or "recovered_img.png" in text


# ---------------------------------------------------------------------------
# 7. Empty cache shows "no media found" message
# ---------------------------------------------------------------------------

def test_empty_entries_shows_empty_state(tmp_path):
    out = tmp_path / "gallery.html"
    generate_gallery([], out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    assert "No media found" in text or "no media found" in text.lower()
    assert "empty-state" in text


# ---------------------------------------------------------------------------
# 8. CDN URL is included and copy button present when metadata.url is set
# ---------------------------------------------------------------------------

def test_cdn_url_and_copy_button(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    cdn = "https://cdn.discordapp.com/attachments/111/222/photo.png"
    entry = _make_entry(files_dir, "photo.png", url=cdn)
    out = tmp_path / "gallery.html"

    generate_gallery([entry], out, embed_images=True)
    text = out.read_text(encoding="utf-8")

    assert "cdn.discordapp.com" in text
    assert "copy-btn" in text
    assert "copyUrl" in text


# ---------------------------------------------------------------------------
# 9. Non-image entries show placeholder (no img tag, has placeholder class)
# ---------------------------------------------------------------------------

def test_video_entry_shows_placeholder(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    # Write minimal valid bytes (content irrelevant for placeholder test)
    entry = _make_entry(files_dir, "clip.mp4", mime="video/mp4", data=b"\x00" * 64)
    out = tmp_path / "gallery.html"

    generate_gallery([entry], out, embed_images=True)
    text = out.read_text(encoding="utf-8")

    assert "video-placeholder" in text
    # No src= pointing at the mp4 in image context
    assert 'data:video/mp4;base64,' not in text


def test_audio_entry_shows_placeholder(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    entry = _make_entry(files_dir, "track.mp3", mime="audio/mpeg", data=b"\xff\xfb" + b"\x00" * 62)
    out = tmp_path / "gallery.html"

    generate_gallery([entry], out, embed_images=True)
    text = out.read_text(encoding="utf-8")

    assert "audio-placeholder" in text


# ---------------------------------------------------------------------------
# 10. Lightbox scaffold present in HTML
# ---------------------------------------------------------------------------

def test_lightbox_elements_present(tmp_path):
    entry = _make_entry(tmp_path / "files", "img.png")
    out = tmp_path / "gallery.html"
    generate_gallery([entry], out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    assert 'id="lightbox"' in text
    assert 'id="lightbox-img"' in text
    assert "openLightbox" in text
    assert "closeLightbox" in text


# ---------------------------------------------------------------------------
# 11. Output file is written to the correct path (parent dirs created)
# ---------------------------------------------------------------------------

def test_output_path_parent_created(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "gallery.html"
    generate_gallery([], nested, embed_images=True)
    assert nested.exists()


# ---------------------------------------------------------------------------
# 12. Mixed entries: MIME badge labels appear for each type
# ---------------------------------------------------------------------------

def test_mime_badge_labels_for_mixed_entries(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    entries = [
        _make_entry(files_dir, "a.png",  mime="image/png",  data=_PNG_1X1),
        _make_entry(files_dir, "b.gif",  mime="image/gif",  data=b"GIF89a" + b"\x00" * 60),
        _make_entry(files_dir, "c.mp4",  mime="video/mp4",  data=b"\x00" * 64),
        _make_entry(files_dir, "d.webp", mime="image/webp", data=b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 50),
    ]
    out = tmp_path / "gallery.html"
    generate_gallery(entries, out, embed_images=True)

    text = out.read_text(encoding="utf-8")
    assert "PNG" in text
    assert "GIF" in text
    assert "MP4" in text
    assert "WebP" in text
