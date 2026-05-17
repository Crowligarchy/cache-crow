"""
Watch mode: monitor cache directory for new files and auto-extract media.

Uses watchdog for filesystem events and rich for live display.
"""

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .scanner import identify_file_type, MIME_EXTENSIONS
from .extractor import MEDIA_TYPES

console = Console()

# Type icons for display
TYPE_ICONS: dict[str, str] = {
    "image/png": "[bold blue]PNG [/bold blue]",
    "image/jpeg": "[bold yellow]JPEG[/bold yellow]",
    "image/gif": "[bold green]GIF [/bold green]",
    "image/webp": "[bold cyan]WEBP[/bold cyan]",
    "video/mp4": "[bold magenta]MP4 [/bold magenta]",
    "video/webm": "[bold red]WEBM[/bold red]",
    "application/octet-stream": "[dim]BIN [/dim]",
}


def fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


class CacheWatcher:
    """
    Watches a cache directory for new files using watchdog.

    On new file creation:
    - Identifies the file type via magic bytes
    - Displays a live notification
    - Optionally extracts media files to output_dir
    """

    def __init__(
        self,
        cache_dir: Path,
        output_dir: Optional[Path] = None,
        show_all: bool = False,
        max_rows: int = 20,
    ) -> None:
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        self.show_all = show_all
        self.max_rows = max_rows

        self._seen: dict[str, dict] = {}  # filename -> info dict
        self._lock = threading.Lock()
        self._running = False
        self._observer = None
        self._extracted_count = 0

    def _handle_new_file(self, path: Path) -> None:
        """Process a newly created/modified cache file."""
        if not path.is_file():
            return

        # Wait briefly for file to be fully written
        time.sleep(0.1)

        try:
            stat = path.stat()
        except OSError:
            return

        mime = identify_file_type(path)
        is_media = mime in MEDIA_TYPES
        timestamp = datetime.now().strftime("%H:%M:%S")

        info = {
            "name": path.name,
            "mime": mime,
            "size": stat.st_size,
            "time": timestamp,
            "is_media": is_media,
            "extracted": False,
        }

        # Auto-extract if output dir specified and file is media
        if self.output_dir and is_media and stat.st_size >= 1024:
            ext = MIME_EXTENSIONS.get(mime, ".bin")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            dest = self.output_dir / (path.name + ext)
            counter = 1
            while dest.exists():
                dest = self.output_dir / (path.name + f"_{counter}" + ext)
                counter += 1
            try:
                shutil.copy2(path, dest)
                info["extracted"] = True
                self._extracted_count += 1
            except (OSError, PermissionError):
                pass

        if self.show_all or is_media:
            with self._lock:
                self._seen[path.name] = info

    def _build_table(self) -> Table:
        """Build a rich Table of recently seen files."""
        table = Table(
            title=f"[bold cyan]cache-crow watch[/bold cyan] — {self.cache_dir}",
            show_lines=False,
            expand=True,
        )
        table.add_column("Time", style="dim", width=8)
        table.add_column("File", style="cyan", width=12)
        table.add_column("Type", width=6)
        table.add_column("Size", justify="right", width=10)
        table.add_column("Action", width=12)

        with self._lock:
            rows = list(self._seen.values())[-self.max_rows :]

        for info in reversed(rows):
            type_label = TYPE_ICONS.get(info["mime"], "[dim]???[/dim]")
            action = ""
            if info["is_media"]:
                if info["extracted"]:
                    action = "[bold green]extracted[/bold green]"
                else:
                    action = "[yellow]media[/yellow]"
            else:
                action = "[dim]skipped[/dim]"

            table.add_row(
                info["time"],
                info["name"],
                type_label,
                fmt_size(info["size"]),
                action,
            )

        total_media = sum(1 for v in self._seen.values() if v["is_media"])
        table.caption = (
            f"[dim]Total seen: {len(self._seen)} | "
            f"Media: {total_media} | "
            f"Extracted: {self._extracted_count} | "
            f"Press Ctrl+C to stop[/dim]"
        )
        return table

    def run(self) -> None:
        """Start watching the cache directory. Blocks until Ctrl+C."""
        try:
            from watchdog.observers import Observer  # type: ignore
            from watchdog.events import FileSystemEventHandler  # type: ignore
        except ImportError:
            console.print("[red]watchdog is not installed. Run: pip install watchdog[/red]")
            return

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    watcher._handle_new_file(Path(event.src_path))

            def on_modified(self, event):
                if not event.is_directory:
                    p = Path(event.src_path)
                    # Only handle f_XXXXXX files (not index/data_ metadata files)
                    if p.name.startswith("f_"):
                        watcher._handle_new_file(p)

        observer = Observer()
        observer.schedule(_Handler(), str(self.cache_dir), recursive=False)
        observer.start()
        self._observer = observer
        self._running = True

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[cyan]Output directory:[/cyan] {self.output_dir}")

        console.print(
            f"[bold green]Watching[/bold green] {self.cache_dir} for new cache files..."
        )

        try:
            with Live(
                self._build_table(),
                console=console,
                refresh_per_second=4,
                screen=False,
            ) as live:
                while True:
                    live.update(self._build_table())
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            console.print(
                f"\n[bold]Watch stopped.[/bold] "
                f"Seen: {len(self._seen)} files, "
                f"extracted: {self._extracted_count}"
            )
