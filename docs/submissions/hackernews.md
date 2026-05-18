# Hacker News submission

**Best time to post:** Tuesday–Thursday, 7am–9am PST (HN front page is most competitive mid-morning Pacific; early posts have more upvote runway before peak browsing hours)

---

**Title:**

Show HN: cache-crow – recover media from Discord/Slack Chrome Simple Cache by magic bytes

---

**URL:**

https://github.com/Crowligarchy/cache-crow

---

**Text (optional "text" field on Show HN):**

Discord is an Electron app. Its Chromium network stack writes every image, GIF, and video you view to a local "Simple Cache" on disk — binary blobs named `f_000001`, no extension, no automatic cleanup on message deletion.

cache-crow parses the Simple Cache format (24-byte header + URL key + response body + EOF records), identifies media by magic bytes rather than filenames, and extracts clean files with correct extensions.

Two things I found interesting while building this:

1. The Chrome Simple Cache header embeds the original CDN URL as a UTF-8 key. For Discord attachments, that URL encodes the guild ID, channel ID, and original filename. Even after a message is deleted, the CDN often still serves the file at that URL — deletion removes the server-side record but does not invalidate CDN edge caches.

2. Chromium's cache eviction is managed internally by the cache backend, not by the application. Discord can signal a clear through Electron's API, but the result is non-deterministic. Files can persist for days or weeks after a message is deleted.

The tool is local-only — no network access, reads only files the current OS user already has read permission on.

`pipx install cache-crow`

Supports Discord (stable, canary, PTB), Slack, and any Chromium-based app if you point `--cache-dir` at its Cache_Data directory. Roadmap: Signal Desktop, Telegram Desktop, Teams.
