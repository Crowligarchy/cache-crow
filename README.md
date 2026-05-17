# cache-crow

> Recover deleted Discord media from local Electron cache.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Crowligarchy/cache-crow?style=social)](https://github.com/Crowligarchy/cache-crow/stargazers)

Discord caches every image, GIF, and video you view — on your local disk, as raw
binary blobs, with no extensions. **When someone deletes a message, the media file
stays on disk.** This is not a bug — it is how every Chromium-based app works. The
cache persists for days or weeks after deletion, long enough to matter in DFIR
investigations, privacy audits, and personal recovery.

cache-crow finds those files, identifies them by magic bytes, and extracts them with
the correct extension. No accounts. No network access. No guesswork.

Works on Linux, macOS, and Windows. Targets Discord and Slack today, more apps coming.

---

## Quick demo

```
$ cache-crow --cache-dir ~/.config/discord/Cache/Cache_Data --stats

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
$ cache-crow --cache-dir ~/.config/discord/Cache/Cache_Data

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

## Install

```bash
# recommended — isolated install, no venv required
pipx install git+https://github.com/Crowligarchy/cache-crow

# or with pip into your environment
pip install git+https://github.com/Crowligarchy/cache-crow

# PyPI (publishing in progress — use the git URL above for now)
# pip install cache-crow
```

---

## Usage

```bash
# scan your Discord cache, show a table of all found media
cache-crow

# stats-only mode: just counts and sizes, no file table
cache-crow --stats

# extract everything >=1KB into ./recovered with correct extensions
cache-crow --output-dir ./recovered

# target Slack instead of Discord
cache-crow --app slack

# point at a specific cache directory (useful for forensics of another user's profile)
cache-crow --cache-dir /path/to/Cache_Data

# combine flags
cache-crow --app discord --output-dir ./out --stats
```

```bash
cache-crow --watch        # live monitoring mode: alert when new files appear
cache-crow --tui          # interactive TUI browser (textual-based)
```

---

## How it works

Discord is an Electron app built on Chromium. Chromium's network stack maintains a
disk cache for HTTP responses — images, videos, and other media fetched from Discord's
CDN land in this cache as opaque binary blobs. On Linux, the cache lives at:

```
~/.config/discord/Cache/Cache_Data/
```

On macOS it's `~/Library/Application Support/discord/Cache/Cache_Data/`. On Windows,
`%APPDATA%\discord\Cache\Cache_Data\`.

Files in `Cache_Data` have names like `f_000001`, `f_00a3f2` — no extensions, no
metadata in the filename. The file format is Chromium's "Simple Cache" format: a
small header, then the raw HTTP response body.

cache-crow reads each file's first 12 bytes and checks for magic byte signatures:

| Magic bytes              | Format    |
|--------------------------|-----------|
| `\x89PNG`                | PNG       |
| `\xFF\xD8\xFF`           | JPEG      |
| `GIF8` or `GIF9`         | GIF       |
| `RIFF....WEBP`           | WebP      |
| `....ftyp` (offset 4)    | MP4       |
| `\x1A\x45\xDF\xA3`       | WebM/MKV  |

No extension guessing, no MIME sniffing from headers — just the bytes themselves.

When Discord fetches a CDN URL (e.g. `https://cdn.discordapp.com/attachments/...`),
Chromium writes that response to the cache. If the sender then deletes the message,
Discord removes the message from its servers and tells clients to redact it from their
UI. What Discord does **not** do is clear the local Chromium cache. The file sits on
disk until Chromium's cache eviction decides to remove it — which can be days or weeks.

This is not a Discord bug. This is how every Chromium-based app works. It's documented
behavior that happens to have significant forensics and privacy implications.

---

## Supported apps

| App      | Cache path (Linux)                              | Status |
|----------|-------------------------------------------------|--------|
| Discord  | `~/.config/discord/Cache/Cache_Data`            | Stable |
| Discord Canary | `~/.config/discordcanary/Cache/Cache_Data` | Stable |
| Discord PTB | `~/.config/discordptb/Cache/Cache_Data`      | Stable |
| Slack    | `~/.config/Slack/Cache/Cache_Data`              | Stable |

On the roadmap: Telegram Desktop, Signal Desktop, Microsoft Teams (Electron builds).
PRs welcome.

---

## Cache persistence

This is the part most people find surprising.

**Deleting a message does not clear the cache.** When you delete a message in Discord,
the server-side record is removed and other clients receive a delete event. But
Chromium's disk cache on each recipient's machine is not notified — it has no mechanism
for that. The cached file persists.

**Clearing Discord's cache in settings does not always work.** Discord's built-in
cache clear goes through the Electron API, which clears HTTP cache for *new* responses.
Files that were written before the clear are sometimes evicted, sometimes not — it
depends on Chromium's internal eviction order.

**Uninstalling Discord does not remove the cache.** On most systems, `~/.config/discord`
is not touched by the uninstaller. You can verify this yourself: install Discord,
view some images, uninstall, and the `Cache_Data` directory is still there.

**Discord's CDN keeps content alive too.** CDN URLs remain valid for roughly one week
after the originating attachment is deleted. The local cache may actually outlast the
server-side content.

The bottom line: cached media should be considered a persistent artifact of any
Discord session. Security researchers, DFIR practitioners, and anyone with access to
a machine can recover it with a simple directory scan.

---

## Compared to existing tools

Most Discord cache tools were written in 2019-2022, target Windows only, and require
a GUI. cache-crow is different:

| Feature              | cache-crow | Most alternatives |
|----------------------|------------|-------------------|
| Cross-platform       | Yes        | Windows-only      |
| CLI / scriptable     | Yes        | GUI-only          |
| Pipe-friendly output | Yes        | No                |
| Active maintenance   | Yes        | Abandoned 2019-22 |
| Magic-byte detection | Yes        | Extension rename  |
| Multiple apps        | Yes        | Discord-only      |
| Minimal deps (rich)  | Yes        | Varies            |
| TUI browser          | Yes        | No                |
| LevelDB metadata     | Yes (opt-in) | No              |

---

## Security and privacy

cache-crow is a forensics and privacy research tool. It is designed to analyze **your
own machine's cache** — the same files your OS user account already has read access to.

Intended use cases:

- **DFIR / incident response**: recover evidence from a compromised host
- **Privacy audit**: understand what your apps are storing about you
- **Security research**: study Electron app caching behavior
- **Personal recovery**: retrieve something you viewed but forgot to save

This tool does not access any network resources. It does not authenticate with Discord.
It reads only local files that your user account already has permission to read.

If you use this tool to access another person's device without authorization, that is
a legal matter between you and them. The authors take no responsibility for misuse.

---

## Contributing

Issues and PRs are welcome.

```bash
git clone https://github.com/Crowligarchy/cache-crow
cd cache-crow
pip install -e ".[dev]"
pytest
```

Areas where contributions help most:
- New app cache paths (macOS / Windows paths, more Electron apps)
- Additional magic byte signatures
- LevelDB metadata reader (cross-reference blobs to CDN URLs)
- Watch mode implementation
- TUI browser

---

## License

MIT. See [LICENSE](LICENSE).
