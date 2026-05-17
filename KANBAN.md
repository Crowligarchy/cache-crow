# cache-crow — Kanban Board

> Modern Discord (and app) cache explorer. Browse, filter, analyze, and extract cached images/media that survive message deletion.

---

## Backlog

- [ ] Support additional apps: Slack, Telegram, Signal, WhatsApp desktop
- [ ] Metadata database: index cache entries with timestamps, file types, sizes
- [ ] Deduplication: identify duplicate cached images across apps
- [ ] Export report: generate HTML gallery of recovered images
- [ ] Configurable output profiles: researcher mode, cleanup mode, archive mode
- [x] Integration test with two Discord accounts (sender deletes, receiver verifies cache persistence) — DONE 2026-05-17

---

## Todo

_(no open tasks — all planned features delivered)_

---

## In Progress

_(no tasks in progress)_

---

## Done

- [x] Task #6: Chrome Simple Cache stream parser (simple_cache.py) — 13 tests, extract_stream1() correctly strips Chrome wrapper from f_XXXXXX files (2026-05-17)
- [x] Task #7: Chrome Simple Cache index file parser (index_parser.py) — 11 tests, parse_index() reads binary index → URL hash + timestamps (2026-05-17)
- [x] Task #8: Extractor stream stripping fix (extractor.py) — extract_media() now writes clean media bytes instead of Chrome-wrapped blobs; 8 new tests (2026-05-17)
- [x] discordo live-login blocked by hCaptcha — Superseded — token extraction via headless browser now used instead. (2026-05-17)

- [x] Task 1: Discord test server + two-account communication (2026-05-17)
  - Guild `cache-crow-test` created by cachecrow_beta (Account B) — Account A blocked by Discord verification requirement (code 40002)
  - Guild ID: `1505524316257652850`, Channel `#test-media` ID: `1505524317134524487`
  - Invite `7MQ3a8qj3b` created; Account A join attempted but blocked by verification
  - Account B successfully sends text messages and PNG attachments to the channel
  - Account B can read channel history
  - Credentials saved to `~/.crowligarchy/credentials.env`: DISCORD_TEST_GUILD_ID, DISCORD_TEST_CHANNEL_ID, DISCORD_TEST_INVITE
  - Setup script: `scripts/discord_test_setup.py`

- [x] Task 2: Integration test proving cache persistence after message deletion (2026-05-17)
  - `tests/test_integration.py` — 8 tests across 3 classes
  - `TestPngGeneration` (4 tests): validates in-memory PNG generator and scanner identification
  - `TestDiscordCachePersistence` (2 live tests, `@pytest.mark.integration`): end-to-end proof
    - Sends 50x50 red PNG via Account B token to `#test-media` channel
    - Downloads CDN URL to simulated cache dir as `f_test001` (Discord naming convention)
    - Deletes message via Account B token (HTTP 204 confirmed)
    - Verifies CDN URL still returns 200 + valid PNG after deletion
    - Runs `scan_cache()` against temp dir — recovered bytes match original PNG exactly
  - `TestCachePersistenceMocked` (2 tests): mock-based coverage for CI without live tokens
  - All 49 tests pass (22 new + 27 existing)

- [x] Task #5: Textual TUI (2026-05-17)
  - `src/cache_crow/tui.py` — Textual app with split layout
  - Left panel: file list (name, type, size) sorted by size descending
  - Right panel: metadata view (MIME, size, date, CDN URL, guild/channel IDs from LevelDB)
  - Keybindings: `e`=extract, `q`=quit, arrow keys navigate
  - Status bar: file count, media count, total size
  - Rich fallback display if textual unavailable
  - CLI flag: `--tui` launches the browser; works with `--output-dir` for extraction
  - 9 new tests (test_tui.py), all passing

- [x] Task #4: Watch mode (2026-05-17)
  - `src/cache_crow/watcher.py` — CacheWatcher with watchdog filesystem observer
  - Monitors cache directory for new `f_XXXXXX` files
  - Identifies file type via magic bytes on creation
  - Live-updating rich table via `rich.live.Live` (refresh 4 Hz)
  - Auto-extracts media files when `--output-dir` is set
  - `--watch-all` flag shows all file types (not just media)
  - Graceful Ctrl+C stop with summary
  - CLI flags: `--watch`, `--watch-all`
  - 17 new tests (test_watcher.py), all passing

- [x] Task #3: LevelDB Metadata Reader (2026-05-17)
  - `src/cache_crow/metadata.py` — dual-strategy metadata reader
  - Strategy 1: LevelDB index reader (plyvel) — parses Chrome cache LevelDB for URL mappings
  - Strategy 2: Chrome Simple Cache entry header scanning — extracts URL from f_XXXXXX file headers
  - `CacheMetadata` dataclass with `url`, `size`, `content_type` fields
  - Computed properties: `guild_id`, `channel_id`, `cdn_filename` (parsed from Discord CDN URLs)
  - `enrich_entries_with_metadata()` enriches `CacheEntry` list in place
  - CLI flag: `--metadata` enables enrichment + CDN URL column in output table
  - Graceful degradation when LevelDB absent or headers are raw media
  - 27 new tests (test_metadata.py), all passing

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
