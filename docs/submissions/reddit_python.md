# r/Python submission (Show r/Python)

**Best time to post:** Tuesday or Thursday, 8am–11am EST (Show r/Python posts get traction early in the week, early in the day before the feed fills up)

---

**Title:**

Show r/Python: cache-crow — a CLI tool that parses Discord's Chrome Simple Cache binary format and recovers media by magic byte detection

---

**Body:**

**cache-crow** — https://github.com/Crowligarchy/cache-crow

Discord is an Electron app, which means it uses Chromium's HTTP disk cache to store every image, GIF, and video you view. The files are written to `~/.config/discord/Cache/Cache_Data/` with no extension and no human-readable name. I built cache-crow to parse those blobs and recover the underlying media files.

---

**The Chrome Simple Cache format**

Chromium uses a format called "Simple Cache." Each cached response is stored as a single file with this structure:

```
[24-byte header][URL key (UTF-8)][response body][EOF record][response headers][EOF record]
```

The 24-byte header contains a magic number, a key hash, and a key length field. After that comes the original request URL (the CDN URL Discord fetched), then the raw response body, then a trailing EOF record and the response headers.

Most existing Discord cache tools skip this entirely and just copy the raw file as-is. That works sometimes (Chromium's Simple Cache often doesn't wrap the content tightly), but the result is a file with leading binary garbage that some viewers reject. cache-crow actually parses the header, reads the key length, advances past the URL key, and extracts clean bytes starting from the response body offset.

---

**Magic byte detection**

There are no filenames or extensions to trust, so identification is done by inspecting the first bytes of the response body:

```python
MAGIC_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n",              0, "image/png",  ".png"),
    (b"\xff\xd8\xff",                   0, "image/jpeg", ".jpg"),
    (b"GIF87a",                         0, "image/gif",  ".gif"),
    (b"GIF89a",                         0, "image/gif",  ".gif"),
    (b"RIFF",                           0, "image/webp", ".webp"),  # + WEBP at offset 8
    (b"\x1a\x45\xdf\xa3",              0, "video/webm", ".webm"),
    (b"ftyp",                           4, "video/mp4",  ".mp4"),   # offset 4
]

def detect_mime(data: bytes) -> tuple[str, str] | None:
    for magic, offset, mime, ext in MAGIC_SIGNATURES:
        if data[offset:offset + len(magic)] == magic:
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime, ext
    return None
```

The MP4 case is worth noting — the `ftyp` box appears at byte offset 4, not offset 0, because the first 4 bytes are a 32-bit big-endian box size field. WebP requires a double check: the file starts with `RIFF` (shared with WAV), so we also verify `WEBP` at offset 8.

---

**CDN URL recovery**

With `--metadata`, cache-crow reads the URL key from the Simple Cache entry header. For Discord attachments this is always:

```
https://cdn.discordapp.com/attachments/{guild_id}/{channel_id}/{filename}
```

This lets you trace a cached file back to the exact guild and channel. It also means that even after a message is deleted, the CDN URL is still embedded in the cached entry — and the CDN often still serves the file at that URL.

---

**API example**

```python
from cache_crow import scan_cache, extract_media

# Scan and get a list of CacheEntry objects
entries = scan_cache(app="discord")

for entry in entries:
    print(entry.filename, entry.mime_type, entry.size, entry.cdn_url)

# Extract to disk with correct extensions
results = extract_media(entries, output_dir="./recovered", min_size=1024)
print(f"Extracted {results.extracted} files")
```

**CLI:**

```bash
pipx install cache-crow

cache-crow                              # table view
cache-crow --stats                      # counts and sizes
cache-crow --output-dir ./recovered     # extract
cache-crow --format json | jq '.'       # JSON output
cache-crow --watch --output-dir ./live  # real-time capture
cache-crow --tui                        # Textual TUI browser
cache-crow --metadata                   # include CDN URLs
```

---

**Design notes**

- Core dependency is only `rich` (for the table/progress output). TUI requires `textual`, LevelDB index reading requires `leveldb` — both are optional extras.
- Tested on Python 3.10, 3.11, 3.12. The magic byte table and Simple Cache parser are the interesting parts; everything else is fairly standard `pathlib` + `struct` work.
- Watch mode uses `watchdog` to monitor the cache directory and runs the extraction pipeline on new files as they arrive.
- JSON output (`--format json`) makes it straightforward to compose with other tools: `cache-crow --format json | jq '.[] | select(.mime_type == "video/mp4")'`

Would love contributions in these areas specifically:
- Additional magic byte signatures (AVIF, HEIC, SVG, AV1)
- LevelDB index cross-referencing to get richer metadata
- macOS/Windows path testing
- Support for more Electron apps (Signal Desktop, Telegram, Teams)

GitHub: https://github.com/Crowligarchy/cache-crow
MIT licensed.
