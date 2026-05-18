# r/privacy submission

**Best time to post:** Monday or Wednesday, 9am–12pm EST (privacy subs are active early week)

---

**Title:**

Discord (and Slack) cache every image you view to your local disk — here's a tool to see exactly what's stored and clean it up

---

**Body:**

Discord is an Electron app. Under the hood, it runs Chromium, and Chromium's HTTP cache is always on. Every image, GIF, and video you view in Discord gets written to your disk at:

- Linux: `~/.config/discord/Cache/Cache_Data/`
- macOS: `~/Library/Application Support/discord/Cache/Cache_Data/`
- Windows: `%APPDATA%\discord\Cache\Cache_Data\`

The files are stored as binary blobs with no extension and no human-readable name — entries like `f_000001`, `f_00a3f2`. Chromium decides when to evict them, not Discord. **Deleting a message does not remove the cached copy from a viewer's machine.** Discord's built-in "clear cache" option is also unreliable — it goes through Electron's API rather than deleting files directly, and results vary.

Uninstalling Discord typically does not remove `~/.config/discord` either, so the cache survives uninstall on most systems.

This is not a Discord-specific bug — it is documented Chromium behavior shared by every Electron app: Discord, Slack, VS Code, Teams, Signal Desktop, Telegram Desktop.

---

**I wrote cache-crow to make this visible and manageable.**

https://github.com/Crowligarchy/cache-crow

It scans your local cache directory, identifies media files by their magic bytes (since there are no extensions to trust), and shows you exactly what is sitting on your disk. You can extract the files, get stats, or just audit what is there.

**Install:**

```bash
pipx install cache-crow
```

**See what's in your Discord cache:**

```bash
cache-crow --stats
```

```
           Cache Stats
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric              ┃   Value ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Total files scanned │      39 │
│ Media files found   │      23 │
│ Total media size    │ 92.0 KB │
└─────────────────────┴─────────┘
```

**See all cached media with types:**

```bash
cache-crow
```

**Recover original CDN URLs (traces a file back to the guild and channel it came from):**

```bash
cache-crow --metadata
```

**Extract files with correct extensions so you can view them:**

```bash
cache-crow --output-dir ./audit-output
```

**Target Slack instead of Discord:**

```bash
cache-crow --app slack
```

---

**What this means for you practically:**

- Images shared in any Discord server or DM you have viewed are on your disk, potentially for weeks, regardless of whether the message was deleted
- The original CDN URL embedded in each cache entry is often still live after deletion — the image may still be publicly accessible via its direct link
- Discord's "clear cache" in Settings > App Settings does not guarantee removal
- If you share a computer, other users with filesystem access to your home directory can read these files

**What you can do:**

- Run `cache-crow --stats` periodically to understand what is cached
- Run `cache-crow --output-dir ./audit/` to inspect the actual files
- To actually clear the cache reliably, quit Discord and delete the `Cache_Data/` directory manually, then restart Discord

The tool is local-only: no network requests, no external services, reads only files your OS user already has permission to access. MIT licensed.

Roadmap includes support for Telegram Desktop, Signal Desktop, VS Code, and Teams.

GitHub: https://github.com/Crowligarchy/cache-crow
