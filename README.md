# cache-crow

> Every image you view in Discord is cached to your local disk — with no extension,
> no expiry, and no automatic cleanup when messages are deleted. cache-crow reads
> those binary blobs, identifies them by magic bytes, and gives them back to you.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/Crowligarchy/cache-crow/tests.yml?label=tests)](https://github.com/Crowligarchy/cache-crow/actions)
[![GitHub stars](https://img.shields.io/github/stars/Crowligarchy/cache-crow?style=social)](https://github.com/Crowligarchy/cache-crow/stargazers)

Works on **Linux, macOS, and Windows**. Targets **Discord and Slack** today; more apps in the roadmap.

---

## What it does

Discord is an Electron app built on Chromium. Chromium's network stack maintains a local
HTTP cache for performance — every image, GIF, and video you view gets written to disk as a
binary blob with no extension, named something like `f_000001` or `f_00a3f2`.

When someone deletes a message, Discord removes the server-side record and tells your
client to hide it. What it cannot do is reach into your local filesystem and delete the
cached copy. **That file stays on disk** — sometimes for days or weeks, depending on
Chromium's cache eviction schedule.

cache-crow exploits this:

1. Scans `Cache_Data/` for files matching known media magic bytes
2. Identifies each file's format with zero guesswork (PNG, JPEG, GIF, WebP, MP4, WebM)
3. Extracts them with the correct extension, stripping the Chrome Simple Cache wrapper
4. Optionally recovers the original CDN URL from embedded cache entry headers

No accounts. No network access. No third-party servers. Reads only files your OS user
account already has permission to read.

---

## Install

```bash
# Recommended — installs the `cache-crow` command globally, isolated from your system Python
pipx install git+https://github.com/Crowligarchy/cache-crow

# With plain pip (ensure ~/.local/bin is in your PATH — see note below)
pip install --user git+https://github.com/Crowligarchy/cache-crow

# PyPI (coming soon — use the git URL above for now)
# pip install cache-crow
```

> **PATH note for pip users**: pip installs scripts to `~/.local/bin` on Linux/macOS.
> If `cache-crow` is not found after install, add this to your shell profile:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```
> Then open a new terminal or run `source ~/.bashrc` (or `~/.zshrc`). **`pipx` handles
> this automatically** — it is the recommended install method.

### Optional extras

```bash
# Interactive TUI browser (powered by Textual)
pip install 'cache-crow[tui]'

# LevelDB index reader — recover CDN URLs from the cache index
pip install 'cache-crow[leveldb]'

# Everything
pip install 'cache-crow[all]'
```

### Verify installation

```bash
cache-crow --version
# cache-crow 0.1.0
```

---

## Quick start

```bash
# Scan your Discord cache, show a table of all found media
cache-crow

# Stats only: counts and sizes, no file listing
cache-crow --stats

# Extract everything >=1 KB into ./recovered/ with correct extensions
cache-crow --output-dir ./recovered

# Target Slack instead of Discord
cache-crow --app slack

# Point at a specific directory (forensics, another user's profile)
cache-crow --cache-dir /path/to/Cache_Data

# Machine-readable JSON — pipe into jq, scripts, whatever
cache-crow --format json | jq '.[] | select(.mime_type == "video/mp4")'

# Live monitoring: show new cache files as they arrive
cache-crow --watch --output-dir ./live-capture

# Interactive TUI browser
cache-crow --tui
```

---

## Demo

```
$ cache-crow --stats

           Cache Stats
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric              ┃   Value ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Total files scanned │      39 │
├─────────────────────┼─────────┤
│ Media files found   │      23 │
├─────────────────────┼─────────┤
│ Total media size    │ 92.0 KB │
└─────────────────────┴─────────┘
  Breakdown by Type
┏━━━━━━━━━━━━┳━━━━━━━┓
┃ Type       ┃ Count ┃
┡━━━━━━━━━━━━╇━━━━━━━┩
│ image/png  │     8 │
├────────────┼───────┤
│ image/jpeg │     5 │
├────────────┼───────┤
│ image/webp │     4 │
├────────────┼───────┤
│ image/gif  │     3 │
├────────────┼───────┤
│ video/mp4  │     2 │
├────────────┼───────┤
│ video/webm │     1 │
└────────────┴───────┘
```

```
$ cache-crow

      Media in discord cache
┏━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Filename ┃ Type       ┃    Size ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━┩
│ f_000001 │ image/png  │ 11.4 KB │
│ f_000006 │ image/png  │ 11.4 KB │
│ f_000009 │ image/jpeg │   120 B │
│ f_000023 │ video/webm │   104 B │
│ f_000017 │ image/webp │    45 B │
│ f_000014 │ image/gif  │    42 B │
│ f_000021 │ video/mp4  │    40 B │
│ ...      │ ...        │     ... │
└──────────┴────────────┴─────────┘
Media files found: 23 of 39 total
```

```
$ cache-crow --output-dir ./recovered

Extracting from: /home/user/.config/discord/Cache/Cache_Data
   Extraction Results
┏━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric        ┃ Value ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total scanned │    39 │
├───────────────┼───────┤
│ Extracted     │     8 │
├───────────────┼───────┤
│ Skipped       │    31 │
└───────────────┴───────┘

Output: ./recovered
```

---

## Full usage reference

```
usage: cache-crow [-h] [--version] [--app APP] [--cache-dir PATH]
                  [--output-dir PATH] [--min-size BYTES] [--stats]
                  [--format FORMAT] [--metadata] [--watch] [--watch-all] [--tui]

options:
  --version          Show version and exit
  --app APP          Target app: discord (default) or slack
  --cache-dir PATH   Override the cache directory (skips auto-detection)
  --output-dir PATH  Extract found media files into PATH with correct extensions
  --min-size BYTES   Minimum file size to extract, in bytes (default: 1024)
  --stats            Summary stats only (counts and sizes, no file listing)
  --format FORMAT    Output format: table (default) or json
  --metadata         Enrich entries with CDN URLs and guild/channel IDs
  --watch            Watch for new cache files in real time (Ctrl+C to stop)
  --watch-all        In watch mode, show all files, not just media
  --tui              Interactive TUI browser (requires cache-crow[tui])
```

---

## How it works

### Chrome Simple Cache format

Discord's Chromium cache uses the "Simple Cache" format. Each entry is a single file:

```
[24-byte header][URL key][response body][EOF record][response headers][EOF record]
```

The header contains the original CDN URL as a UTF-8 key. The response body is the
actual media content. cache-crow parses this structure to extract the raw bytes —
not just copy the raw file — so extracted media is clean and playable.

### Magic byte detection

Rather than trusting filenames or extensions (there are none), cache-crow reads the
first bytes of each file and matches against known signatures:

| Magic bytes              | Format    |
|--------------------------|-----------|
| `\x89PNG`                | PNG       |
| `\xFF\xD8\xFF`           | JPEG      |
| `GIF8` or `GIF9`         | GIF       |
| `RIFF....WEBP`           | WebP      |
| `....ftyp` (offset 4)    | MP4       |
| `\x1A\x45\xDF\xA3`       | WebM/MKV  |

### CDN URL recovery

With `--metadata`, cache-crow also reads the URL key embedded in each cache entry
header. For Discord attachments, the URL encodes the guild ID, channel ID, and
original filename:

```
https://cdn.discordapp.com/attachments/{guild_id}/{channel_id}/{filename}
```

This lets you trace a cached file back to the Discord channel and server where it
was originally shared.

---

## Cache persistence: the facts

**Deleting a message does not clear the cache.**
When you delete a Discord message, the server-side record is removed. Other clients
receive a delete event. But Chromium's disk cache on each viewer's machine has no
mechanism to receive deletion signals — it simply retains the file until its normal
eviction cycle.

**Discord's "clear cache" setting is unreliable.**
Discord's built-in cache clear goes through the Electron API. Files written before
the clear are sometimes evicted, sometimes not — it depends on Chromium's internal
eviction order, not a guaranteed delete.

**Uninstalling Discord does not remove the cache.**
On most systems, `~/.config/discord` is not touched by the uninstaller. The `Cache_Data`
directory survives uninstall.

**This is not a Discord bug.**
This is documented Chromium behavior shared by every Electron app: Discord, Slack,
VS Code, Teams, Signal Desktop, Telegram Desktop. The local disk cache is a
performance feature, not a privacy control.

---

## Supported apps

| App            | Linux                                            | Status |
|----------------|--------------------------------------------------|--------|
| Discord        | `~/.config/discord/Cache/Cache_Data`             | Stable |
| Discord Canary | `~/.config/discordcanary/Cache/Cache_Data`       | Stable |
| Discord PTB    | `~/.config/discordptb/Cache/Cache_Data`          | Stable |
| Slack          | `~/.config/Slack/Cache/Cache_Data`               | Stable |

macOS and Windows paths are also auto-detected — see `cache-crow --help` for the full
list.

Roadmap: Telegram Desktop, Signal Desktop, VS Code, Microsoft Teams. PRs welcome.

---

## Compared to existing tools

Most Discord cache tools were written in 2019-2022, target Windows only, and require
a GUI. cache-crow is different:

| Feature                  | cache-crow      | Most alternatives |
|--------------------------|-----------------|-------------------|
| Cross-platform           | Yes             | Windows-only      |
| CLI / scriptable         | Yes             | GUI-only          |
| JSON output / pipe-friendly | Yes          | No                |
| Chrome Simple Cache parsing | Yes (stream1) | Raw file copy     |
| Magic-byte detection     | Yes             | Extension rename  |
| Multiple apps            | Yes             | Discord-only      |
| Minimal deps (rich only) | Yes             | Varies            |
| Live watch mode          | Yes             | No                |
| TUI browser              | Yes             | No                |
| CDN URL recovery         | Yes             | No                |
| Active maintenance       | 2025            | Abandoned 2019-22 |

---

## Security and privacy

cache-crow is a forensics and privacy research tool. It reads only files on your
local filesystem that your OS user account already has permission to read. It makes
no network requests.

**Intended use cases:**

- **DFIR / incident response** — recover evidence from a compromised or seized host
- **Privacy audit** — understand what your Electron apps are storing about you
- **Security research** — study Chromium's disk cache format and behavior
- **Personal recovery** — retrieve something you viewed but forgot to save

If you use this tool to access a device you do not own or have explicit permission to
examine, that is a legal matter between you and your jurisdiction's computer misuse
laws. The authors take no responsibility for misuse.

---

## Contributing

Issues and PRs are welcome.

```bash
git clone https://github.com/Crowligarchy/cache-crow
cd cache-crow
pip install -e ".[dev]"
pytest
```

Where contributions help most:
- Additional app cache paths (macOS/Windows variants, more Electron apps)
- Additional magic byte signatures (SVG, AVIF, AV1, HEIC)
- LevelDB index cross-referencing improvements
- Windows testing and CI
- Demo GIF / screenshot for the README

---

## License

MIT. See [LICENSE](LICENSE).
