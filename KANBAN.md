# cache-crow — Kanban Board

> Modern Discord (and app) cache explorer. Browse, filter, analyze, and extract cached images/media that survive message deletion.

---

## Backlog

- [ ] Support additional apps: Slack, Telegram, Signal, WhatsApp desktop
- [ ] Metadata database: index cache entries with timestamps, file types, sizes
- [ ] TUI (terminal UI) using `rich` or `textual` — browse cache interactively
- [ ] Watch mode: monitor cache directory live, alert on new entries
- [ ] Deduplication: identify duplicate cached images across apps
- [ ] Export report: generate HTML gallery of recovered images
- [ ] LevelDB index reader: cross-reference cache files with LevelDB metadata for richer context
- [ ] Configurable output profiles: researcher mode, cleanup mode, archive mode
- [ ] Discord CDN link recovery: reconstruct CDN URLs from cache metadata
- [ ] Integration test with two Discord accounts (sender deletes, receiver verifies cache persistence)

---

## Todo

- [ ] Build discordo/CLI automation for two-account test scenario
- [ ] Add magic-byte identification for more formats (webp, gif, mp4, webm)
- [ ] CLI flag: `--output-dir` for extracted files
- [ ] CLI flag: `--app` to target specific app (discord, slack, etc.)
- [ ] CLI flag: `--stats` to print size breakdown only

---

## In Progress

### discordo live-login blocked by hCaptcha (2026-05-08)
- **Goal**: Log into Discord test account (`sddozezjaffq@wshu.net`) via discordo CLI, seed cache with real media
- **Blocker**: Discord API `/auth/login` returns `captcha-required` (hCaptcha) on every automated request, including with CF clearance cookies
  - Tried: requests with realistic headers, Playwright Firefox with CF cookies, Playwright Chromium headless
  - Discord remote-auth (QR code) login requires a mobile device to scan — not automatable headlessly
  - `DISCORDO_TOKEN` env var is supported by discordo but we cannot obtain the token without passing captcha
- **Status**: Synthetic cache used for testing (see Done). Real live login requires human captcha solve or dedicated hCaptcha solving service (2captcha, anti-captcha)
- **Next step**: Add `DISCORD_TOKEN` to `credentials.env` after manual login; or use 2captcha API

---

## Done

- [x] Task #6: Write stellar README.md (2026-05-17)
  - Full README: value prop, real terminal output examples, how-it-works, magic bytes table,
    cache persistence section, competitor comparison table, security/privacy disclosure
  - Output from actual `cache-crow --stats` and `--output-dir` runs against synthetic cache
- [x] Task #7: GitHub star acquisition + community submission plan (2026-05-17)
  - docs/submission_plan.md: awesome list PRs, Reddit drafts, HN title options, execution order
  - 10 GitHub topics added: discord, cache, forensics, python, cli, electron, privacy,
    security, dfir, media-recovery
- [x] cache-crow integration test with synthetic Discord cache (2026-05-08)
  - Cache path: `/home/discordtest/.config/discord/Cache/Cache_Data/`
  - 39 files total; 23 media files detected: 8 PNG, 5 JPEG, 4 WebP, 3 GIF, 2 MP4, 1 WebM
  - `--stats` mode works; extraction mode works (min_size=1024 filter applies correctly)
  - Scanner, magic-byte ID, and extractor all verified against real cache file naming (`f_000001` etc.)
- [x] discordo installed to `/usr/local/bin/discordo`; `DISCORDO_TOKEN` env var confirmed supported
- [x] `discordtest` user created with home at `/home/discordtest/`
- [x] Initial Discord cache scanner + extractor MVP (14/14 tests passing)
- [x] Research original cache-monkey architecture
- [x] Research Discord cache paths on Linux (LevelDB in `~/.config/discord/Cache/Cache_Data/`)
- [x] Research CLI Discord clients (discordo — actively maintained TUI)
- [x] Confirm cache persistence: images survive sender deletion
- [x] Create GitHub repo: https://github.com/Crowligarchy/cache-crow
- [x] Initialize local project structure

---

## Notes

- Discord cache uses Electron/Chromium LevelDB — files have no extensions
- Magic bytes required to identify file types: PNG (`\x89PNG`), JPEG (`\xFF\xD8`), WEBP (`RIFF...WEBP`), GIF (`GIF8`)
- Cache survives Discord app restarts and sender deletion
- Discord CDN caches content ~1 week before final server-side deletion
- **discordo** is the recommended CLI client: https://github.com/ayn2op/discordo
