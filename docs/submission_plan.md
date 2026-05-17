# cache-crow: Star Acquisition Plan

Status: ready to execute. Work through sections in order — GitHub topics first
(takes 30 seconds), then awesome list PRs (highest compounding return), then
community posts.

---

## 1. GitHub Topics (do this now)

Run once:

```bash
gh repo edit Crowligarchy/cache-crow \
  --add-topic discord \
  --add-topic cache \
  --add-topic forensics \
  --add-topic python \
  --add-topic cli \
  --add-topic electron \
  --add-topic privacy \
  --add-topic security \
  --add-topic dfir \
  --add-topic media-recovery
```

Topics drive organic discovery from GitHub's Explore page and from
`github.com/topics/discord`, `github.com/topics/forensics`, etc. The `dfir` and
`media-recovery` topics have low competition and targeted audiences who star tools
they actually use.

---

## 2. Awesome List PRs

Submit in this order (highest expected impact first).

### 2a. cugu/awesome-forensics

- **URL**: https://github.com/cugu/awesome-forensics
- **Stars**: ~3.5k, actively maintained, CI validates links
- **Category to target**: "Electron / Browser Artifacts" or "File Analysis"
- **Format**: `[cache-crow](https://github.com/Crowligarchy/cache-crow) - Extracts media from Electron app caches (Discord, Slack) using magic-byte detection. Cross-platform CLI, Python 3.10+.`
- **Submission notes**: CONTRIBUTING.md says one tool per PR, no editorialized
  descriptions. PRs are reviewed — check open PRs for format examples before
  submitting.
- **Status**: Actively maintained. Recent commits in 2024-2025. PRs get merged
  within a few weeks if the tool is relevant.

### 2b. Lissy93/awesome-privacy

- **URL**: https://github.com/Lissy93/awesome-privacy
- **Stars**: ~7k
- **Category**: "Security Tools" or a forensics/analysis sub-section
- **Format**: Data goes in `awesome-privacy.yml` (not README directly). See
  CONTRIBUTING.md. PR title must be "Adds cache-crow to [section-name]".
  Description: 50-250 chars, not promotional.
- **Submission notes**: Requires filling out a PR template. The tool fits under
  "Know what's on your device" / privacy audit tooling angle.

### 2c. vinta/awesome-python

- **URL**: https://github.com/vinta/awesome-python
- **Stars**: ~220k — high visibility but high bar
- **Category**: "Command-line Interface Development" or create a case for a
  "Forensics / Security" section
- **Format**: Alphabetically sorted, `[cache-crow](link) - Description.` one-liner
- **Submission notes**: This list is very selective. Frame cache-crow as a CLI
  tool (which it is) rather than a forensics tool — the CLI section is more active.
  Low probability of acceptance without significant stars first. Submit here after
  the others have added credibility.

### 2d. Digital-Forensics-Discord-Server/MemberProjects

- **URL**: https://github.com/Digital-Forensics-Discord-Server/MemberProjects
- **Stars**: Lower visibility, but this is the DFIR community's own project list
- **Purpose**: Not a star driver but puts the tool in front of DFIR practitioners
  who will actually use it and share it within that community
- **Format**: Open a PR adding a row to the README table with tool name, author,
  description, and link
- **Do this first** — this community is most likely to use the tool genuinely

### 2e. alphaSeclab/awesome-forensics

- **URL**: https://github.com/alphaSeclab/awesome-forensics
- **Notes**: ~2k stars, less actively maintained but still indexed by GitHub
  search. Submit after cugu/awesome-forensics.

---

## 3. Reddit Posts

### Primary target: r/privacy (1.8M members)

**Angle**: "Discord caches every image you view on your disk — here's how to see
what's there" — this frames it as a privacy disclosure, not a hacking tool.

**Draft post:**

```
Title: Discord caches every image and video you view to your local disk —
       here's a tool to see what's stored

Body:

Most people don't realize this: every time you view an image or video in
Discord, a copy is written to a local Electron cache directory with no
extension. If someone sends then deletes a message, the file stays on your
disk — sometimes for weeks.

I built cache-crow to make this visible. It scans your Discord cache,
identifies files by magic bytes (not by extension), and shows you what's
there:

  cache-crow --stats
  # → 23 media files (8 PNG, 5 JPEG, 4 WebP, 3 GIF, 2 MP4, 1 WebM)

  cache-crow --output-dir ./recovered
  # → extracts everything with the right extension

Cache paths:
  Linux:   ~/.config/discord/Cache/Cache_Data/
  macOS:   ~/Library/Application Support/discord/Cache/Cache_Data/
  Windows: %APPDATA%\discord\Cache\Cache_Data\

Some things worth knowing:
- Discord's "clear cache" setting doesn't always purge this directory
- Uninstalling Discord leaves the cache folder intact on most systems
- The cache is readable by anyone with access to your OS user account

GitHub: https://github.com/Crowligarchy/cache-crow
Install: pip install git+https://github.com/Crowligarchy/cache-crow

Cross-platform (Linux/macOS/Windows), MIT license, Python 3.10+. Slack
support is also included.

Happy to answer questions about how the cache format works.
```

**Post timing**: Tuesday or Wednesday, 9-11am ET. Avoid Monday and Friday.
**Do not post the same text to multiple subreddits simultaneously** — wait at
least a few days between communities, and adjust the framing for each.

### Secondary targets

**r/netsec** — lead with the forensics angle, mention DFIR use cases. Shorter
post, link to the README. netsec readers will explore on their own.

**r/discordapp** (700k members) — frame this carefully. Do not lead with
"deleted messages." Lead with "I built a tool to see what Discord stores
locally on your machine." This community has moderators who may be Discord
employees or enthusiasts — be straightforward and technical.

**r/Python** — focus on the implementation: magic byte detection, Chromium
Simple Cache format, rich terminal output. Link to the source. Python
community engages more when the code is interesting, not just the feature.

**r/netsecstudents** — educational angle. Explain how Electron apps cache,
what magic bytes are, how cache eviction works. This community stars tools
they learn from.

---

## 4. Hacker News

### Show HN title options

Option A (recommended — specific, technical, surprising):
```
Show HN: cache-crow – extract media Discord cached on your disk from deleted messages
```

Option B (privacy angle):
```
Show HN: cache-crow – Discord keeps a local copy of every image you view, here's how to read it
```

Option C (forensics angle):
```
Show HN: cache-crow – CLI tool for reading Electron app disk caches (Discord, Slack)
```

**Recommendation**: Option B. The "you didn't know this was happening to you"
angle generates HN discussion. Option A risks sounding like a hacking tool.
Option C is accurate but dry.

**Post timing**: Tuesday through Thursday, 9am-noon ET. Monday morning is
competitive. Friday afternoon is a dead zone.

**Text to include in the HN post body** (HN allows a short description on Show HN):

```
Discord (and other Electron apps) cache media to a local directory using
Chromium's disk cache format. Files have no extensions — they're stored as
binary blobs named f_000001, f_00a3f2, etc. When a message is deleted, the
local cache is not cleared.

cache-crow scans the cache, identifies files by magic bytes, and extracts
them with the correct extension. Python 3.10+, cross-platform, MIT.

GitHub: https://github.com/Crowligarchy/cache-crow
```

**Engagement strategy**: Be in the thread for the first 2 hours to answer
technical questions. HN rewards authors who engage substantively. Expect
questions about: how Chromium's Simple Cache format works, whether this is
a Discord-specific issue (it isn't — all Electron apps behave this way),
and privacy implications.

---

## 5. Similar tools to engage

These are unmaintained tools that people still find via search. Opening issues
referencing cache-crow as an active alternative is legitimate as long as it is
honest and helpful.

| Repo | Language | Last commit | Stars | Action |
|------|----------|-------------|-------|--------|
| mdawsonuk/DiscordExplorer | None | 2020-10 | 21 | Open issue: "This repo appears unmaintained — cache-crow is an active Python alternative: [link]" |
| TatoExp/DCache | C# | 2019-10 | 1 | Small — skip |
| vars1ty/Discord-Cache-Viewer | C# | 2022-01 | 1 | Small — skip |
| lloyd99901/CacheExplorer | VB.NET | 2020-05 | 2 | Small — skip |
| FordJ2/discord-cache-grabber | Batch | 2022-03 | 5 | Small — skip |

Only engage with mdawsonuk/DiscordExplorer — it has enough stars that people
still find it. Be helpful, not promotional. Phrase it as: "Saw people landing
here looking for an active tool — cache-crow does [X] and is actively
maintained: [link]."

Note: uintdev/Discord-Cache-Dump (Go, 60 stars, last commit 2025-11) is
actively maintained. Do not post on that one. Consider opening a discussion
there proposing collaboration or cross-referencing.

---

## 6. GitHub discoverability patterns

Beyond topics, these drive organic stars:

**Issues as content**: Create a few issues labeled `good first issue` and
`help wanted` for the roadmap items (watch mode, macOS cache paths, additional
magic bytes). Developers searching for OSS contributions to make will star
before they even start.

**Releases**: Cut a v0.1.0 release with `gh release create v0.1.0 --generate-notes`.
Releases show in GitHub's Explore feed and push the repo higher in topic searches.

**GitHub Sponsors / profile**: Add a `FUNDING.yml` pointing to GitHub Sponsors.
Even if no one donates, the button increases perceived legitimacy.

**Cross-link from DFIR content**: Blog posts on HackTricks, Forensic Focus, and
similar sites link to tools. The existing HackTricks Discord Cache Forensics page
(https://hacktricks.wiki/en/generic-methodologies-and-resources/basic-forensic-methodology/specific-software-file-type-tricks/discord-cache-forensics.html)
does not reference a Python CLI tool. Opening a PR there would put cache-crow in
front of every practitioner who reads that page.

---

## 7. Execution order

1. Add GitHub topics (30 seconds, run the gh command above)
2. Cut a v0.1.0 release
3. Open issue on Digital-Forensics-Discord-Server/MemberProjects
4. PR to cugu/awesome-forensics
5. PR to Lissy93/awesome-privacy
6. Post to r/privacy
7. Post to r/netsec (different angle, 3-5 days after r/privacy)
8. Post to r/discordapp
9. Show HN (after at least 15-20 stars — HN commenters check the star count
   as a signal of whether others found it worth starring)
10. Post to r/Python
11. PR to vinta/awesome-python (after 50+ stars)
12. Engage mdawsonuk/DiscordExplorer issue
