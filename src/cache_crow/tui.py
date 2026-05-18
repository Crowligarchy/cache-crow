"""
Textual TUI: interactive gallery browser for Discord cache files.

Layout:
  - Header: filter bar, sort selector, file count, total size
  - Left panel: scrollable file list (filename, type, size, relative time)
  - Right panel: metadata view (MIME, size, date, path, CDN URL, optional preview)
  - Footer: keybinding hints
  - Keybindings: ↑/↓ or j/k navigate, e extract, s save, d delete, f filter, q quit, / search
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import time
from typing import Optional

from .models import CacheEntry, CacheMetadata
from .scanner import MIME_EXTENSIONS
from .extractor import MEDIA_TYPES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TYPE_ICONS: dict[str, str] = {
    "image/png": "PNG ",
    "image/jpeg": "JPEG",
    "image/gif": "GIF ",
    "image/webp": "WEBP",
    "video/mp4": "MP4 ",
    "video/webm": "WEBM",
    "application/octet-stream": "BIN ",
}

TYPE_DISPLAY_ICONS: dict[str, str] = {
    "image/png": "[blue]PNG [/blue]",
    "image/jpeg": "[yellow]JPEG[/yellow]",
    "image/gif": "[green]GIF [/green]",
    "image/webp": "[cyan]WEBP[/cyan]",
    "video/mp4": "[magenta]MP4 [/magenta]",
    "video/webm": "[red]WEBM[/red]",
    "application/octet-stream": "[dim]BIN [/dim]",
}

# Filter cycle order
FILTER_CYCLE = ["all", "images", "videos", "gifs"]

# Sort cycle order
SORT_CYCLE = ["date", "size", "type", "name"]

# Default dump directory
DEFAULT_DUMP_DIR = Path.home() / "Pictures" / "cache-crow"

# MIME types belonging to each filter group
FILTER_MIMES: dict[str, set[str]] = {
    "all": set(TYPE_ICONS.keys()),
    "images": {"image/png", "image/jpeg", "image/webp"},
    "videos": {"video/mp4", "video/webm"},
    "gifs": {"image/gif"},
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def fmt_size(size: int) -> str:
    """Human-readable file size."""
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def relative_time(ts: float) -> str:
    """Return a short human-readable relative time string (e.g. '2d', '1h', '5m')."""
    delta = int(time() - ts)
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def _ffprobe_duration(path: Path) -> Optional[str]:
    """Return formatted video duration via ffprobe, or None if unavailable."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        seconds = float(result.stdout.strip())
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"
    except Exception:
        return None


def _apply_filter(entries: list[CacheEntry], filter_name: str) -> list[CacheEntry]:
    """Return entries matching the given filter group."""
    allowed = FILTER_MIMES.get(filter_name, set(TYPE_ICONS.keys()))
    return [e for e in entries if e.mime_type in allowed]


def _apply_sort(entries: list[CacheEntry], sort_key: str) -> list[CacheEntry]:
    """Return entries sorted by the given key."""
    if sort_key == "date":
        return sorted(entries, key=lambda e: e.modified, reverse=True)
    if sort_key == "size":
        return sorted(entries, key=lambda e: e.size, reverse=True)
    if sort_key == "type":
        return sorted(entries, key=lambda e: e.mime_type)
    if sort_key == "name":
        return sorted(entries, key=lambda e: e.path.name)
    return entries


def _apply_search(entries: list[CacheEntry], query: str) -> list[CacheEntry]:
    """Return entries whose filename contains the query (case-insensitive)."""
    if not query:
        return entries
    q = query.lower()
    return [e for e in entries if q in e.path.name.lower()]


def _is_saved(entry: CacheEntry, dump_dir: Path) -> bool:
    """Return True if the entry has already been saved to the dump directory."""
    ext = MIME_EXTENSIONS.get(entry.mime_type, ".bin")
    dest = dump_dir / (entry.path.name + ext)
    return dest.exists()


# ---------------------------------------------------------------------------
# Main TUI launcher
# ---------------------------------------------------------------------------

def launch_tui(
    entries: list[CacheEntry],
    output_dir: Optional[Path] = None,
) -> None:
    """
    Launch the Textual TUI cache gallery browser.

    Args:
        entries: List of CacheEntry objects to display.
        output_dir: If set, 'e' key extracts selected file here.
    """
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Horizontal, Vertical, ScrollableContainer
        from textual.widgets import (
            DataTable,
            Footer,
            Header,
            Input,
            Label,
            Select,
            Static,
        )
        from textual.reactive import reactive
        from textual import events
    except ImportError:
        _fallback_tui(entries, output_dir)
        return

    dump_dir = DEFAULT_DUMP_DIR

    # ------------------------------------------------------------------
    # MetadataPanel widget
    # ------------------------------------------------------------------

    class MetadataPanel(Static):
        """Right panel: shows metadata for the selected cache entry."""

        DEFAULT_CSS = """
        MetadataPanel {
            width: 100%;
            height: 100%;
            padding: 1 2;
        }
        """

        def render_entry(self, entry: Optional[CacheEntry]) -> str:
            if entry is None:
                return "[dim]No file selected. Use arrow keys to navigate.[/dim]"

            lines: list[str] = []

            # --- Basic info ---
            lines.append(f"[bold cyan]{entry.path.name}[/bold cyan]")
            lines.append("")

            icon_str = TYPE_DISPLAY_ICONS.get(entry.mime_type, "[dim]??? [/dim]")
            lines.append(f"[bold]Type:[/bold]     {icon_str}  {entry.mime_type}")
            lines.append(f"[bold]Size:[/bold]     {fmt_size(entry.size)} ({entry.size:,} B)")

            mod_dt = datetime.fromtimestamp(entry.modified)
            rel = relative_time(entry.modified)
            lines.append(
                f"[bold]Modified:[/bold] {mod_dt.strftime('%Y-%m-%d %H:%M')}  [dim]({rel} ago)[/dim]"
            )
            lines.append(f"[bold]Path:[/bold]     [dim]{entry.path}[/dim]")

            # --- Video duration ---
            if entry.mime_type in {"video/mp4", "video/webm"}:
                dur = _ffprobe_duration(entry.path)
                if dur:
                    lines.append(f"[bold]Duration:[/bold] {dur}")

            lines.append("")

            # --- CDN metadata ---
            if entry.metadata and entry.metadata.url:
                meta = entry.metadata
                lines.append("[bold green]CDN Metadata[/bold green]")
                lines.append(f"[bold]URL:[/bold]      {meta.url}")
                if meta.guild_id:
                    lines.append(f"[bold]Guild:[/bold]    {meta.guild_id}")
                if meta.channel_id:
                    lines.append(f"[bold]Channel:[/bold]  {meta.channel_id}")
                if meta.cdn_filename:
                    lines.append(f"[bold]CDN name:[/bold] {meta.cdn_filename}")
                if meta.content_type:
                    lines.append(f"[bold]Ctype:[/bold]    {meta.content_type}")
            else:
                lines.append("[dim]No CDN metadata.[/dim]")

            lines.append("")

            # --- Saved indicator ---
            if _is_saved(entry, dump_dir):
                lines.append("[green]Saved to dump dir[/green]  [dim]([bold]d[/bold] to delete)[/dim]")
            else:
                lines.append("[dim]Not in dump dir  ([bold]s[/bold] to save)[/dim]")

            # --- Extract hint ---
            lines.append("")
            if entry.mime_type in MEDIA_TYPES:
                if output_dir:
                    lines.append("[bold]\\[e][/bold] Extract    [bold]\\[s][/bold] Save    [bold]\\[d][/bold] Delete")
                else:
                    lines.append("[bold]\\[s][/bold] Save    [bold]\\[d][/bold] Delete")
                    lines.append("[dim](Use --output-dir to enable custom extraction)[/dim]")

            return "\n".join(lines)

        def update_entry(self, entry: Optional[CacheEntry]) -> None:
            self.update(self.render_entry(entry))

    # ------------------------------------------------------------------
    # Main App
    # ------------------------------------------------------------------

    class CacheBrowserApp(App):
        """Textual gallery browser for Discord cache files."""

        TITLE = "cache-crow"
        SUB_TITLE = "Discord Cache Browser"

        CSS = """
        Screen {
            layout: vertical;
        }

        /* ---- Top bar ---- */
        #top-bar {
            layout: horizontal;
            height: 3;
            background: $boost;
            padding: 0 1;
            align: left middle;
        }
        #filter-label {
            width: auto;
            margin-right: 1;
            color: $text-muted;
        }
        #filter-value {
            width: 10;
            color: $accent;
            text-style: bold;
        }
        #sort-label {
            width: auto;
            margin-left: 2;
            margin-right: 1;
            color: $text-muted;
        }
        #sort-value {
            width: 8;
            color: $accent;
            text-style: bold;
        }
        #search-input {
            width: 20;
            margin-left: 2;
            height: 1;
            border: none;
        }
        #stats-label {
            width: 1fr;
            text-align: right;
            color: $text-muted;
        }

        /* ---- Main split ---- */
        #main-container {
            layout: horizontal;
            height: 1fr;
        }
        #file-panel {
            width: 45%;
            height: 100%;
            border: solid $primary;
            padding: 0;
        }
        #meta-panel {
            width: 55%;
            height: 100%;
            border: solid $accent;
            padding: 0;
        }

        /* ---- Status bar ---- */
        #status-bar {
            height: 1;
            background: $boost;
            color: $text-muted;
            padding: 0 1;
        }

        DataTable {
            height: 100%;
        }
        """

        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("escape", "quit", "Quit", show=False),
            Binding("e", "extract", "Extract"),
            Binding("s", "save_dump", "Save"),
            Binding("d", "delete_dump", "Delete"),
            Binding("f", "cycle_filter", "Filter"),
            Binding("t", "cycle_sort", "Sort"),
            Binding("slash", "focus_search", "Search", key_display="/"),
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
        ]

        _filter_index: int = 0
        _sort_index: int = 0
        _search_query: str = ""
        _selected_entry: Optional[CacheEntry] = None
        _displayed_entries: list[CacheEntry] = []

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="top-bar"):
                yield Static("Filter:", id="filter-label")
                yield Static("all", id="filter-value")
                yield Static("Sort:", id="sort-label")
                yield Static("date", id="sort-value")
                yield Input(placeholder="/search...", id="search-input")
                yield Static("", id="stats-label")
            with Horizontal(id="main-container"):
                with Vertical(id="file-panel"):
                    yield DataTable(id="file-table", cursor_type="row")
                with Vertical(id="meta-panel"):
                    yield MetadataPanel(id="meta-content")
            yield Static("", id="status-bar")
            yield Footer()

        # ------------------------------------------------------------------
        # Lifecycle
        # ------------------------------------------------------------------

        def on_mount(self) -> None:
            self._refresh_table()

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "search-input":
                self._search_query = event.value
                self._refresh_table()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            """Return focus to the file table after submitting the search."""
            if event.input.id == "search-input":
                table = self.query_one("#file-table", DataTable)
                table.focus()

        def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
            if event.row_key and event.row_key.value:
                key = event.row_key.value
                for entry in self._displayed_entries:
                    if entry.path.name == key:
                        self._selected_entry = entry
                        self.query_one("#meta-content", MetadataPanel).update_entry(entry)
                        break

        # ------------------------------------------------------------------
        # Table rendering
        # ------------------------------------------------------------------

        def _refresh_table(self) -> None:
            """Re-filter, re-sort, and rebuild the file table."""
            filter_name = FILTER_CYCLE[self._filter_index]
            sort_name = SORT_CYCLE[self._sort_index]

            filtered = _apply_filter(entries, filter_name)
            filtered = _apply_search(filtered, self._search_query)
            sorted_entries = _apply_sort(filtered, sort_name)
            self._displayed_entries = sorted_entries

            # Update top-bar labels
            self.query_one("#filter-value", Static).update(filter_name)
            self.query_one("#sort-value", Static).update(sort_name)

            total_size = sum(e.size for e in sorted_entries)
            self.query_one("#stats-label", Static).update(
                f"Found: {len(sorted_entries)}  Total: {fmt_size(total_size)}"
            )

            # Rebuild the DataTable
            table = self.query_one("#file-table", DataTable)
            table.clear(columns=True)
            table.add_columns("File", "Type", "Size", "Age")

            for entry in sorted_entries:
                age = relative_time(entry.modified)
                icon = TYPE_ICONS.get(entry.mime_type, "??? ")
                saved_marker = "[green]*[/green]" if _is_saved(entry, dump_dir) else " "
                has_meta = "[cyan]M[/cyan]" if (entry.metadata and entry.metadata.url) else " "
                label = f"{saved_marker}{has_meta} {entry.path.name}"
                table.add_row(
                    label,
                    icon,
                    fmt_size(entry.size),
                    age,
                    key=entry.path.name,
                )

            # Update status bar
            self.query_one("#status-bar", Static).update(
                f"[dim][bold]↑↓/jk[/bold]=nav  [bold]e[/bold]=extract  "
                f"[bold]s[/bold]=save  [bold]d[/bold]=delete  "
                f"[bold]f[/bold]=filter  [bold]t[/bold]=sort  "
                f"[bold]/[/bold]=search  [bold]q[/bold]=quit[/dim]"
            )

            # Restore selection or pick first row
            if sorted_entries:
                # Try to re-select the previously selected entry
                current_name = self._selected_entry.path.name if self._selected_entry else None
                match_idx = 0
                if current_name:
                    for i, e in enumerate(sorted_entries):
                        if e.path.name == current_name:
                            match_idx = i
                            break
                self._selected_entry = sorted_entries[match_idx]
                self.query_one("#meta-content", MetadataPanel).update_entry(self._selected_entry)
                # Move cursor
                table.move_cursor(row=match_idx)
            else:
                self._selected_entry = None
                self.query_one("#meta-content", MetadataPanel).update_entry(None)

        # ------------------------------------------------------------------
        # Actions
        # ------------------------------------------------------------------

        def action_cycle_filter(self) -> None:
            self._filter_index = (self._filter_index + 1) % len(FILTER_CYCLE)
            self._refresh_table()
            self.notify(
                f"Filter: {FILTER_CYCLE[self._filter_index]}",
                title="Filter",
                timeout=1.5,
            )

        def action_cycle_sort(self) -> None:
            self._sort_index = (self._sort_index + 1) % len(SORT_CYCLE)
            self._refresh_table()
            self.notify(
                f"Sort: {SORT_CYCLE[self._sort_index]}",
                title="Sort",
                timeout=1.5,
            )

        def action_focus_search(self) -> None:
            inp = self.query_one("#search-input", Input)
            inp.focus()

        def action_cursor_down(self) -> None:
            self.query_one("#file-table", DataTable).action_scroll_down()

        def action_cursor_up(self) -> None:
            self.query_one("#file-table", DataTable).action_scroll_up()

        def action_extract(self) -> None:
            """Extract the selected file to output_dir."""
            entry = self._selected_entry
            if not entry:
                self.notify("No file selected.", severity="warning")
                return
            if entry.mime_type not in MEDIA_TYPES:
                self.notify(
                    f"Not a media file ({entry.mime_type}).",
                    severity="warning",
                )
                return
            if not output_dir:
                self.notify(
                    "No output directory set. Run with --output-dir.",
                    severity="warning",
                )
                return

            output_dir.mkdir(parents=True, exist_ok=True)
            ext = MIME_EXTENSIONS.get(entry.mime_type, ".bin")
            dest = output_dir / (entry.path.name + ext)
            counter = 1
            while dest.exists():
                dest = output_dir / (entry.path.name + f"_{counter}" + ext)
                counter += 1
            try:
                shutil.copy2(entry.path, dest)
                self.notify(f"Extracted: {dest.name}", title="Extracted", severity="information")
            except Exception as exc:
                self.notify(f"Extraction failed: {exc}", title="Error", severity="error")

        def action_save_dump(self) -> None:
            """Save the selected file to the default dump directory."""
            entry = self._selected_entry
            if not entry:
                self.notify("No file selected.", severity="warning")
                return
            if entry.mime_type not in MEDIA_TYPES:
                self.notify(f"Not a media file ({entry.mime_type}).", severity="warning")
                return

            dump_dir.mkdir(parents=True, exist_ok=True)
            ext = MIME_EXTENSIONS.get(entry.mime_type, ".bin")
            dest = dump_dir / (entry.path.name + ext)
            if dest.exists():
                self.notify(f"Already saved: {dest.name}", severity="information")
                return
            try:
                shutil.copy2(entry.path, dest)
                self.notify(
                    f"Saved to {dump_dir.name}/{dest.name}",
                    title="Saved",
                    severity="information",
                )
                # Refresh to update saved markers
                self._refresh_table()
            except Exception as exc:
                self.notify(f"Save failed: {exc}", title="Error", severity="error")

        def action_delete_dump(self) -> None:
            """Delete the selected file from the dump directory."""
            entry = self._selected_entry
            if not entry:
                self.notify("No file selected.", severity="warning")
                return

            ext = MIME_EXTENSIONS.get(entry.mime_type, ".bin")
            dest = dump_dir / (entry.path.name + ext)
            if not dest.exists():
                self.notify("File not in dump dir.", severity="warning")
                return
            try:
                dest.unlink()
                self.notify(f"Deleted: {dest.name}", title="Deleted", severity="information")
                self._refresh_table()
            except Exception as exc:
                self.notify(f"Delete failed: {exc}", title="Error", severity="error")

        def action_quit(self) -> None:
            self.exit()

    app = CacheBrowserApp()
    app.run()


# ---------------------------------------------------------------------------
# Fallback TUI (rich-based, used when textual is not installed)
# ---------------------------------------------------------------------------

def _fallback_tui(
    entries: list[CacheEntry],
    output_dir: Optional[Path] = None,
) -> None:
    """Fallback interactive browser using rich (when textual is not available)."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    sorted_entries = sorted(entries, key=lambda x: x.size, reverse=True)
    media_entries = [e for e in sorted_entries if e.mime_type in MEDIA_TYPES]
    total_size = sum(e.size for e in entries)

    table = Table(
        title="[bold]cache-crow[/bold] — Cache Browser (fallback mode)",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="cyan")
    table.add_column("Type")
    table.add_column("Size", justify="right")
    table.add_column("Age", justify="right")
    table.add_column("CDN URL", style="green")

    for i, entry in enumerate(sorted_entries, 1):
        icon = TYPE_ICONS.get(entry.mime_type, "??? ")
        url = ""
        if entry.metadata and entry.metadata.url:
            url = entry.metadata.url[:40] + "..."
        age = relative_time(entry.modified)
        table.add_row(str(i), entry.path.name, icon, fmt_size(entry.size), age, url)

    console.print(table)
    console.print(
        f"\n[bold]Total:[/bold] {len(entries)} files | "
        f"Media: {len(media_entries)} | "
        f"Size: {fmt_size(total_size)}"
    )
    console.print(
        "\n[dim]Install textual for interactive TUI: pip install 'cache-crow[tui]'[/dim]"
    )
