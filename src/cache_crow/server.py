"""
Local HTTP server with a browser-based gallery UI for cache-crow.

Usage:
    from cache_crow.server import run_server
    run_server(entries, port=8765, cache_dirs=[Path("/path/to/Cache_Data")])
"""

import json
import mimetypes
import socketserver
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote

from .models import CacheEntry

# ---------------------------------------------------------------------------
# Embedded single-page app
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>cache-crow gallery</title>
<style>
  :root {
    --bg: #0d0d0f;
    --surface: #17171a;
    --surface2: #1e1e23;
    --border: #2a2a32;
    --accent: #7c5ef0;
    --accent2: #5ea8f0;
    --text: #e8e8f0;
    --text-dim: #888898;
    --red: #f05e5e;
    --green: #5ef0a0;
    --radius: 10px;
    --card-w: 220px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    font-size: 14px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ---- header ---- */
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    position: sticky;
    top: 0;
    z-index: 100;
    flex-wrap: wrap;
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    font-size: 16px;
    letter-spacing: -0.3px;
    color: var(--accent);
    flex-shrink: 0;
  }
  .logo svg { width: 22px; height: 22px; fill: var(--accent); }
  .controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    flex: 1;
  }

  /* ---- filter buttons ---- */
  .filter-btn {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-dim);
    border-radius: 6px;
    padding: 5px 12px;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .filter-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  .filter-btn:hover:not(.active) {
    background: var(--border);
    color: var(--text);
  }

  /* ---- sort select ---- */
  select {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 5px 10px;
    cursor: pointer;
    font-size: 13px;
    appearance: none;
    -webkit-appearance: none;
  }
  select:focus { outline: 2px solid var(--accent); }

  /* ---- search ---- */
  .search-wrap {
    position: relative;
    flex: 1;
    min-width: 160px;
    max-width: 340px;
  }
  .search-wrap input {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 5px 10px 5px 32px;
    font-size: 13px;
  }
  .search-wrap input::placeholder { color: var(--text-dim); }
  .search-wrap input:focus { outline: 2px solid var(--accent); }
  .search-icon {
    position: absolute;
    left: 9px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-dim);
    pointer-events: none;
    font-size: 15px;
  }

  /* ---- count badge ---- */
  #result-count {
    margin-left: auto;
    color: var(--text-dim);
    font-size: 12px;
    white-space: nowrap;
  }

  /* ---- grid ---- */
  #grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--card-w), 1fr));
    gap: 14px;
    padding: 20px 24px;
    flex: 1;
  }

  /* ---- card ---- */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1),
                box-shadow 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    cursor: pointer;
  }
  .card:hover {
    transform: translateY(-3px) scale(1.015);
    box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px var(--accent);
  }
  .card-media {
    width: 100%;
    height: 160px;
    object-fit: cover;
    display: block;
    background: var(--surface2);
    flex-shrink: 0;
  }
  video.card-media { object-fit: contain; background: #000; }
  .card-audio-thumb {
    width: 100%;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--surface2);
    font-size: 36px;
    flex-shrink: 0;
  }
  .card-body {
    padding: 10px 12px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .card-name {
    font-size: 12px;
    font-weight: 500;
    color: var(--text);
    word-break: break-all;
    line-clamp: 2;
    -webkit-line-clamp: 2;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .card-meta {
    font-size: 11px;
    color: var(--text-dim);
    display: flex;
    gap: 8px;
  }
  .badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }
  .badge-image  { background: rgba(94,168,240,0.18); color: var(--accent2); }
  .badge-video  { background: rgba(124,94,240,0.18); color: var(--accent); }
  .badge-audio  { background: rgba(94,240,160,0.18); color: var(--green); }
  .badge-other  { background: rgba(200,200,210,0.1); color: var(--text-dim); }
  .card-actions {
    padding: 6px 12px 10px;
    display: flex;
    gap: 6px;
  }
  .btn {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 5px 0;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.12s, color 0.12s;
    text-align: center;
    text-decoration: none;
    display: block;
  }
  .btn:hover { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn-dl { background: var(--surface2); }

  /* ---- empty state ---- */
  #empty {
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 80px 20px;
    color: var(--text-dim);
    font-size: 15px;
    flex: 1;
  }
  #empty span { font-size: 48px; }

  /* ---- footer ---- */
  footer {
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 10px 24px;
    font-size: 12px;
    color: var(--text-dim);
    display: flex;
    gap: 20px;
  }
  footer strong { color: var(--text); }

  /* ---- lightbox ---- */
  #lightbox {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.88);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(6px);
  }
  #lightbox.open { display: flex; }
  #lb-content {
    position: relative;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }
  #lb-img {
    max-width: 90vw;
    max-height: 80vh;
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.7);
  }
  #lb-video {
    max-width: 90vw;
    max-height: 80vh;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.7);
  }
  #lb-info {
    color: var(--text-dim);
    font-size: 13px;
    text-align: center;
  }
  #lb-close {
    position: fixed;
    top: 20px;
    right: 24px;
    background: rgba(255,255,255,0.1);
    border: none;
    color: #fff;
    border-radius: 50%;
    width: 36px;
    height: 36px;
    cursor: pointer;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s;
  }
  #lb-close:hover { background: var(--red); }
  #lb-dl {
    background: var(--accent);
    border: none;
    color: #fff;
    border-radius: 6px;
    padding: 7px 20px;
    cursor: pointer;
    font-size: 13px;
    text-decoration: none;
    transition: opacity 0.15s;
  }
  #lb-dl:hover { opacity: 0.85; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>
    cache-crow
  </div>
  <div class="controls">
    <button class="filter-btn active" data-filter="all">All</button>
    <button class="filter-btn" data-filter="image">Images</button>
    <button class="filter-btn" data-filter="video">Videos</button>
    <button class="filter-btn" data-filter="audio">Audio</button>
    <select id="sort-select">
      <option value="size-desc">Largest first</option>
      <option value="size-asc">Smallest first</option>
      <option value="date-desc">Newest first</option>
      <option value="date-asc">Oldest first</option>
      <option value="type">By type</option>
    </select>
    <div class="search-wrap">
      <span class="search-icon">&#128269;</span>
      <input type="text" id="search-box" placeholder="Search filename..." />
    </div>
    <span id="result-count"></span>
  </div>
</header>

<div id="grid"></div>
<div id="empty"><span>&#128247;</span>No files match your filters.</div>

<footer>
  <span>Total: <strong id="stat-count">0</strong> files</span>
  <span>Size: <strong id="stat-size">0 MB</strong></span>
</footer>

<!-- Lightbox -->
<div id="lightbox">
  <button id="lb-close" title="Close (Esc)">&#10005;</button>
  <div id="lb-content">
    <img id="lb-img" src="" alt="" style="display:none" />
    <video id="lb-video" controls style="display:none"></video>
    <div id="lb-info"></div>
    <a id="lb-dl" href="#" download>&#8595; Download</a>
  </div>
</div>

<script>
(function () {
  let allEntries = [];
  let filtered = [];
  let activeFilter = 'all';
  let sortKey = 'size-desc';
  let searchTerm = '';

  function fmtSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(2) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }

  function fmtDate(ts) {
    return new Date(ts * 1000).toLocaleString();
  }

  function mediaCategory(mime) {
    if (mime.startsWith('image/')) return 'image';
    if (mime.startsWith('video/')) return 'video';
    if (mime.startsWith('audio/')) return 'audio';
    return 'other';
  }

  function badgeClass(cat) {
    return 'badge badge-' + cat;
  }

  function buildCard(e) {
    const cat = mediaCategory(e.mime_type);
    const fileUrl = '/file/' + encodeURIComponent(e.filename);

    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.filename = e.filename;
    card.dataset.cat = cat;

    let mediaEl = '';
    if (cat === 'image') {
      mediaEl = `<img class="card-media" src="${fileUrl}" loading="lazy" alt="${e.filename}" />`;
    } else if (cat === 'video') {
      mediaEl = `<video class="card-media" preload="metadata" muted>
        <source src="${fileUrl}" type="${e.mime_type}" />
      </video>`;
    } else if (cat === 'audio') {
      mediaEl = `<div class="card-audio-thumb">&#127925;</div>`;
    } else {
      mediaEl = `<div class="card-audio-thumb">&#128196;</div>`;
    }

    card.innerHTML = `
      ${mediaEl}
      <div class="card-body">
        <div class="card-name">${e.filename}</div>
        <div class="card-meta">
          <span class="${badgeClass(cat)}">${cat}</span>
          <span>${fmtSize(e.size)}</span>
        </div>
        <div class="card-meta" style="font-size:10px">${fmtDate(e.modified)}</div>
        ${e.guild_id ? `<div class="card-meta" style="font-size:10px;color:#5ea8f0">Guild: ${e.guild_id}</div>` : ''}
      </div>
      <div class="card-actions">
        <a class="btn btn-dl" href="${fileUrl}" download="${e.filename}">&#8595; Download</a>
      </div>`;

    // Click → lightbox (but not download btn)
    card.addEventListener('click', (ev) => {
      if (ev.target.closest('.btn-dl')) return;
      openLightbox(e, fileUrl, cat);
    });

    return card;
  }

  function openLightbox(e, fileUrl, cat) {
    const lb = document.getElementById('lightbox');
    const lbImg = document.getElementById('lb-img');
    const lbVid = document.getElementById('lb-video');
    const lbInfo = document.getElementById('lb-info');
    const lbDl = document.getElementById('lb-dl');

    lbImg.style.display = 'none';
    lbVid.style.display = 'none';
    lbImg.src = '';
    lbVid.src = '';

    if (cat === 'image') {
      lbImg.src = fileUrl;
      lbImg.style.display = 'block';
    } else if (cat === 'video') {
      lbVid.src = fileUrl;
      lbVid.style.display = 'block';
      lbVid.load();
    }

    lbInfo.textContent = `${e.filename}  •  ${fmtSize(e.size)}  •  ${e.mime_type}`;
    lbDl.href = fileUrl;
    lbDl.download = e.filename;
    lb.classList.add('open');
  }

  function closeLightbox() {
    const lb = document.getElementById('lightbox');
    const lbVid = document.getElementById('lb-video');
    lbVid.pause();
    lb.classList.remove('open');
  }

  document.getElementById('lb-close').addEventListener('click', closeLightbox);
  document.getElementById('lightbox').addEventListener('click', (e) => {
    if (e.target === document.getElementById('lightbox')) closeLightbox();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeLightbox();
  });

  function applyFiltersAndSort() {
    let list = allEntries.slice();

    // Filter by category
    if (activeFilter !== 'all') {
      list = list.filter(e => mediaCategory(e.mime_type) === activeFilter);
    }

    // Filter by search
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      list = list.filter(e => e.filename.toLowerCase().includes(term));
    }

    // Sort
    switch (sortKey) {
      case 'size-desc': list.sort((a, b) => b.size - a.size); break;
      case 'size-asc':  list.sort((a, b) => a.size - b.size); break;
      case 'date-desc': list.sort((a, b) => b.modified - a.modified); break;
      case 'date-asc':  list.sort((a, b) => a.modified - b.modified); break;
      case 'type':      list.sort((a, b) => a.mime_type.localeCompare(b.mime_type)); break;
    }

    filtered = list;
    renderGrid();
  }

  function renderGrid() {
    const grid = document.getElementById('grid');
    const empty = document.getElementById('empty');
    grid.innerHTML = '';

    if (filtered.length === 0) {
      grid.style.display = 'none';
      empty.style.display = 'flex';
    } else {
      grid.style.display = 'grid';
      empty.style.display = 'none';
      for (const e of filtered) {
        grid.appendChild(buildCard(e));
      }
    }

    document.getElementById('result-count').textContent =
      filtered.length + ' of ' + allEntries.length + ' files';
  }

  function updateFooter(entries) {
    const total = entries.length;
    const totalBytes = entries.reduce((s, e) => s + e.size, 0);
    document.getElementById('stat-count').textContent = total;
    document.getElementById('stat-size').textContent = fmtSize(totalBytes);
  }

  // Filter buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.dataset.filter;
      applyFiltersAndSort();
    });
  });

  // Sort
  document.getElementById('sort-select').addEventListener('change', (e) => {
    sortKey = e.target.value;
    applyFiltersAndSort();
  });

  // Search
  document.getElementById('search-box').addEventListener('input', (e) => {
    searchTerm = e.target.value.trim();
    applyFiltersAndSort();
  });

  // Load data
  fetch('/api/entries')
    .then(r => r.json())
    .then(data => {
      allEntries = data;
      updateFooter(data);
      applyFiltersAndSort();
    })
    .catch(err => {
      console.error('Failed to load entries:', err);
    });
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Server implementation
# ---------------------------------------------------------------------------

class _GalleryHandler(BaseHTTPRequestHandler):
    """Request handler for the cache-crow gallery server."""

    entries: list[CacheEntry] = []
    cache_dirs: list[Path] = []

    def log_message(self, fmt, *args):  # suppress default logging
        pass

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self) -> None:
        body = b"Not found"
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]

        if path == "/" or path == "":
            self._send_html(_HTML)
            return

        if path == "/api/entries":
            records = []
            for e in self.entries:
                rec = {
                    "filename": e.path.name,
                    "mime_type": e.mime_type,
                    "size": e.size,
                    "modified": e.modified,
                    "url": None,
                    "guild_id": None,
                    "channel_id": None,
                }
                if e.metadata:
                    rec["url"] = e.metadata.url
                    rec["guild_id"] = e.metadata.guild_id
                    rec["channel_id"] = e.metadata.channel_id
                records.append(rec)
            self._send_json(records)
            return

        if path.startswith("/file/"):
            filename = unquote(path[len("/file/"):])
            # Search across all cache dirs
            for cache_dir in self.cache_dirs:
                candidate = cache_dir / filename
                if candidate.exists() and candidate.is_file():
                    try:
                        data = candidate.read_bytes()
                    except OSError:
                        self._send_404()
                        return
                    ct, _ = mimetypes.guess_type(filename)
                    content_type = ct or "application/octet-stream"
                    self._send_bytes(data, content_type)
                    return
            self._send_404()
            return

        self._send_404()


def run_server(
    entries: list[CacheEntry],
    port: int = 8765,
    cache_dirs: list[Path] | None = None,
) -> None:
    """Start the gallery HTTP server and open the browser.

    Blocks until Ctrl+C.
    """
    if cache_dirs is None:
        # Derive unique parent dirs from entries
        seen: set[Path] = set()
        cache_dirs = []
        for e in entries:
            p = e.path.parent
            if p not in seen:
                seen.add(p)
                cache_dirs.append(p)

    # Build a handler class with the data bound via class attributes
    handler = type(
        "_BoundGalleryHandler",
        (_GalleryHandler,),
        {"entries": entries, "cache_dirs": cache_dirs},
    )

    server = HTTPServer(("localhost", port), handler)
    url = f"http://localhost:{port}"
    print(f"cache-crow gallery server running at {url}")
    print("Press Ctrl+C to stop.\n")

    # Open browser after a short delay to let the server bind
    t = threading.Timer(0.5, webbrowser.open, args=(url,))
    t.daemon = True
    t.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        print("\nServer stopped.")
