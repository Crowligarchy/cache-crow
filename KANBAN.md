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

- [ ] Initial Discord cache scanner + extractor MVP

---

## Done

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
