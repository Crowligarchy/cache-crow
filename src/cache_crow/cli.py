import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .extractor import extract_media, MEDIA_TYPES
from .scanner import find_cache_dirs, scan_cache, MIME_EXTENSIONS

console = Console()

_EPILOG = """
examples:
  # scan your Discord cache, show a table of all found media
  cache-crow

  # quick stats: counts and sizes, no file listing
  cache-crow --stats

  # extract all media >=1 KB to ./recovered/ with correct extensions
  cache-crow --output-dir ./recovered

  # target Slack instead of Discord
  cache-crow --app slack

  # point at an arbitrary cache directory (forensics, other users' profiles)
  cache-crow --cache-dir /path/to/Cache_Data

  # machine-readable JSON output (pipe-friendly)
  cache-crow --format json | jq '.[] | select(.mime_type == "video/mp4")'

  # enrich results with CDN URLs from cache entry headers
  cache-crow --metadata

  # live-monitoring mode: alert as new cache files appear
  cache-crow --watch --output-dir ./live-capture

  # interactive TUI browser (requires: pip install cache-crow[tui])
  cache-crow --tui

  # extract only files larger than 50 KB
  cache-crow --output-dir ./recovered --min-size 51200

supported apps:
  discord, discord-canary, discord-ptb, slack

cache locations (auto-detected per OS):
  Linux:   ~/.config/discord/Cache/Cache_Data/
  macOS:   ~/Library/Application Support/discord/Cache/Cache_Data/
  Windows: %APPDATA%\\discord\\Cache\\Cache_Data\\
"""


def resolve_cache_dirs(app: str, cache_dir: str | None) -> list[Path]:
    if cache_dir:
        p = Path(cache_dir).expanduser()
        if not p.exists():
            console.print(f"[red]Cache dir not found:[/red] {p}")
            sys.exit(1)
        return [p]
    dirs = find_cache_dirs(app)
    if not dirs:
        console.print(f"[yellow]No cache directories found for app:[/yellow] {app}")
        console.print(
            f"[dim]Tip: use --cache-dir /path/to/Cache_Data to specify a directory manually[/dim]"
        )
        sys.exit(1)
    return dirs


def fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cache-crow",
        description=(
            "Scan and extract media from Electron app caches.\n"
            "Identifies files by magic bytes — no guessing, no extensions needed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--app",
        default="discord",
        choices=["discord", "slack"],
        metavar="APP",
        help="Target app: discord (default) or slack",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        metavar="PATH",
        help="Override the cache directory (skips auto-detection)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="PATH",
        help="Extract found media files into PATH with correct extensions",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=1024,
        metavar="BYTES",
        help="Minimum file size to extract, in bytes (default: 1024)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print summary stats only (file counts and sizes, no listing)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        metavar="FORMAT",
        help="Output format: table (default) or json (pipe-friendly)",
    )
    parser.add_argument(
        "--metadata",
        action="store_true",
        help=(
            "Enrich entries with CDN URLs and guild/channel IDs from cache "
            "entry headers (and LevelDB index if available)"
        ),
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the cache directory for new files in real time (Ctrl+C to stop)",
    )
    parser.add_argument(
        "--watch-all",
        action="store_true",
        help="In watch mode, display all files (not just media)",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help=(
            "Launch interactive TUI browser "
            "(install textual: pip install 'cache-crow[tui]')"
        ),
    )

    args = parser.parse_args()

    # --- Watch mode ---
    if args.watch:
        dirs = resolve_cache_dirs(args.app, args.cache_dir)
        output_dir = Path(args.output_dir).expanduser() if args.output_dir else None

        from .watcher import CacheWatcher

        for cache_dir in dirs:
            console.print(f"[bold]Watching:[/bold] {cache_dir}")
            watcher = CacheWatcher(
                cache_dir=cache_dir,
                output_dir=output_dir,
                show_all=args.watch_all,
            )
            watcher.run()
        return

    dirs = resolve_cache_dirs(args.app, args.cache_dir)

    all_entries = []
    for cache_dir in dirs:
        all_entries.extend(scan_cache(cache_dir))

    # --- Metadata enrichment ---
    if args.metadata:
        from .metadata import enrich_entries_with_metadata

        for cache_dir in dirs:
            dir_entries = [e for e in all_entries if e.path.parent == cache_dir]
            enrich_entries_with_metadata(dir_entries, cache_dir)

        enriched = sum(1 for e in all_entries if e.metadata and e.metadata.url)
        if enriched:
            console.print(
                f"[green]Metadata:[/green] enriched {enriched} of {len(all_entries)} entries with CDN URLs"
            )
        else:
            console.print(
                "[yellow]Metadata:[/yellow] no CDN URLs found "
                "(LevelDB index may be absent or cache files have no headers)"
            )

    media_entries = [e for e in all_entries if e.mime_type in MEDIA_TYPES]

    # --- TUI mode ---
    if args.tui:
        from .tui import launch_tui

        output_dir = Path(args.output_dir).expanduser() if args.output_dir else None
        launch_tui(all_entries, output_dir=output_dir)
        return

    # --- Stats mode ---
    if args.stats:
        by_type: dict[str, int] = {}
        total_size = 0
        for e in media_entries:
            by_type[e.mime_type] = by_type.get(e.mime_type, 0) + 1
            total_size += e.size

        stats_table = Table(title="Cache Stats", show_lines=True)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", justify="right")
        stats_table.add_row("Total files scanned", str(len(all_entries)))
        stats_table.add_row("Media files found", str(len(media_entries)))
        stats_table.add_row("Total media size", fmt_size(total_size))
        console.print(stats_table)

        if by_type:
            type_table = Table(title="Breakdown by Type", show_lines=True)
            type_table.add_column("Type", style="cyan")
            type_table.add_column("Count", justify="right")
            for mime, count in sorted(by_type.items(), key=lambda x: -x[1]):
                type_table.add_row(mime, str(count))
            console.print(type_table)

        if args.metadata:
            meta_entries = [e for e in all_entries if e.metadata and e.metadata.url]
            if meta_entries:
                meta_table = Table(title="CDN URLs Recovered", show_lines=True)
                meta_table.add_column("File", style="cyan")
                meta_table.add_column("Guild ID")
                meta_table.add_column("Channel ID")
                meta_table.add_column("URL", style="green")
                for e in meta_entries[:20]:
                    m = e.metadata
                    meta_table.add_row(
                        e.path.name,
                        m.guild_id or "-",
                        m.channel_id or "-",
                        (m.url or "")[:60],
                    )
                console.print(meta_table)
        return

    # --- Extract mode ---
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
        all_stats: dict = {
            "total_scanned": 0,
            "extracted": 0,
            "skipped": 0,
            "by_type": {},
        }
        for cache_dir in dirs:
            console.print(f"\n[bold cyan]Extracting from:[/bold cyan] {cache_dir}")
            stats = extract_media(cache_dir, output_dir, min_size=args.min_size)
            all_stats["total_scanned"] += stats["total_scanned"]
            all_stats["extracted"] += stats["extracted"]
            all_stats["skipped"] += stats["skipped"]
            for mime, count in stats["by_type"].items():
                all_stats["by_type"][mime] = all_stats["by_type"].get(mime, 0) + count

        if args.format == "json":
            print(json.dumps(all_stats, indent=2))
            return

        result_table = Table(title="Extraction Results", show_lines=True)
        result_table.add_column("Metric", style="cyan")
        result_table.add_column("Value", justify="right")
        result_table.add_row("Total scanned", str(all_stats["total_scanned"]))
        result_table.add_row("Extracted", str(all_stats["extracted"]))
        result_table.add_row("Skipped", str(all_stats["skipped"]))
        console.print(result_table)

        if all_stats["by_type"]:
            type_table = Table(title="By Type", show_lines=True)
            type_table.add_column("MIME Type", style="cyan")
            type_table.add_column("Count", justify="right")
            for mime, count in sorted(all_stats["by_type"].items(), key=lambda x: -x[1]):
                type_table.add_row(mime, str(count))
            console.print(type_table)

        console.print(f"\n[bold]Output:[/bold] {output_dir}")
        return

    # --- JSON output mode ---
    if args.format == "json":
        records = []
        for e in sorted(media_entries, key=lambda x: x.size, reverse=True):
            rec: dict = {
                "filename": e.path.name,
                "path": str(e.path),
                "mime_type": e.mime_type,
                "size": e.size,
                "modified": e.modified,
            }
            if e.metadata:
                rec["url"] = e.metadata.url
                rec["guild_id"] = e.metadata.guild_id
                rec["channel_id"] = e.metadata.channel_id
                rec["cdn_filename"] = e.metadata.cdn_filename
            print(json.dumps(rec))
        return

    # --- Default: print table of found media ---
    table = Table(title=f"Media in {args.app} cache", show_lines=True)
    table.add_column("Filename", style="cyan", no_wrap=True)
    table.add_column("Type")
    table.add_column("Size", justify="right")

    if args.metadata:
        table.add_column("CDN URL", style="green")
        table.add_column("Guild ID")
        table.add_column("Channel ID")

    for e in sorted(media_entries, key=lambda x: x.size, reverse=True):
        if args.metadata:
            m = e.metadata
            url = (m.url or "")[:50] if m else ""
            guild = m.guild_id or "-" if m else "-"
            channel = m.channel_id or "-" if m else "-"
            table.add_row(e.path.name, e.mime_type, fmt_size(e.size), url, guild, channel)
        else:
            table.add_row(e.path.name, e.mime_type, fmt_size(e.size))

    console.print(table)
    console.print(f"[bold]Media files found:[/bold] {len(media_entries)} of {len(all_entries)} total")
