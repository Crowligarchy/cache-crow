"""
gallery.py — Generate a self-contained HTML media gallery from CacheEntry objects.

Usage:
    generate_gallery(entries, Path("gallery.html"))                  # linked mode
    generate_gallery(entries, Path("gallery.html"), embed_images=True)  # base64 embed
"""

from __future__ import annotations

import base64
import html
import math
from datetime import datetime, timezone
from pathlib import Path

from .models import CacheEntry

# ---------------------------------------------------------------------------
# MIME helpers
# ---------------------------------------------------------------------------

_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_VIDEO_MIMES = {"video/mp4", "video/webm"}
_AUDIO_MIMES = {"audio/mpeg", "audio/ogg", "audio/wav", "audio/flac", "audio/aac"}

_MIME_LABEL: dict[str, str] = {
    "image/png":  "PNG",
    "image/jpeg": "JPEG",
    "image/gif":  "GIF",
    "image/webp": "WebP",
    "video/mp4":  "MP4",
    "video/webm": "WebM",
    "audio/mpeg": "MP3",
    "audio/ogg":  "OGG",
    "audio/wav":  "WAV",
    "audio/flac": "FLAC",
    "audio/aac":  "AAC",
}

_FILTER_GROUPS: list[tuple[str, str]] = [
    ("all",   "All"),
    ("png",   "PNG"),
    ("jpeg",  "JPEG"),
    ("gif",   "GIF"),
    ("webp",  "WebP"),
    ("video", "Video"),
    ("audio", "Audio"),
]


def _mime_group(mime: str) -> str:
    if mime == "image/png":
        return "png"
    if mime == "image/jpeg":
        return "jpeg"
    if mime == "image/gif":
        return "gif"
    if mime == "image/webp":
        return "webp"
    if mime in _VIDEO_MIMES:
        return "video"
    if mime in _AUDIO_MIMES:
        return "audio"
    return "other"


def _fmt_size(size: int) -> str:
    if size >= 1_048_576:
        return f"{size / 1_048_576:.2f} MB"
    if size >= 1_024:
        return f"{size / 1_024:.1f} KB"
    return f"{size} B"


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ""


def _total_size_label(entries: list[CacheEntry]) -> str:
    total = sum(e.size for e in entries)
    return _fmt_size(total)


# ---------------------------------------------------------------------------
# Media source resolution
# ---------------------------------------------------------------------------

def _media_src_embedded(entry: CacheEntry) -> str | None:
    """Return a data-URI for an image entry, or None if unreadable."""
    if entry.mime_type not in _IMAGE_MIMES:
        return None
    try:
        data = entry.path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{entry.mime_type};base64,{b64}"
    except OSError:
        return None


def _media_src_linked(entry: CacheEntry, gallery_path: Path, output_dir: Path | None) -> str | None:
    """Return a relative URL from the gallery HTML file to the extracted media file."""
    if entry.mime_type not in _IMAGE_MIMES:
        return None
    if output_dir is None:
        return None
    try:
        rel = entry.path.relative_to(output_dir)
        # Compute path relative to the directory containing the gallery HTML
        gallery_dir = gallery_path.parent
        abs_media = output_dir / rel
        rel_from_gallery = abs_media.relative_to(gallery_dir)
        return str(rel_from_gallery).replace("\\", "/")
    except ValueError:
        # output_dir not a parent of entry.path — fall back to absolute
        return str(entry.path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Card HTML builder
# ---------------------------------------------------------------------------

def _build_card(
    entry: CacheEntry,
    embed: bool,
    gallery_path: Path,
    output_dir: Path | None,
    index: int,
) -> str:
    group = _mime_group(entry.mime_type)
    mime_label = _MIME_LABEL.get(entry.mime_type, entry.mime_type)
    size_label = _fmt_size(entry.size)
    ts_label = _fmt_ts(entry.modified) if entry.modified else ""
    filename = html.escape(entry.path.name)
    cdn_url = ""
    cdn_display = ""
    if entry.metadata and entry.metadata.url:
        cdn_url = html.escape(entry.metadata.url)
        cdn_display = html.escape(
            entry.metadata.url[:72] + ("..." if len(entry.metadata.url) > 72 else "")
        )

    # Determine the thumbnail / preview element
    is_image = entry.mime_type in _IMAGE_MIMES
    is_video = entry.mime_type in _VIDEO_MIMES
    is_audio = entry.mime_type in _AUDIO_MIMES

    preview_html = ""
    lightbox_src = ""

    if is_image:
        src: str | None = None
        if embed:
            src = _media_src_embedded(entry)
        else:
            src = _media_src_linked(entry, gallery_path, output_dir)

        if src:
            escaped_src = html.escape(src)
            preview_html = (
                f'<img class="card-thumb" src="{escaped_src}" '
                f'alt="{filename}" loading="lazy" '
                f'data-lightbox-src="{escaped_src}" data-index="{index}" />'
            )
            lightbox_src = escaped_src
        else:
            preview_html = (
                f'<div class="card-placeholder img-placeholder">'
                f'<span class="ph-icon">&#128444;</span>'
                f'<span class="ph-label">{mime_label}</span>'
                f'</div>'
            )

    elif is_video:
        preview_html = (
            f'<div class="card-placeholder video-placeholder">'
            f'<span class="ph-icon">&#127910;</span>'
            f'<span class="ph-label">{mime_label}</span>'
            f'</div>'
        )

    elif is_audio:
        preview_html = (
            f'<div class="card-placeholder audio-placeholder">'
            f'<span class="ph-icon">&#127925;</span>'
            f'<span class="ph-label">{mime_label}</span>'
            f'</div>'
        )

    else:
        preview_html = (
            f'<div class="card-placeholder other-placeholder">'
            f'<span class="ph-icon">&#128196;</span>'
            f'<span class="ph-label">{mime_label}</span>'
            f'</div>'
        )

    url_block = ""
    if cdn_url:
        url_block = f"""
        <div class="card-url">
          <span class="url-text" title="{cdn_url}">{cdn_display}</span>
          <button class="copy-btn" onclick="copyUrl(this, '{cdn_url}')" title="Copy URL">
            &#128203;
          </button>
        </div>"""

    ts_block = f'<div class="card-ts">{ts_label}</div>' if ts_label else ""

    lightbox_attr = f'data-lightbox-src="{lightbox_src}"' if lightbox_src else ""

    return f"""    <div class="card" data-group="{group}" data-size="{entry.size}" data-ts="{entry.modified}" {lightbox_attr}>
      <div class="card-media" {"onclick=\"openLightbox('" + lightbox_src + "')\"" if lightbox_src else ""}>
        {preview_html}
      </div>
      <div class="card-info">
        <div class="card-filename" title="{filename}">{filename}</div>
        <div class="card-meta">
          <span class="badge badge-mime">{mime_label}</span>
          <span class="badge badge-size">{size_label}</span>
        </div>
        {ts_block}
        {url_block}
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# CSS / JS inline assets
# ---------------------------------------------------------------------------

_CSS = """\
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:         #0d1117;
  --surface:    #161b22;
  --surface2:   #21262d;
  --border:     #30363d;
  --accent:     #58a6ff;
  --accent2:    #3fb950;
  --text:       #e6edf3;
  --text-muted: #8b949e;
  --danger:     #f85149;
  --radius:     8px;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 14px;
  min-height: 100vh;
}

/* ---- Header ---- */
header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
}
header h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.3px; }
header .logo { font-size: 24px; }
.stats-badge {
  margin-left: auto;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 12px;
  color: var(--text-muted);
}
.stats-badge strong { color: var(--accent2); }

/* ---- Controls ---- */
.controls {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.filter-bar { display: flex; gap: 6px; flex-wrap: wrap; }
.filter-btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text-muted);
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.filter-btn:hover { border-color: var(--accent); color: var(--text); }
.filter-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
  font-weight: 600;
}

.sort-bar { display: flex; gap: 6px; align-items: center; margin-left: auto; }
.sort-bar label { color: var(--text-muted); font-size: 12px; }
.sort-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.sort-select:focus { outline: 2px solid var(--accent); }

/* ---- Grid ---- */
.gallery-wrap { padding: 24px; }
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

/* ---- Card ---- */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: border-color 0.15s, transform 0.1s;
}
.card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
}
.card.hidden { display: none; }

.card-media {
  background: var(--surface2);
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: default;
}
.card-media[onclick] { cursor: zoom-in; }

.card-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.card-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  padding: 16px;
}
.ph-icon { font-size: 40px; line-height: 1; }
.ph-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--text-muted);
}
.video-placeholder { background: #0d1f0d; }
.audio-placeholder { background: #1a1a0d; }
.img-placeholder   { background: var(--surface2); }
.other-placeholder { background: var(--surface2); }

/* ---- Card info ---- */
.card-info {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.card-filename {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}

.card-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  border-radius: 4px;
  padding: 2px 7px;
}
.badge-mime { background: #1f2d3d; color: var(--accent); }
.badge-size { background: #1f2d1f; color: var(--accent2); }

.card-ts {
  font-size: 11px;
  color: var(--text-muted);
}

.card-url {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  margin-top: 2px;
}
.url-text {
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  font-family: ui-monospace, "Cascadia Code", monospace;
}
.copy-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.7;
  transition: opacity 0.15s;
}
.copy-btn:hover { opacity: 1; }

/* ---- Empty state ---- */
.empty-state {
  text-align: center;
  padding: 80px 24px;
  color: var(--text-muted);
}
.empty-state .empty-icon { font-size: 64px; margin-bottom: 16px; }
.empty-state h2 { font-size: 20px; color: var(--text); margin-bottom: 8px; }
.empty-state p { font-size: 14px; }

/* ---- Lightbox ---- */
#lightbox {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}
#lightbox.open { display: flex; }
#lightbox img {
  max-width: 92vw;
  max-height: 92vh;
  border-radius: var(--radius);
  box-shadow: 0 8px 40px rgba(0,0,0,0.7);
  cursor: default;
}
#lightbox-close {
  position: fixed;
  top: 16px;
  right: 20px;
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 50%;
  width: 36px;
  height: 36px;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1001;
  transition: background 0.15s;
}
#lightbox-close:hover { background: var(--danger); }

/* ---- Responsive ---- */
@media (max-width: 600px) {
  header { padding: 12px 16px; }
  .controls { padding: 10px 16px; }
  .gallery-wrap { padding: 16px; }
  .gallery-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
  .sort-bar { margin-left: 0; }
}
"""

_JS = """\
// ---- Filter ----
const allCards = Array.from(document.querySelectorAll('.card'));

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const group = btn.dataset.group;
    allCards.forEach(card => {
      if (group === 'all' || card.dataset.group === group) {
        card.classList.remove('hidden');
      } else {
        card.classList.add('hidden');
      }
    });
    updateCount();
  });
});

// ---- Sort ----
const grid = document.getElementById('gallery-grid');
document.getElementById('sort-select').addEventListener('change', function() {
  const val = this.value;
  const visible = Array.from(grid.children).filter(c => !c.classList.contains('hidden'));
  const hidden  = Array.from(grid.children).filter(c =>  c.classList.contains('hidden'));

  visible.sort((a, b) => {
    if (val === 'size-desc') return Number(b.dataset.size) - Number(a.dataset.size);
    if (val === 'size-asc')  return Number(a.dataset.size) - Number(b.dataset.size);
    if (val === 'date-desc') return Number(b.dataset.ts)   - Number(a.dataset.ts);
    if (val === 'date-asc')  return Number(a.dataset.ts)   - Number(b.dataset.ts);
    if (val === 'type')      return (a.dataset.group || '').localeCompare(b.dataset.group || '');
    return 0;
  });

  // Re-append in sorted order, then re-append hidden to keep them accessible
  [...visible, ...hidden].forEach(el => grid.appendChild(el));
});

// ---- Live count ----
function updateCount() {
  const vis = allCards.filter(c => !c.classList.contains('hidden')).length;
  document.getElementById('visible-count').textContent = vis;
}

// ---- Lightbox ----
const lightbox  = document.getElementById('lightbox');
const lbImg     = document.getElementById('lightbox-img');
const lbClose   = document.getElementById('lightbox-close');

function openLightbox(src) {
  if (!src) return;
  lbImg.src = src;
  lightbox.classList.add('open');
  document.body.style.overflow = 'hidden';
}

lightbox.addEventListener('click', (e) => {
  if (e.target === lightbox) closeLightbox();
});
lbClose.addEventListener('click', closeLightbox);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeLightbox();
});

function closeLightbox() {
  lightbox.classList.remove('open');
  lbImg.src = '';
  document.body.style.overflow = '';
}

// ---- Copy URL ----
function copyUrl(btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '&#10003;';
    btn.style.color = '#3fb950';
    setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; }, 1500);
  }).catch(() => {
    // Fallback for non-secure contexts
    const ta = document.createElement('textarea');
    ta.value = url;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
}
"""


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_gallery(
    entries: list[CacheEntry],
    output_path: Path,
    embed_images: bool = False,
    output_dir: Path | None = None,
) -> None:
    """Write a self-contained HTML gallery to *output_path*.

    Parameters
    ----------
    entries:
        List of CacheEntry objects to include in the gallery.
    output_path:
        Destination .html file path.
    embed_images:
        If True, encode image bytes as base64 data-URIs.
        If False, link to files relative to *output_dir*.
    output_dir:
        Directory where extracted files live (used for relative links in
        linked mode).  Ignored when embed_images=True.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_files = len(entries)
    total_size = _total_size_label(entries)

    # Build cards
    card_fragments: list[str] = []
    for idx, entry in enumerate(entries):
        card_fragments.append(
            _build_card(entry, embed=embed_images, gallery_path=output_path,
                        output_dir=output_dir, index=idx)
        )

    cards_html = "\n".join(card_fragments)

    # Filter buttons
    filter_btns = "\n".join(
        f'        <button class="filter-btn{"  active" if key == "all" else ""}" '
        f'data-group="{key}">{label}</button>'
        for key, label in _FILTER_GROUPS
    )

    # Main content
    if not entries:
        main_content = """\
    <div class="empty-state">
      <div class="empty-icon">&#128269;</div>
      <h2>No media found</h2>
      <p>The cache scan returned no recoverable media entries.</p>
    </div>"""
    else:
        main_content = f"""\
    <div class="gallery-grid" id="gallery-grid">
{cards_html}
    </div>"""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>cache-crow &mdash; Media Gallery</title>
  <style>
{_CSS}  </style>
</head>
<body>

<header>
  <span class="logo">&#129415;</span>
  <h1>cache-crow &mdash; Media Gallery</h1>
  <div class="stats-badge">
    <strong id="visible-count">{total_files}</strong> of
    <strong>{total_files}</strong> files &nbsp;&middot;&nbsp;
    <strong>{total_size}</strong> total
  </div>
</header>

<div class="controls">
  <div class="filter-bar" role="group" aria-label="Filter by type">
{filter_btns}
  </div>
  <div class="sort-bar">
    <label for="sort-select">Sort:</label>
    <select id="sort-select" class="sort-select" aria-label="Sort order">
      <option value="size-desc">Size &darr;</option>
      <option value="size-asc">Size &uarr;</option>
      <option value="date-desc">Date &darr;</option>
      <option value="date-asc">Date &uarr;</option>
      <option value="type">Type</option>
    </select>
  </div>
</div>

<div class="gallery-wrap">
{main_content}
</div>

<!-- Lightbox -->
<div id="lightbox" role="dialog" aria-modal="true" aria-label="Image preview">
  <button id="lightbox-close" aria-label="Close preview">&times;</button>
  <img id="lightbox-img" src="" alt="Preview" />
</div>

<script>
{_JS}
</script>
</body>
</html>
"""

    output_path.write_text(html_doc, encoding="utf-8")
