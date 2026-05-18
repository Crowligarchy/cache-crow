# Twitter/X thread — launch

**Best time to post:** Tuesday or Wednesday, 9am–11am EST
**Format:** Reply-chain thread. Post tweet 1, then reply to it with tweets 2–5 in sequence.

---

**Tweet 1 (hook):**

Every image you view in Discord is saved to your disk with no extension, no name, and no automatic cleanup when messages get deleted.

I built a tool that finds those files, identifies them by magic bytes, and gives them back to you.

cache-crow -- open source, local-only, no network access

https://github.com/Crowligarchy/cache-crow

---

**Tweet 2 (the technical finding):**

2/ Discord runs on Chromium (Electron). Chromium's HTTP disk cache stores every media file you view as a binary blob named something like `f_000001`.

When a message is deleted, Discord can't reach into your filesystem. That file stays until Chromium's eviction cycle — sometimes weeks later.

The Chrome Simple Cache format embeds the original CDN URL in each entry header. After deletion, that URL often still works.

---

**Tweet 3 (what the tool does):**

3/ cache-crow parses the Simple Cache binary format, reads magic bytes to identify file types (no extensions to trust), and extracts clean media files.

```bash
pipx install cache-crow

cache-crow --stats          # what's on your disk
cache-crow --output-dir ./recovered   # extract it
cache-crow --metadata       # recover original CDN URLs
cache-crow --watch          # capture new files in real time
cache-crow --tui            # interactive browser
```

JSON output: `cache-crow --format json | jq '.'`

---

**Tweet 4 (privacy angle + scope):**

4/ This is not a Discord-specific issue.

Every Electron app shares the same Chromium cache behavior: Slack, VS Code, Teams, Signal Desktop, Telegram Desktop.

cache-crow supports Discord (stable/canary/PTB) and Slack today. Telegram and Signal are on the roadmap.

Linux, macOS, and Windows. MIT licensed.

---

**Tweet 5 (CTA):**

5/ If you want to understand what your Electron apps are storing about you, or you work in DFIR and need a scriptable cache parser, check it out.

Stars, issues, and PRs welcome -- especially for additional Electron app paths, magic byte signatures (AVIF, HEIC), and Windows testing.

https://github.com/Crowligarchy/cache-crow

#Python #OpenSource #Privacy #InfoSec #Discord

---

**Hashtag notes:**
- Use all five hashtags only on tweet 5 (the CTA). Hashtags on earlier tweets reduce reach on X.
- If engagement is low in the first hour, quote-tweet tweet 1 with a screenshot of the `--stats` output to add visual interest.
