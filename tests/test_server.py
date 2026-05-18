"""Tests for cache_crow.server — local gallery HTTP server."""

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from cache_crow.models import CacheEntry, CacheMetadata
from cache_crow.server import _GalleryHandler, run_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _make_entry(tmp_path: Path, name: str, content: bytes, mime: str) -> CacheEntry:
    p = tmp_path / name
    p.write_bytes(content)
    stat = p.stat()
    return CacheEntry(path=p, size=len(content), mime_type=mime, modified=stat.st_mtime)


def _make_server(entries: list[CacheEntry], cache_dirs: list[Path], port: int):
    """Construct an HTTPServer bound to *port* using _GalleryHandler."""
    from http.server import HTTPServer

    handler = type(
        "_BoundHandler",
        (_GalleryHandler,),
        {"entries": entries, "cache_dirs": cache_dirs},
    )
    return HTTPServer(("localhost", port), handler)


def _run_server_in_bg(server) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Give the server a moment to start accepting connections
    time.sleep(0.05)
    return t


def _get(url: str) -> tuple[int, bytes, str]:
    """Return (status_code, body_bytes, content_type)."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestServerServesRootHTML:
    """GET / returns the embedded single-page HTML app."""

    def test_root_returns_200(self, tmp_path):
        port = _free_port()
        entries = [_make_entry(tmp_path, "img.png", b"\x89PNG\r\n\x1a\n", "image/png")]
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, body, ct = _get(f"http://localhost:{port}/")
            assert status == 200
            assert b"cache-crow" in body
            assert b"text/html" in ct.encode()
        finally:
            server.shutdown()

    def test_root_contains_grid_element(self, tmp_path):
        port = _free_port()
        entries = []
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            _, body, _ = _get(f"http://localhost:{port}/")
            assert b'id="grid"' in body
        finally:
            server.shutdown()


class TestAPIEntries:
    """GET /api/entries returns JSON list with correct fields."""

    def test_entries_returns_json_list(self, tmp_path):
        port = _free_port()
        entries = [
            _make_entry(tmp_path, "photo.jpg", b"\xFF\xD8\xFF" + b"\x00" * 20, "image/jpeg"),
            _make_entry(tmp_path, "clip.mp4", b"\x00\x00\x00\x18ftyp" + b"\x00" * 10, "video/mp4"),
        ]
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, body, ct = _get(f"http://localhost:{port}/api/entries")
            assert status == 200
            assert "application/json" in ct
            data = json.loads(body)
            assert isinstance(data, list)
            assert len(data) == 2
        finally:
            server.shutdown()

    def test_entries_have_required_fields(self, tmp_path):
        port = _free_port()
        entries = [_make_entry(tmp_path, "img.png", b"\x89PNG\r\n\x1a\n", "image/png")]
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            _, body, _ = _get(f"http://localhost:{port}/api/entries")
            data = json.loads(body)
            record = data[0]
            for field in ("filename", "mime_type", "size", "modified", "url", "guild_id", "channel_id"):
                assert field in record, f"Missing field: {field}"
        finally:
            server.shutdown()

    def test_entries_filename_and_size_correct(self, tmp_path):
        port = _free_port()
        content = b"\x89PNG\r\n\x1a\n" + b"x" * 512
        entries = [_make_entry(tmp_path, "test_image.png", content, "image/png")]
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            _, body, _ = _get(f"http://localhost:{port}/api/entries")
            data = json.loads(body)
            assert data[0]["filename"] == "test_image.png"
            assert data[0]["size"] == len(content)
            assert data[0]["mime_type"] == "image/png"
        finally:
            server.shutdown()

    def test_entries_includes_metadata_fields_when_present(self, tmp_path):
        port = _free_port()
        meta = CacheMetadata(
            url="https://cdn.discordapp.com/attachments/111/222/photo.jpg",
            size=1234,
            content_type="image/jpeg",
        )
        content = b"\xFF\xD8\xFF" + b"\x00" * 20
        entry = _make_entry(tmp_path, "photo.jpg", content, "image/jpeg")
        entry.metadata = meta
        server = _make_server([entry], [tmp_path], port)
        _run_server_in_bg(server)
        try:
            _, body, _ = _get(f"http://localhost:{port}/api/entries")
            data = json.loads(body)
            rec = data[0]
            assert rec["url"] == meta.url
            assert rec["guild_id"] == "111"
            assert rec["channel_id"] == "222"
        finally:
            server.shutdown()

    def test_empty_cache_returns_empty_list(self, tmp_path):
        port = _free_port()
        server = _make_server([], [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, body, _ = _get(f"http://localhost:{port}/api/entries")
            assert status == 200
            data = json.loads(body)
            assert data == []
        finally:
            server.shutdown()


class TestFileEndpoint:
    """GET /file/FILENAME serves raw file bytes from cache dir."""

    def test_file_endpoint_returns_correct_bytes(self, tmp_path):
        port = _free_port()
        content = b"\x89PNG\r\n\x1a\n" + b"fake png payload"
        entries = [_make_entry(tmp_path, "image.png", content, "image/png")]
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, body, _ = _get(f"http://localhost:{port}/file/image.png")
            assert status == 200
            assert body == content
        finally:
            server.shutdown()

    def test_file_endpoint_404_for_missing_file(self, tmp_path):
        port = _free_port()
        server = _make_server([], [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, _, _ = _get(f"http://localhost:{port}/file/nonexistent.png")
            assert status == 404
        finally:
            server.shutdown()

    def test_file_endpoint_url_encoded_filename(self, tmp_path):
        port = _free_port()
        content = b"GIF89a" + b"\x00" * 10
        entries = [_make_entry(tmp_path, "my image.gif", content, "image/gif")]
        server = _make_server(entries, [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, body, _ = _get(f"http://localhost:{port}/file/my%20image.gif")
            assert status == 200
            assert body == content
        finally:
            server.shutdown()

    def test_unknown_route_returns_404(self, tmp_path):
        port = _free_port()
        server = _make_server([], [tmp_path], port)
        _run_server_in_bg(server)
        try:
            status, _, _ = _get(f"http://localhost:{port}/does/not/exist")
            assert status == 404
        finally:
            server.shutdown()
