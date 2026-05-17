"""
Textual TUI: interactive browser for Discord cache files.

Layout:
  - Left panel: scrollable file list (filename, type icon, size)
  - Right panel: metadata view (MIME, size, date, CDN URL, guild/channel IDs)
  - Status bar: total file count, total size, keybindings hint
  - Keybindings: arrow keys navigate, 'e' extract, 'q' quit, '/' filter
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import CacheEntry, CacheMetadata
from .scanner import MIME_EXTENSIONS
from .extractor import MEDIA_TYPES

# Type icons (unicode)
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


def fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def launch_tui(
    entries: list[CacheEntry],
    output_dir: Optional[Path] = None,
) -> None:
    """
    Launch the Textual TUI cache browser.

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
            Label,
            Static,
        )
        from textual.reactive import reactive
    except ImportError:
        # Fallback to rich-based interactive display
        _fallback_tui(entries, output_dir)
        return

    total_size = sum(e.size for e in entries)
    media_count = sum(1 for e in entries if e.mime_type in MEDIA_TYPES)

    class MetadataPanel(Static):
        """Right panel: shows metadata for the selected entry."""

        DEFAULT_CSS = """
        MetadataPanel {
            width: 100%;
            height: 100%;
            padding: 1 2;
            border: solid $accent;
        }
        """

        def render_entry(self, entry: Optional[CacheEntry]) -> str:
            if entry is None:
                return "[dim]No file selected. Use arrow keys to navigate.[/dim]"

            lines = []
            lines.append(f"[bold cyan]File:[/bold cyan] {entry.path.name}")
            lines.append(f"[bold]MIME Type:[/bold]  {entry.mime_type}")
            lines.append(f"[bold]Size:[/bold]       {fmt_size(entry.size)} ({entry.size:,} bytes)")
            mod_dt = datetime.fromtimestamp(entry.modified)
            lines.append(f"[bold]Modified:[/bold]   {mod_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"[bold]Path:[/bold]       {entry.path}")
            lines.append("")

            if entry.metadata and entry.metadata.url:
                meta = entry.metadata
                lines.append("[bold green]CDN Metadata[/bold green]")
                lines.append(f"[bold]URL:[/bold]        {meta.url}")
                if meta.guild_id:
                    lines.append(f"[bold]Guild ID:[/bold]   {meta.guild_id}")
                if meta.channel_id:
                    lines.append(f"[bold]Channel ID:[/bold] {meta.channel_id}")
                if meta.cdn_filename:
                    lines.append(f"[bold]CDN Name:[/bold]   {meta.cdn_filename}")
                if meta.content_type:
                    lines.append(f"[bold]Content-Type:[/bold] {meta.content_type}")
            else:
                lines.append("[dim]No CDN metadata available.[/dim]")
                lines.append("[dim](Run with --metadata flag to attempt metadata enrichment)[/dim]")

            lines.append("")
            if entry.mime_type in MEDIA_TYPES:
                if output_dir:
                    lines.append("[bold green]Press 'e' to extract this file[/bold green]")
                else:
                    lines.append(
                        "[dim]Run with --output-dir to enable extraction[/dim]"
                    )
            return "\n".join(lines)

        def update_entry(self, entry: Optional[CacheEntry]) -> None:
            self.update(self.render_entry(entry))

    class CacheBrowserApp(App):
        """Textual app for browsing Discord cache files."""

        TITLE = "cache-crow TUI"
        SUB_TITLE = "Discord Cache Browser"
        CSS = """
        Screen {
            layout: vertical;
        }
        #main-container {
            layout: horizontal;
            height: 1fr;
        }
        #file-panel {
            width: 55%;
            height: 100%;
            border: solid $primary;
            padding: 0;
        }
        #meta-panel {
            width: 45%;
            height: 100%;
        }
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
            Binding("e", "extract", "Extract"),
            Binding("escape", "quit", "Quit", show=False),
        ]

        selected_entry: Optional[CacheEntry] = None
        _extracted_count: int = 0

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="main-container"):
                with Vertical(id="file-panel"):
                    yield Label("[bold]Cache Files[/bold]", id="file-label")
                    yield DataTable(id="file-table", cursor_type="row")
                with Vertical(id="meta-panel"):
                    yield Label("[bold]File Details[/bold]", id="meta-label")
                    yield MetadataPanel(id="meta-content")
            yield Static(
                f"[dim]Files: {len(entries)} | Media: {media_count} | "
                f"Total: {fmt_size(total_size)} | "
                f"[bold]q[/bold]=quit [bold]e[/bold]=extract [bold]↑↓[/bold]=navigate[/dim]",
                id="status-bar",
            )
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#file-table", DataTable)
            table.add_columns("File", "Type", "Size", "Modified")

            sorted_entries = sorted(entries, key=lambda x: x.size, reverse=True)
            for entry in sorted_entries:
                mod_dt = datetime.fromtimestamp(entry.modified)
                icon = TYPE_ICONS.get(entry.mime_type, "??? ")
                has_meta = "[green]*[/green]" if (entry.metadata and entry.metadata.url) else " "
                table.add_row(
                    f"{has_meta} {entry.path.name}",
                    icon,
                    fmt_size(entry.size),
                    mod_dt.strftime("%m/%d %H:%M"),
                    key=entry.path.name,
                )

            # Store sorted entries for lookup
            self._sorted_entries = sorted_entries

            if sorted_entries:
                self.selected_entry = sorted_entries[0]
                meta_panel = self.query_one("#meta-content", MetadataPanel)
                meta_panel.update_entry(self.selected_entry)

        def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
            if event.row_key and event.row_key.value:
                filename = event.row_key.value
                # Strip leading metadata indicator if present
                filename = filename.strip()
                for entry in self._sorted_entries:
                    if entry.path.name == filename:
                        self.selected_entry = entry
                        meta_panel = self.query_one("#meta-content", MetadataPanel)
                        meta_panel.update_entry(entry)
                        break

        def action_extract(self) -> None:
            """Extract the selected file to output_dir."""
            entry = self.selected_entry
            if not entry:
                self.notify("No file selected.", severity="warning")
                return
            if entry.mime_type not in MEDIA_TYPES:
                self.notify(
                    f"Not a media file ({entry.mime_type}) — skipping extraction.",
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
                self._extracted_count += 1
                self.notify(
                    f"Extracted: {dest.name}",
                    title="Extracted",
                    severity="information",
                )
            except Exception as exc:
                self.notify(
                    f"Extraction failed: {exc}",
                    title="Error",
                    severity="error",
                )

        def action_quit(self) -> None:
            self.exit()

    app = CacheBrowserApp()
    app.run()


def _fallback_tui(
    entries: list[CacheEntry],
    output_dir: Optional[Path] = None,
) -> None:
    """Fallback interactive browser using rich (when textual is not available)."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    import sys

    console = Console()

    sorted_entries = sorted(entries, key=lambda x: x.size, reverse=True)
    media_entries = [e for e in sorted_entries if e.mime_type in MEDIA_TYPES]
    total_size = sum(e.size for e in entries)

    table = Table(title="[bold]cache-crow[/bold] — Cache Browser (fallback mode)", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="cyan")
    table.add_column("Type")
    table.add_column("Size", justify="right")
    table.add_column("CDN URL", style="green")

    for i, entry in enumerate(sorted_entries, 1):
        icon = TYPE_ICONS.get(entry.mime_type, "??? ")
        url = ""
        if entry.metadata and entry.metadata.url:
            url = entry.metadata.url[:40] + "..."
        table.add_row(str(i), entry.path.name, icon, fmt_size(entry.size), url)

    console.print(table)
    console.print(
        f"\n[bold]Total:[/bold] {len(entries)} files | "
        f"Media: {len(media_entries)} | "
        f"Size: {fmt_size(total_size)}"
    )
    console.print(
        "\n[dim]Install textual for interactive TUI: pip install textual[/dim]"
    )
