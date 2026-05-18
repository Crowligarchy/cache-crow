# r/discordapp submission

**Best time to post:** Tuesday–Thursday, 10am–1pm EST (peak subreddit activity)

---

**Title:**

I made a CLI tool that recovers media from your local Discord cache — including images from deleted messages

---

**Body:**

Every image, GIF, and video you view in Discord gets written to your local disk as a binary blob by Chromium's network cache. The files have no extension, no descriptive name — just entries like `f_000001`. When a message gets deleted, Discord can't reach into your filesystem and remove those blobs. They stay there until Chromium's eviction cycle gets around to them, which can be days or weeks.

I wrote **cache-crow** to surface those files: it reads the Chrome Simple Cache format, identifies each file by its magic bytes (not filename), strips the cache wrapper, and hands you clean, properly-named files with the right extensions.

**Install:**

```bash
pipx install cache-crow
```

Or grab the latest from source:

```bash
pipx install git+https://github.com/Crowligarchy/cache-crow
```

**Basic usage:**

```bash
# See what's in your cache
cache-crow

# Stats summary
cache-crow --stats

# Extract everything >= 1KB into ./recovered/
cache-crow --output-dir ./recovered

# Recover the original CDN URL for each file (guild/channel/filename)
cache-crow --metadata

# Watch mode: capture new cache files in real time as you browse
cache-crow --watch --output-dir ./live-capture

# Interactive TUI browser
cache-crow --tui
```

**Example output:**

```
$ cache-crow --stats

           Cache Stats
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric              ┃   Value ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Total files scanned │      39 │
│ Media files found   │      23 │
│ Total media size    │ 92.0 KB │
└─────────────────────┴─────────┘

  Breakdown by Type
┏━━━━━━━━━━━━┳━━━━━━━┓
┃ Type       ┃ Count ┃
┡━━━━━━━━━━━━╇━━━━━━━┩
│ image/png  │     8 │
│ image/jpeg │     5 │
│ image/webp │     4 │
│ image/gif  │     3 │
│ video/mp4  │     2 │
│ video/webm │     1 │
└────────────┴───────┘
```

**Highlights:**

- **Watch mode** (`--watch`): runs continuously and extracts media as it enters your cache — useful if you want to capture something the moment it loads
- **CDN URL recovery** (`--metadata`): extracts the original `cdn.discordapp.com` URL from the cache entry header. Even after a message is deleted, that CDN URL is often still live and servable
- **TUI browser** (`--tui`): interactive terminal UI (powered by Textual) for browsing found files without running extraction
- **JSON output**: `--format json` makes it scriptable — pipe to `jq`, feed into another tool, whatever
- Works on Discord Canary, PTB, Slack, and Chrome/Brave too — not just the main Discord client

This is a local-only tool. No network requests, no accounts, no third-party services. It reads files your OS user already has permission to read.

Linux, macOS, and Windows are all supported.

GitHub: https://github.com/Crowligarchy/cache-crow

Happy to answer questions about how the Chrome Simple Cache format works or why the CDN persistence happens.
