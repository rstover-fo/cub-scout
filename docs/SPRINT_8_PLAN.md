# Sprint 8: Free Source Crawlers (Athletic Dept + CollegePressBox)

**Status:** Planned
**Prerequisite:** Sprint 7 (article crawler infrastructure)

---

## Context

Sprint 7 built the article crawler infrastructure (`ArticleCrawlerBase`, 247Sports + On3 crawlers). The existing crawlers capture free public articles but hit paywalls on premium content. This sprint expands to high-quality free sources that provide the same scouting intelligence — coach evaluations, practice reports, player mentions — without paywall or ToS concerns.

## Source Analysis

| Source | Content Type | Signal Quality | Parsing Difficulty |
|--------|-------------|---------------|-------------------|
| **Athletic dept sites** (texassports.com, etc.) | Press conference transcripts, practice reports, post-game quotes | High — coaches name and evaluate specific players | Medium — each school has different site structure |
| **CollegePressBox.com** | Aggregated press transcripts, game notes, media guides | High — structured press materials | Low — single site, consistent format |
| **SB Nation team blogs** | Free analyst articles, spring practice coverage | Medium — fan-analyst perspective, variable quality | Low — predictable URL structure |

## Phase 1: Athletic Department Sites + CollegePressBox

### 8.1: Create `CollegePressBoxCrawler`
**File:** `src/crawlers/articles/collegepressbox.py`

- **Discovery:** Fetch `collegepressbox.com/conference/{conf}/beatwriters` or team-specific pages
- **Extraction:** Parse press conference transcripts, game notes
- `source_name = "collegepressbox"`, `request_delay = 1.5`
- Content here is press material — free, public, no ToS concerns
- Start with SEC + Big Ten teams matching the 4 daily pipeline teams

### 8.2: Create `AthleticDeptCrawler`
**File:** `src/crawlers/articles/athletic_dept.py`

- Per-school config dict mapping team slugs to athletic site URL patterns:
  - `texas` -> `texassports.com/news`
  - `ohio-state` -> `ohiostatebuckeyes.com/news`
  - `georgia` -> `georgiadogs.com/news`
  - `alabama` -> `rolltide.com/news`
- **Discovery:** Fetch team news page, filter for football articles
- **Extraction:** Parse article body, author, date
- `source_name = "athletic_dept"`, `request_delay = 1.5`
- These are official university sites — public press materials, no ToS issues

### 8.3: Write tests for Phase 1 crawlers
- Inline HTML fixtures per source
- Parse, extract, and crawl integration tests
- Follow Sprint 7 test patterns

### 8.4: Wire Phase 1 crawlers into `--crawl-articles`
- Add both crawlers to the `--crawl-articles` pipeline stage
- Update daily pipeline workflow

---

## Phase 2: SB Nation Team Blogs (Future)

### 8.5: Create `SBNationCrawler`
- **Discovery:** Fetch `sbnation.com/{team-blog}/` (e.g., `burntorangenation.com`)
- Free analyst articles, high volume
- Predictable URL/HTML structure across the SB Nation network

---

## Phase 3: YouTube Press Conference Transcripts (Future)

### 8.6: Create `YouTubeTranscriptCrawler`
- Uses `youtube-transcript-api` package (no API key needed for auto-captions)
- Search team YouTube channels for press conference videos
- Extract auto-generated captions as text
- Needs transcript cleanup (punctuation, speaker identification)

---

## Phase 4: X/Twitter (Deferred — Requires Revenue)

- Official API: $100/mo basic tier
- Only justified when platform has paying users
- High noise, requires beat writer account curation

---

## Task Dependencies

```
8.1 + 8.2 (parallel) -> 8.3 -> 8.4
                                  |
                          8.5 (Phase 2, future)
                          8.6 (Phase 3, future)
```

## Verification

1. `ruff check . && ruff format --check .`
2. `pytest -q` — all tests pass including new crawler tests
3. `--crawl-articles` runs all crawlers (247, On3, CollegePressBox, Athletic Dept)
4. Manual smoke test against live sites for the 4 daily pipeline teams
