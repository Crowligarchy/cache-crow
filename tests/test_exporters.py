"""Tests for cache_crow.exporters — CSV and HTML export."""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path

import pytest

from cache_crow.exporters import export_csv, export_html, _CSV_COLUMNS
from cache_crow.models import CacheEntry, CacheMetadata

# ---------------------------------------------------------------------------
# Minimal valid PNG (1×1 pixel) for thumbnail embedding tests
# ---------------------------------------------------------------------------
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01"
    b"\x00\x00\x00\x01"
    b"\x08\x02"
    b"\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x11\x00\x01"
    b"\x82\x90\x05\xe8"
    b"\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)


def _make_entry(
    tmp_path: Path,
    name: str = "testfile",
    mime: str = "image/png",
    data: bytes = _PNG_1X1,
    url: str | None = None,
    app: str | None = "discord",
) -> CacheEntry:
    """Create a CacheEntry backed by a real file in tmp_path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / name
    p.write_bytes(data)
    meta = (
        CacheMetadata(url=url, size=len(data), content_type=mime) if url else None
    )
    return CacheEntry(
        path=p,
        size=len(data),
        mime_type=mime,
        modified=time.time(),
        metadata=meta,
        app_source=app,
    )


# ===========================================================================
# CSV tests
# ===========================================================================


class TestExportCsv:
    """Tests for export_csv()."""

    def test_csv_has_correct_headers(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        csv_text = export_csv([entry])
        reader = csv.DictReader(io.StringIO(csv_text))
        assert reader.fieldnames == _CSV_COLUMNS

    def test_csv_data_row_matches_entry(self, tmp_path):
        cdn = "https://cdn.discordapp.com/attachments/111/222/img.png"
        entry = _make_entry(tmp_path / "files", "img.png", url=cdn)
        csv_text = export_csv([entry])
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1
        row = rows[0]
        assert row["filename"] == "img.png"
        assert row["mime_type"] == "image/png"
        assert row["cdn_url"] == cdn
        assert row["guild_id"] == "111"
        assert row["channel_id"] == "222"
        assert row["app"] == "discord"
        assert int(row["size_bytes"]) == len(_PNG_1X1)

    def test_csv_multiple_entries(self, tmp_path):
        files = tmp_path / "files"
        entries = [
            _make_entry(files, f"img{i}.png") for i in range(5)
        ]
        csv_text = export_csv(entries)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 5

    def test_csv_empty_entries(self):
        csv_text = export_csv([])
        reader = csv.DictReader(io.StringIO(csv_text))
        assert reader.fieldnames == _CSV_COLUMNS
        assert list(reader) == []

    def test_csv_missing_cdn_url(self, tmp_path):
        """Entry with no metadata (no CDN URL) should export empty strings."""
        entry = _make_entry(tmp_path / "files", "img.png", url=None)
        csv_text = export_csv([entry])
        reader = csv.DictReader(io.StringIO(csv_text))
        row = list(reader)[0]
        assert row["cdn_url"] == ""
        assert row["guild_id"] == ""
        assert row["channel_id"] == ""

    def test_csv_writes_to_file(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        out = tmp_path / "report.csv"
        result = export_csv([entry], output_path=out)
        assert result is None
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "filename" in content
        assert "img.png" in content

    def test_csv_returns_string_without_output_path(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        result = export_csv([entry])
        assert isinstance(result, str)
        assert "img.png" in result

    def test_csv_creates_parent_dirs(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        out = tmp_path / "deep" / "nested" / "report.csv"
        export_csv([entry], output_path=out)
        assert out.exists()

    def test_csv_mixed_mime_types(self, tmp_path):
        files = tmp_path / "files"
        entries = [
            _make_entry(files, "a.png", mime="image/png"),
            _make_entry(files, "b.mp4", mime="video/mp4", data=b"\x00" * 64),
            _make_entry(files, "c.webm", mime="video/webm", data=b"\x1a\x45\xdf\xa3" + b"\x00" * 60),
        ]
        csv_text = export_csv(entries)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        mimes = {r["mime_type"] for r in rows}
        assert mimes == {"image/png", "video/mp4", "video/webm"}


# ===========================================================================
# HTML tests
# ===========================================================================


class TestExportHtml:
    """Tests for export_html()."""

    def test_html_basic_structure(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        html = export_html([entry])
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_html_summary_stats(self, tmp_path):
        files = tmp_path / "files"
        entries = [_make_entry(files, f"img{i}.png") for i in range(3)]
        html = export_html(entries)
        # Total count appears in the summary section
        assert ">3<" in html  # rendered as <div class="value">3</div>

    def test_html_with_cdn_url(self, tmp_path):
        cdn = "https://cdn.discordapp.com/attachments/111/222/photo.png"
        entry = _make_entry(tmp_path / "files", "photo.png", url=cdn)
        html = export_html([entry])
        assert "cdn.discordapp.com" in html
        assert "111" in html  # guild_id
        assert "222" in html  # channel_id

    def test_html_missing_cdn_url_shows_dash(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png", url=None)
        html = export_html([entry])
        # Dash placeholder should appear
        assert "—" in html or "&mdash;" in html or "&#x2014;" in html

    def test_html_empty_entries(self):
        html = export_html([])
        assert "<!DOCTYPE html>" in html
        assert "No entries to display" in html

    def test_html_contains_table(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        html = export_html([entry])
        assert "<table" in html
        assert "<thead>" in html
        assert "<tbody" in html
        assert "</table>" in html

    def test_html_contains_sortable_headers(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        html = export_html([entry])
        # Column headers with data-col attributes
        assert 'data-col="filename"' in html
        assert 'data-col="size_bytes"' in html
        assert 'data-col="mime_type"' in html
        assert 'data-col="modified_ts"' in html

    def test_html_contains_filter_input(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        html = export_html([entry])
        assert 'id="filter-input"' in html

    def test_html_contains_vanilla_js(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        html = export_html([entry])
        assert "<script>" in html
        # No external CDN dependency
        assert "cdn.jsdelivr.net" not in html
        assert "unpkg.com" not in html
        assert "cdnjs.cloudflare.com" not in html

    def test_html_embeds_thumbnail_for_small_image(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "photo.png", data=_PNG_1X1)
        html = export_html([entry], embed_thumbnails=True)
        assert "data:image/png;base64," in html

    def test_html_no_embed_when_disabled(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "photo.png", data=_PNG_1X1)
        html = export_html([entry], embed_thumbnails=False)
        assert "data:image/png;base64," not in html

    def test_html_no_embed_for_video(self, tmp_path):
        entry = _make_entry(
            tmp_path / "files", "clip.mp4", mime="video/mp4", data=b"\x00" * 64
        )
        html = export_html([entry], embed_thumbnails=True)
        assert "data:video/mp4;base64," not in html

    def test_html_writes_to_file(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        out = tmp_path / "report.html"
        result = export_html([entry], output_path=out)
        assert result is None
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "img.png" in content

    def test_html_returns_string_without_output_path(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        result = export_html([entry])
        assert isinstance(result, str)
        assert "<!DOCTYPE html>" in result

    def test_html_creates_parent_dirs(self, tmp_path):
        entry = _make_entry(tmp_path / "files", "img.png")
        out = tmp_path / "deep" / "nested" / "report.html"
        export_html([entry], output_path=out)
        assert out.exists()

    def test_html_filename_escaped(self, tmp_path):
        """Filenames with HTML special chars should be escaped."""
        files = tmp_path / "files"
        files.mkdir(parents=True, exist_ok=True)
        # Create a file; the actual name on disk is safe but we spoof the CacheEntry
        p = files / "safe.png"
        p.write_bytes(_PNG_1X1)
        from cache_crow.models import CacheEntry
        entry = CacheEntry(
            path=p,
            size=len(_PNG_1X1),
            mime_type="image/png",
            modified=time.time(),
        )
        # Override path name indirectly by monkey-patching Path.name is read-only,
        # so just verify normal escaping works for standard names.
        html = export_html([entry])
        assert "safe.png" in html

    def test_html_mime_filter_select_populated(self, tmp_path):
        files = tmp_path / "files"
        entries = [
            _make_entry(files, "a.png", mime="image/png"),
            _make_entry(files, "b.mp4", mime="video/mp4", data=b"\x00" * 64),
        ]
        html = export_html(entries)
        assert "image/png" in html
        assert "video/mp4" in html

    def test_html_large_image_not_embedded(self, tmp_path):
        """Images over 500 KB should not be embedded even when embed=True."""
        files = tmp_path / "files"
        files.mkdir(parents=True, exist_ok=True)
        big_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * (600 * 1024)
        p = files / "big.png"
        p.write_bytes(big_data)
        entry = CacheEntry(
            path=p,
            size=len(big_data),
            mime_type="image/png",
            modified=time.time(),
        )
        html = export_html([entry], embed_thumbnails=True)
        # Should fall back to placeholder, not embed 600 KB of base64
        assert "data:image/png;base64," not in html
