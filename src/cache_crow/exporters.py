"""
cache_crow.exporters — CSV and HTML export helpers.

Two public functions:
  export_csv(entries, output_path=None)  → CSV string or writes file
  export_html(entries, output_path=None, embed_thumbnails=True) → HTML string or writes file
"""

from __future__ import annotations

import base64
import csv
import datetime
import html as _html
import io
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import CacheEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CSV_COLUMNS = ["filename", "size_bytes", "mime_type", "modified_ts", "cdn_url", "guild_id", "channel_id", "app"]

_THUMB_SIZE_LIMIT = 500 * 1024  # 500 KB
_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _entry_to_row(entry: "CacheEntry") -> dict:
    """Convert a CacheEntry to a flat dict matching _CSV_COLUMNS."""
    m = entry.metadata
    return {
        "filename": entry.path.name,
        "size_bytes": entry.size,
        "mime_type": entry.mime_type,
        "modified_ts": entry.modified,
        "cdn_url": (m.url or "") if m else "",
        "guild_id": (m.guild_id or "") if m else "",
        "channel_id": (m.channel_id or "") if m else "",
        "app": entry.app_source or "",
    }


def _fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _fmt_ts(ts: float) -> str:
    if not ts:
        return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# CSV exporter
# ---------------------------------------------------------------------------

def export_csv(entries: list, output_path=None) -> str | None:
    """Export entries to CSV.

    Parameters
    ----------
    entries:
        List of CacheEntry objects.
    output_path:
        If given (str or Path), write the CSV to that file and return None.
        If None, return the CSV as a string.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for entry in entries:
        writer.writerow(_entry_to_row(entry))

    csv_text = buf.getvalue()

    if output_path is None:
        return csv_text

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(csv_text, encoding="utf-8")
    return None


# ---------------------------------------------------------------------------
# HTML exporter
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cache Crow — Media Report</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: system-ui, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    margin: 0; padding: 1.5rem;
  }}
  h1 {{ color: #a78bfa; margin-top: 0; }}
  .summary {{
    display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem;
  }}
  .stat-card {{
    background: #1e2030; border-radius: 8px; padding: 0.75rem 1.25rem;
    min-width: 140px;
  }}
  .stat-card .label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; }}
  .stat-card .value {{ font-size: 1.5rem; font-weight: 700; color: #e2e8f0; }}
  .controls {{
    display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; align-items: center;
  }}
  .controls input, .controls select {{
    background: #1e2030; border: 1px solid #334155; color: #e2e8f0;
    padding: 0.4rem 0.75rem; border-radius: 6px; font-size: 0.875rem;
  }}
  .controls input {{ flex: 1; min-width: 200px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 0.875rem;
    background: #1e2030; border-radius: 8px; overflow: hidden;
  }}
  thead tr {{ background: #2d3748; }}
  th {{
    padding: 0.75rem 1rem; text-align: left; font-weight: 600;
    color: #94a3b8; cursor: pointer; user-select: none; white-space: nowrap;
  }}
  th:hover {{ color: #e2e8f0; }}
  th.sorted-asc::after {{ content: " \\2191"; }}
  th.sorted-desc::after {{ content: " \\2193"; }}
  td {{ padding: 0.6rem 1rem; border-top: 1px solid #2d3748; vertical-align: middle; }}
  tr:hover td {{ background: #252840; }}
  .thumb {{ width: 48px; height: 48px; object-fit: cover; border-radius: 4px; }}
  .thumb-placeholder {{
    width: 48px; height: 48px; border-radius: 4px;
    background: #2d3748; display: flex; align-items: center; justify-content: center;
    font-size: 0.65rem; color: #64748b; text-align: center;
  }}
  .mime {{ font-size: 0.75rem; color: #64748b; }}
  .size {{ font-variant-numeric: tabular-nums; }}
  .cdn-url {{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cdn-url a {{ color: #60a5fa; text-decoration: none; }}
  .cdn-url a:hover {{ text-decoration: underline; }}
  .no-data {{ text-align: center; padding: 3rem; color: #64748b; }}
  .meta {{ font-size: 0.75rem; color: #64748b; margin-top: 1.5rem; }}
</style>
</head>
<body>
<h1>Cache Crow &mdash; Media Report</h1>
<div class="summary">
  <div class="stat-card"><div class="label">Total entries</div><div class="value">{total_count}</div></div>
  <div class="stat-card"><div class="label">Total size</div><div class="value">{total_size}</div></div>
  <div class="stat-card"><div class="label">With CDN URL</div><div class="value">{cdn_count}</div></div>
  <div class="stat-card"><div class="label">MIME types</div><div class="value">{mime_count}</div></div>
</div>
<div class="controls">
  <input type="search" id="filter-input" placeholder="Filter by filename, MIME type, app&hellip;">
  <select id="mime-select">
    <option value="">All types</option>
    {mime_options}
  </select>
</div>
<table id="media-table">
  <thead>
    <tr>
      <th data-col="thumb" style="width:60px">&#128248;</th>
      <th data-col="filename">Filename</th>
      <th data-col="size_bytes">Size</th>
      <th data-col="mime_type">MIME Type</th>
      <th data-col="modified_ts">Modified</th>
      <th data-col="cdn_url">CDN URL</th>
      <th data-col="guild_id">Guild ID</th>
      <th data-col="channel_id">Channel ID</th>
      <th data-col="app">App</th>
    </tr>
  </thead>
  <tbody id="table-body">
{rows}
  </tbody>
</table>
{no_data_block}
<p class="meta">Generated {generated_at} &bull; cache-crow</p>
<script>
(function() {{
  var rows = Array.from(document.querySelectorAll('#table-body tr'));
  var filterInput = document.getElementById('filter-input');
  var mimeSelect = document.getElementById('mime-select');
  var sortState = {{ col: null, dir: 1 }};

  function applyFilter() {{
    var text = filterInput.value.toLowerCase();
    var mime = mimeSelect.value;
    rows.forEach(function(tr) {{
      var rowText = tr.textContent.toLowerCase();
      var rowMime = tr.dataset.mime || '';
      var show = (!text || rowText.indexOf(text) !== -1) &&
                 (!mime || rowMime === mime);
      tr.style.display = show ? '' : 'none';
    }});
  }}

  function sortBy(col) {{
    var idx = ['thumb','filename','size_bytes','mime_type','modified_ts','cdn_url','guild_id','channel_id','app'].indexOf(col);
    if (idx === -1) return;
    if (sortState.col === col) {{ sortState.dir *= -1; }}
    else {{ sortState.col = col; sortState.dir = 1; }}
    var dir = sortState.dir;
    rows.sort(function(a, b) {{
      var av = (a.cells[idx] ? a.cells[idx].dataset.val || a.cells[idx].textContent : '');
      var bv = (b.cells[idx] ? b.cells[idx].dataset.val || b.cells[idx].textContent : '');
      var an = parseFloat(av), bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return dir * (an - bn);
      return dir * av.localeCompare(bv);
    }});
    var tbody = document.getElementById('table-body');
    rows.forEach(function(r) {{ tbody.appendChild(r); }});
    // update header classes
    document.querySelectorAll('th').forEach(function(th) {{
      th.classList.remove('sorted-asc','sorted-desc');
      if (th.dataset.col === col) {{
        th.classList.add(dir === 1 ? 'sorted-asc' : 'sorted-desc');
      }}
    }});
  }}

  filterInput.addEventListener('input', applyFilter);
  mimeSelect.addEventListener('change', applyFilter);

  document.querySelectorAll('th[data-col]').forEach(function(th) {{
    th.addEventListener('click', function() {{ sortBy(th.dataset.col); }});
  }});
}})();
</script>
</body>
</html>
"""

_ROW_TEMPLATE = """\
    <tr data-mime="{mime_type_esc}">
      <td>{thumb_cell}</td>
      <td data-val="{filename_esc}">{filename_esc}</td>
      <td class="size" data-val="{size_bytes}">{size_fmt}</td>
      <td data-val="{mime_type_esc}"><span class="mime">{mime_type_esc}</span></td>
      <td data-val="{modified_ts}">{modified_fmt}</td>
      <td class="cdn-url">{cdn_cell}</td>
      <td>{guild_id_esc}</td>
      <td>{channel_id_esc}</td>
      <td>{app_esc}</td>
    </tr>"""


def _make_thumb_cell(entry: "CacheEntry", embed: bool) -> str:
    """Return an <img> tag (embedded or empty placeholder) for the entry."""
    if entry.mime_type not in _IMAGE_MIMES:
        label = entry.mime_type.split("/")[-1].upper()
        return f'<div class="thumb-placeholder">{_html.escape(label)}</div>'

    if embed and entry.size <= _THUMB_SIZE_LIMIT:
        try:
            data = entry.path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            src = f"data:{entry.mime_type};base64,{b64}"
            return f'<img class="thumb" src="{src}" alt="{_html.escape(entry.path.name)}">'
        except OSError:
            pass

    # Fallback placeholder
    return '<div class="thumb-placeholder">IMG</div>'


def export_html(entries: list, output_path=None, embed_thumbnails: bool = True) -> str | None:
    """Export entries to a self-contained HTML report.

    Parameters
    ----------
    entries:
        List of CacheEntry objects.
    output_path:
        If given (str or Path), write the HTML to that file and return None.
        If None, return the HTML as a string.
    embed_thumbnails:
        If True (default), inline images under 500 KB as base64 data URIs.
    """
    total_count = len(entries)
    total_bytes = sum(e.size for e in entries)
    cdn_count = sum(1 for e in entries if e.metadata and e.metadata.url)
    all_mimes = sorted({e.mime_type for e in entries})
    mime_count = len(all_mimes)

    mime_options = "\n    ".join(
        f'<option value="{_html.escape(m)}">{_html.escape(m)}</option>'
        for m in all_mimes
    )

    row_parts: list[str] = []
    for entry in entries:
        row = _entry_to_row(entry)
        cdn_url = row["cdn_url"]
        if cdn_url:
            cdn_cell = f'<a href="{_html.escape(cdn_url)}" target="_blank" rel="noopener">{_html.escape(cdn_url[:60])}{"..." if len(cdn_url) > 60 else ""}</a>'
        else:
            cdn_cell = '<span style="color:#4a5568">—</span>'

        row_parts.append(_ROW_TEMPLATE.format(
            mime_type_esc=_html.escape(row["mime_type"]),
            thumb_cell=_make_thumb_cell(entry, embed_thumbnails),
            filename_esc=_html.escape(row["filename"]),
            size_bytes=row["size_bytes"],
            size_fmt=_html.escape(_fmt_size(row["size_bytes"])),
            modified_ts=row["modified_ts"],
            modified_fmt=_html.escape(_fmt_ts(row["modified_ts"])),
            cdn_cell=cdn_cell,
            guild_id_esc=_html.escape(row["guild_id"]),
            channel_id_esc=_html.escape(row["channel_id"]),
            app_esc=_html.escape(row["app"]),
        ))

    rows_html = "\n".join(row_parts)
    no_data_block = (
        '<p class="no-data">No entries to display.</p>' if not entries else ""
    )

    html_text = _HTML_TEMPLATE.format(
        total_count=total_count,
        total_size=_html.escape(_fmt_size(total_bytes)),
        cdn_count=cdn_count,
        mime_count=mime_count,
        mime_options=mime_options,
        rows=rows_html,
        no_data_block=no_data_block,
        generated_at=_html.escape(
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        ),
    )

    if output_path is None:
        return html_text

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_text, encoding="utf-8")
    return None
