import argparse
import base64
import datetime
import json
import re
import shutil
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .config import (
    CONFIG_FILE,
    Config,
    default_db_path,
    default_dump_dir,
    load_config,
    set_setting,
)
from .extractor import extract_media, MEDIA_TYPES
from .models import relative_time
from .scanner import ALL_APPS, find_cache_dirs, scan_all_apps, scan_cache, MIME_EXTENSIONS

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

  # generate a self-contained HTML gallery (images embedded as base64)
  cache-crow --gallery gallery.html

  # generate a gallery that links to files extracted alongside it
  cache-crow --output-dir ./recovered --gallery ./recovered/gallery.html

supported apps:
  discord, discord-canary, discord-ptb, slack

cache locations (auto-detected per OS):
  Linux:   ~/.config/discord/Cache/Cache_Data/
  macOS:   ~/Library/Application Support/discord/Cache/Cache_Data/
  Windows: %APPDATA%\\discord\\Cache\\Cache_Data\\
"""


def fmt_timestamp(ts: float) -> str:
    """Format a Unix timestamp as 'YYYY-MM-DD HH:MM' in local time."""
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def parse_date_filter(value: str) -> float:
    """Parse a date filter value and return a Unix timestamp.

    Accepted formats:
      - "YYYY-MM-DD"      — start of that calendar day (local time)
      - "Nd"              — N days ago from now  (e.g. "7d")
      - "Nh"              — N hours ago from now (e.g. "24h")
      - "N" alone         — treated as days for backwards compat
    """
    now = time.time()
    # Relative: 7d / 24h / 1h
    m = re.fullmatch(r"(\d+)([dh]?)", value.strip(), re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "h":
            return now - n * 3600
        # "d" or bare number — treat as days
        return now - n * 86400
    # Absolute date
    try:
        dt = datetime.datetime.strptime(value.strip(), "%Y-%m-%d")
        return dt.timestamp()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date/time filter {value!r}. "
            "Use YYYY-MM-DD, '7d' (7 days ago), or '24h' (24 hours ago)."
        )


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



def _write_gallery(
    entries: list,
    gallery_path: str,
    output_dir,
    console,
) -> None:
    from .gallery import generate_gallery

    dest = Path(gallery_path).expanduser()
    embed = output_dir is None
    generate_gallery(entries, dest, embed_images=embed, output_dir=output_dir)
    mode = "embedded" if embed else "linked"
    console.print(
        f"[bold green]Gallery:[/bold green] {dest} "
        f"[dim]({mode}, {len(entries)} entries)[/dim]"
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_config_show(cfg: Config) -> None:
    """Print the current config values."""
    table = Table(title=f"Config ({CONFIG_FILE})", show_lines=True)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for key, value in sorted(cfg.as_dict().items()):
        table.add_row(key, str(value))
    console.print(table)


def cmd_config_set(key: str, value: str) -> None:
    """Persist a single config key=value pair."""
    try:
        set_setting(key, value)
        console.print(f"[green]Set[/green] {key} = {value!r}  (saved to {CONFIG_FILE})")
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


def cmd_history(db_path: Path, limit: int = 20) -> None:
    """Print the last N extracted files from the SQLite DB."""
    from .db import CrowDB

    with CrowDB(db_path) as db:
        rows = db.history(limit=limit)
        stats = db.stats()

    if not rows:
        console.print("[yellow]No extraction history found.[/yellow]")
        console.print(f"[dim]DB: {db_path}[/dim]")
        return

    table = Table(title=f"Extraction History (last {limit})", show_lines=True)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Cache File", style="cyan", no_wrap=True)
    table.add_column("MIME Type")
    table.add_column("Size", justify="right")
    table.add_column("Extracted To")
    table.add_column("When")

    for row in rows:
        cp = Path(row["cache_path"])
        ep = row["extracted_path"] or row["dump_path"] or "-"
        if ep and ep != "-":
            ep = Path(ep).name
        ts = row["extracted_at"] or row["discovered_at"]
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"
        table.add_row(
            str(row["id"]),
            cp.name,
            row["mime_type"],
            fmt_size(row["size_bytes"] or 0),
            str(ep),
            when,
        )

    console.print(table)
    console.print(
        f"[dim]Total seen: {stats.get('total_seen', 0)} | "
        f"Extracted: {stats.get('total_extracted', 0)} | "
        f"Dumped: {stats.get('total_dumped', 0)} | "
        f"DB: {db_path}[/dim]"
    )


def cmd_dump(dump_dir: Path) -> None:
    """Show contents and total size of the permanent dump directory."""
    if not dump_dir.exists():
        console.print(f"[yellow]Dump directory does not exist:[/yellow] {dump_dir}")
        console.print("[dim]Use --save to populate it.[/dim]")
        return

    files = sorted(f for f in dump_dir.iterdir() if f.is_file())
    total_size = sum(f.stat().st_size for f in files)

    table = Table(title=f"Dump Directory: {dump_dir}", show_lines=True)
    table.add_column("Filename", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Modified")

    for f in files:
        stat = f.stat()
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
        table.add_row(f.name, fmt_size(stat.st_size), when)

    console.print(table)
    console.print(f"[bold]{len(files)} files[/bold] — total {fmt_size(total_size)}")



def _purge_dir(target_dir, label: str, yes: bool) -> None:
    """Delete all files in target_dir after an optional confirmation prompt."""
    from pathlib import Path
    target_dir = Path(target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        console.print(f"[yellow]Directory not found, skipping:[/yellow] {target_dir}")
        return
    files = [f for f in target_dir.iterdir() if f.is_file()]
    total_size = sum(f.stat().st_size for f in files)
    console.print(
        f"\n[bold]{label}[/bold] {target_dir}\n"
        f"  Files : {len(files)}\n"
        f"  Size  : {fmt_size(total_size)}"
    )
    if not files:
        console.print("  [dim]Nothing to purge.[/dim]")
        return
    if not yes:
        answer = input("  Confirm purge? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            console.print("  [dim]Skipped.[/dim]")
            return
    deleted = 0
    errors = 0
    for f in files:
        try:
            f.unlink()
            deleted += 1
        except OSError as exc:
            console.print(f"  [red]Error deleting {f.name}:[/red] {exc}")
            errors += 1
    console.print(
        f"  [green]Deleted {deleted} file(s).[/green]"
        + (f" [red]{errors} error(s).[/red]" if errors else "")
    )


def cmd_purge(args) -> None:
    """Handle the purge subcommand."""
    purge_target = args.purge_target
    yes = args.yes
    if purge_target in ("cache", "all"):
        app = getattr(args, "app", "discord")
        cache_dir_override = getattr(args, "cache_dir", None)
        if app == "all":
            dirs = find_cache_dirs("all")
        else:
            dirs = resolve_cache_dirs(app, cache_dir_override)
        for d in dirs:
            _purge_dir(d, "Cache directory:", yes)
    if purge_target in ("dump", "all"):
        dump_dir_arg = getattr(args, "dump_dir", None)
        if dump_dir_arg:
            dump_dir = Path(dump_dir_arg).expanduser()
        else:
            try:
                cfg = load_config()
                dump_dir = cfg.dump_dir or default_dump_dir()
            except Exception:
                dump_dir = default_dump_dir()
        _purge_dir(dump_dir, "Dump directory:", yes)


def main() -> None:
    # Load config first so defaults can inform argument defaults
    cfg = load_config()

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
        default=cfg.default_app,
        choices=ALL_APPS,
        metavar="APP",
        help=(
            "Target app (default: discord). "
            "Choices: " + ", ".join(ALL_APPS)
        ),
    )
    parser.add_argument(
        "--all-apps",
        action="store_true",
        help=(
            "Scan all known apps at once. "
            "Adds an 'App' column to the table labelling each entry's source app. "
            "Supersedes --app."
        ),
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
        default=cfg.min_size,
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
    parser.add_argument(
        "--timeline",
        action="store_true",
        help="Sort results chronologically (oldest first) and show a 'Modified' timestamp column.",
    )

    parser.add_argument(
        "--sort",
        choices=["size", "date", "type", "name"],
        default="size",
        metavar="FIELD",
        help="Sort results by: size (default), date, type, or name",
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="DATE",
        help=(
            "Only include files modified after DATE. "
            "Accepts YYYY-MM-DD, '7d' (7 days ago), or '24h' (24 hours ago)."
        ),
    )
    parser.add_argument(
        "--until",
        default=None,
        metavar="DATE",
        help=(
            "Only include files modified before DATE. "
            "Accepts YYYY-MM-DD, '7d' (7 days ago), or '24h' (24 hours ago)."
        ),
    )
    parser.add_argument(
        "--gallery",
        default=None,
        metavar="PATH",
        help=(
            "Write a self-contained HTML media gallery to PATH. "
            "When combined with --output-dir, images are linked to the extracted files; "
            "without --output-dir, images are embedded as base64 data-URIs."
        ),
    )

    parser.add_argument(
        "--serve",
        nargs="?",
        const=8765,
        type=int,
        metavar="PORT",
        help=(
            "Start a local web gallery server at http://localhost:PORT "
            "(default port 8765). Opens the browser automatically. "
            "Works with --app, --cache-dir, and --metadata."
        ),
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help=(
            "Show duplicate groups (files with identical content) in output, "
            "grouped by SHA-256 hash."
        ),
    )
    parser.add_argument(
        "--dedupe-keep",
        choices=["first", "largest", "newest"],
        default=None,
        metavar="STRATEGY",
        help=(
            "When extracting with --output-dir and --dedupe, keep only one "
            "copy per duplicate group. Strategies: first, largest, newest."
        ),
    )
    # --- New flags ---
    parser.add_argument(
        "--dump-dir",
        default=None,
        metavar="PATH",
        help="Permanent archive directory (overrides config dump_dir)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Quick-save all found media to the dump directory",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        metavar="PATH",
        help="SQLite DB path (overrides config db_path)",
    )

    # --- Subcommands ---
    subparsers = parser.add_subparsers(dest="subcommand")

    config_parser = subparsers.add_parser("config", help="Show or edit persistent config")
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_sub.add_parser("show", help="Show current config")
    config_set_p = config_sub.add_parser("set", help="Set a config value")
    config_set_p.add_argument("key", help="Config key to set")
    config_set_p.add_argument("value", help="New value")

    history_parser = subparsers.add_parser("history", help="Show recent extractions from DB")
    history_parser.add_argument(
        "-n", "--limit", type=int, default=20, metavar="N",
        help="Number of records to show (default: 20)",
    )

    subparsers.add_parser("dump", help="Show dump directory contents and size")

    purge_parser = subparsers.add_parser(
        "purge",
        help="Delete files from cache or dump directories",
        description="Remove files from cache directories or the dump directory.",
    )
    purge_parser.add_argument(
        "purge_target",
        choices=["cache", "dump", "all"],
        metavar="TARGET",
        help="What to purge: cache, dump, or all",
    )
    purge_parser.add_argument(
        "--app",
        default="discord",
        choices=ALL_APPS + ["all"],
        metavar="APP",
        help="Target app for cache purge (default: discord)",
    )
    purge_parser.add_argument(
        "--cache-dir",
        default=None,
        metavar="PATH",
        help="Override cache directory for purge",
    )
    purge_parser.add_argument(
        "--dump-dir",
        default=None,
        metavar="PATH",
        help="Override dump directory for purge (default: from config)",
    )
    purge_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # --- Resolve effective dump_dir and db_path (CLI > config > default) ---
    effective_dump_dir: Path = (
        Path(args.dump_dir).expanduser()
        if getattr(args, "dump_dir", None)
        else (cfg.dump_dir or default_dump_dir())
    )
    effective_db_path: Path = (
        Path(args.db_path).expanduser()
        if getattr(args, "db_path", None)
        else (cfg.db_path or default_db_path())
    )

    # --- Subcommand dispatch ---
    if args.subcommand == "config":
        action = getattr(args, "config_action", None)
        if action == "set":
            cmd_config_set(args.key, args.value)
        else:
            cmd_config_show(cfg)
        return

    if args.subcommand == "history":
        cmd_history(effective_db_path, limit=args.limit)
        return

    if args.subcommand == "dump":
        cmd_dump(effective_dump_dir)
        return

    if args.subcommand == "purge":
        cmd_purge(args)
        return

    # --- Watch mode ---
    if args.watch:
        if args.all_apps:
            console.print("[yellow]--all-apps is not supported in watch mode; use --app instead.[/yellow]")
            sys.exit(1)
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

    # --- Resolve date filters early so we can error-check before scanning ---
    since_ts: float | None = None
    until_ts: float | None = None
    if args.since:
        try:
            since_ts = parse_date_filter(args.since)
        except argparse.ArgumentTypeError as exc:
            console.print(f"[red]--since:[/red] {exc}")
            sys.exit(1)
    if args.until:
        try:
            until_ts = parse_date_filter(args.until)
        except argparse.ArgumentTypeError as exc:
            console.print(f"[red]--until:[/red] {exc}")
            sys.exit(1)

    # --- Scan ---
    if args.all_apps:
        all_entries = scan_all_apps()
        dirs = []  # not needed downstream for all-apps mode
    else:
        dirs = resolve_cache_dirs(args.app, args.cache_dir)
        all_entries = []
        for cache_dir in dirs:
            all_entries.extend(scan_cache(cache_dir, app_source=args.app))

    # --- Apply date filters ---
    if since_ts is not None:
        all_entries = [e for e in all_entries if e.modified >= since_ts]
    if until_ts is not None:
        all_entries = [e for e in all_entries if e.modified <= until_ts]

    # --- Record all seen files in the DB (cumulative stats) ---
    from .db import CrowDB

    with CrowDB(effective_db_path) as _db:
        for _entry in all_entries:
            _cdn = _entry.metadata.url if _entry.metadata else None
            _db.mark_seen(
                _entry.path,
                mime_type=_entry.mime_type,
                size_bytes=_entry.size,
                cdn_url=_cdn,
            )

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

    # --- Save to dump dir ---
    if args.save:
        effective_dump_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        with CrowDB(effective_db_path) as _db:
            for _entry in media_entries:
                if _entry.size < args.min_size:
                    continue
                _ext = MIME_EXTENSIONS.get(_entry.mime_type, ".bin")
                _dest = effective_dump_dir / (_entry.path.name + _ext)
                _counter = 1
                while _dest.exists():
                    _dest = effective_dump_dir / (_entry.path.name + f"_{_counter}" + _ext)
                    _counter += 1
                try:
                    shutil.copy2(_entry.path, _dest)
                    _db.mark_dumped(_entry.path, _dest)
                    saved += 1
                except (OSError, PermissionError):
                    pass
        console.print(
            f"[green]Saved {saved} media files[/green] to {effective_dump_dir}"
        )
        return

    # --- Serve mode ---
    if args.serve is not None:
        from .server import run_server
        console.print(f"[bold cyan]Starting gallery server on port {args.serve}...[/bold cyan]")
        run_server(media_entries, port=args.serve, cache_dirs=dirs)
        return

    # --- Dedupe display mode ---
    if args.dedupe:
        from .dedup import find_duplicates
        dup_groups = find_duplicates(media_entries)
        if not dup_groups:
            console.print("[green]No duplicates found.[/green]")
        else:
            console.print(f"[bold]Found {len(dup_groups)} duplicate group(s):[/bold]")
            for digest, members in dup_groups.items():
                dup_table = Table(title=f"Hash: {digest[:16]}...", show_lines=True)
                dup_table.add_column("Filename", style="cyan", no_wrap=True)
                dup_table.add_column("Type")
                dup_table.add_column("Size", justify="right")
                dup_table.add_column("Modified", style="dim")
                for e in members:
                    dup_table.add_row(
                        e.path.name,
                        e.mime_type,
                        fmt_size(e.size),
                        fmt_timestamp(e.modified),
                    )
                console.print(dup_table)
        return

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
        with CrowDB(effective_db_path) as _xdb:
            for cache_dir in dirs:
                console.print(f"\n[bold cyan]Extracting from:[/bold cyan] {cache_dir}")
                stats = extract_media(cache_dir, output_dir, min_size=args.min_size)
                all_stats["total_scanned"] += stats["total_scanned"]
                all_stats["extracted"] += stats["extracted"]
                all_stats["skipped"] += stats["skipped"]
                for mime, count in stats["by_type"].items():
                    all_stats["by_type"][mime] = all_stats["by_type"].get(mime, 0) + count

                # Record extractions in DB
                for _xentry in scan_cache(cache_dir):
                    if _xentry.mime_type in MEDIA_TYPES and _xentry.size >= args.min_size:
                        _xext = MIME_EXTENSIONS.get(_xentry.mime_type, ".bin")
                        _xdest = output_dir / (_xentry.path.name + _xext)
                        if _xdest.exists():
                            _xdb.mark_extracted(_xentry.path, extracted_path=_xdest)

        if args.gallery:
            _write_gallery(media_entries, args.gallery, output_dir=output_dir, console=console)

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
        if args.timeline:
            json_entries = sorted(media_entries, key=lambda x: x.modified)
        else:
            json_entries = sorted(media_entries, key=lambda x: x.size, reverse=True)
        for e in json_entries:
            rec: dict = {
                "filename": e.path.name,
                "path": str(e.path),
                "mime_type": e.mime_type,
                "size": e.size,
                "modified": e.modified,
                "modified_fmt": fmt_timestamp(e.modified),
                "mtime": e.mtime,
                "mtime_iso": datetime.datetime.fromtimestamp(e.mtime).isoformat() if e.mtime else None,
                "ctime": e.ctime,
                "relative_time": relative_time(e.mtime) if e.mtime else None,
            }
            if e.app_source is not None:
                rec["app_source"] = e.app_source
            if e.metadata:
                rec["url"] = e.metadata.url
                rec["guild_id"] = e.metadata.guild_id
                rec["channel_id"] = e.metadata.channel_id
                rec["cdn_filename"] = e.metadata.cdn_filename
            print(json.dumps(rec))
        return

    # --- Gallery (no --output-dir: embed as base64) ---
    if args.gallery:
        _write_gallery(media_entries, args.gallery, output_dir=None, console=console)

    # --- Default: print table of found media ---
    title = "Media in all app caches" if args.all_apps else f"Media in {args.app} cache"
    table = Table(title=title, show_lines=True)
    table.add_column("Filename", style="cyan", no_wrap=True)
    table.add_column("Type")
    table.add_column("Size", justify="right")
    table.add_column("Modified", justify="right", style="dim")
    table.add_column("Age")
    if args.all_apps:
        table.add_column("App", style="magenta")
    if args.metadata:
        table.add_column("CDN URL", style="green")
        table.add_column("Guild ID")
        table.add_column("Channel ID")

    # Sort logic: --sort takes precedence; --timeline is a shortcut for date
    _sort = getattr(args, "sort", "size")
    if args.timeline and _sort == "size":
        _sort = "date"
    if _sort == "date":
        sorted_entries = sorted(media_entries, key=lambda x: x.mtime, reverse=True)
    elif _sort == "type":
        sorted_entries = sorted(media_entries, key=lambda x: x.mime_type)
    elif _sort == "name":
        sorted_entries = sorted(media_entries, key=lambda x: x.path.name)
    else:
        sorted_entries = sorted(media_entries, key=lambda x: x.size, reverse=True)

    for e in sorted_entries:
        row: list[str] = [e.path.name, e.mime_type, fmt_size(e.size)]
        if args.timeline:
            row.append(fmt_timestamp(e.modified))
        if args.all_apps:
            row.append(e.app_source or "-")
        if args.metadata:
            m = e.metadata
            url = (m.url or "")[:50] if m else ""
            guild = m.guild_id or "-" if m else "-"
            channel = m.channel_id or "-" if m else "-"
            row.extend([url, guild, channel])
        table.add_row(*row)

    console.print(table)
    console.print(f"[bold]Media files found:[/bold] {len(media_entries)} of {len(all_entries)} total")
