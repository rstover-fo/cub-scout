# CFB Scout

College football scouting intelligence agent. Crawls recruiting sites, extracts player entities, grades prospects, and serves data via API.

## Related Projects

This project is part of a three-repo college football platform sharing a single Supabase instance:

| Repo | Role | Relationship |
|------|------|-------------|
| **cfb-database** | Schema source of truth, dlt pipelines | Populates `core.roster` and `recruiting.recruits` that this project reads |
| **cfb-app** | Next.js analytics dashboard | Potential future consumer of this API |

**Schema dependency:** cfb-scout reads from `core.roster` and `recruiting.recruits` (owned by cfb-database) and owns the `scouting` schema. Changes to roster/recruit schema in cfb-database can break this project.

## Tech Stack

- Python 3.12, FastAPI, psycopg v3 async (AsyncConnectionPool), anthropic, openai, pgvector
- Database: Supabase Postgres (`scouting` schema owned, `core`/`recruiting` schemas read)
- LLM: Claude (model constant in `src/config.py` as `CLAUDE_MODEL`, currently `claude-haiku-4-5-20251001`)

## Project Structure

```
src/
  api/
    main.py             # FastAPI app (30 endpoints, v0.3.0)
    models.py           # Pydantic request/response models
  clients/
    anthropic.py        # Shared async Anthropic client (lazy singleton)
    pff.py              # PFF API client (httpx, grades/search endpoints)
  crawlers/
    base.py             # BaseCrawler ABC + CrawlResult dataclass
    recruiting/
      two47.py          # 247Sports commits crawler (BeautifulSoup, 2s rate limit)
  processing/
    pipeline.py         # Batch report processing orchestrator
    summarizer.py       # Claude-powered summarization + sentiment
    entity_extraction.py # Player name extraction (regex + Claude NER)
    entity_linking.py   # Connects reports to player profiles
    player_matching.py  # 3-tier matching (deterministic > vector > fuzzy)
    aggregation.py      # Player profile aggregation from multiple reports
    grading.py          # Composite grading pipeline with timeline snapshots
    comparison.py       # Head-to-head player comparison with radar charts
    draft.py            # Draft board scoring/projection (batch N+2 pattern)
    trends.py           # Rising/falling stock via linear regression (numpy)
    transfer_portal.py  # Portal event extraction, destination prediction
    alerting.py         # 5 alert types with condition checking
    embeddings.py       # OpenAI text-embedding-3-small (1536 dims)
    pff_pipeline.py     # PFF grade fetch and storage pipeline
  storage/
    db.py               # Async pooled connections (min=2, max=10), migrations
    schema.sql          # Full schema definition
    migrations/         # 6 migration files (pgvector, embeddings, pending_links, player_mart)
  config.py             # Config dataclass (frozen) with from_env(), CLAUDE_MODEL constant
scripts/
  run_pipeline.py       # Main CLI (--seed, --process, --crawl-247, --link, --grade, etc.)
  run_api.py            # uvicorn API server launcher
  backfill_embeddings.py # One-time embedding backfill for roster data
tests/                  # 25 test files
  conftest.py           # Auto-mocks for Anthropic (prompt-routed) and OpenAI clients
```

## Database Schema

### Owned: `scouting` schema (14 tables)

| Table | Purpose |
|-------|---------|
| `reports` | Raw crawled content with summaries and sentiment |
| `players` | Scouting player profiles with composite grades, traits, comps |
| `player_timeline` | Longitudinal grade/status snapshots |
| `pff_grades` | PFF grade snapshots by season/week |
| `watch_lists` | User watch lists with player_ids array |
| `alerts` | Alert rules (5 types: grade_change, new_report, status_change, trend_change, portal_entry) |
| `alert_history` | Fired alert records |
| `transfer_events` | Portal event tracking (entered/committed/withdrawn) |
| `portal_snapshots` | Daily portal activity snapshots |
| `player_embeddings` | pgvector embeddings for player identity (migration 002) |
| `pending_links` | Review queue for low-confidence matches (migration 003) |
| `player_mart` | Materialized view: roster + recruiting + scouting + portal (migration 004) |
| `team_rosters` | Reserved, currently unused |
| `crawl_jobs` | Reserved, currently unused |

### Depended: schemas from cfb-database

- `core.roster` -- player name, team, year, position
- `recruiting.recruits` -- player name, committed_to, recruiting_year

## API Endpoints (30)

| Group | Endpoints |
|-------|-----------|
| Root | `GET /` (health check) |
| Players | `GET /players`, `GET /players/{id}`, `GET /players/{id}/trend`, `GET /players/{id}/similar` |
| Teams | `GET /teams`, `GET /teams/{name}/players`, `GET /teams/{name}/transfers`, `GET /teams/{name}/portal-impact` |
| Trends | `GET /trends/rising`, `GET /trends/falling` |
| Comparisons | `GET /compare/{id1}/{id2}` |
| Watch Lists | `GET/POST /watchlists`, `POST/DELETE /watchlists/{id}/players/{pid}`, `DELETE /watchlists/{id}` |
| Draft Board | `GET /draft/board`, `GET /draft/position/{pos}` |
| Alerts | `GET/POST /alerts`, `DELETE /alerts/{id}`, `POST /alerts/{id}/deactivate`, `GET /alerts/history`, `POST /alerts/history/{id}/read` |
| Transfer Portal | `GET /transfer-portal/active`, `GET /transfer-portal/player/{id}`, `GET /transfer-portal/player/{id}/predict`, `POST /transfer-portal/snapshot` |

## Processing Pipeline

Data flow: **crawl -> summarize -> extract entities -> link to players -> grade -> alert**

### Player Matching (3-tier)
1. **Deterministic:** Exact name+team+year match, or athlete_id FK
2. **Vector similarity:** pgvector cosine distance (>= 0.92 accept, 0.80-0.92 review queue)
3. **Fuzzy:** rapidfuzz token_sort_ratio (>= 80 threshold)

### Draft Board
Uses batch N+2 optimization: loads PFF grades and trends in 2 bulk queries instead of 2N individual queries.

## Architectural Patterns

- **Async context manager for DB:** `get_connection()` auto-initializes pool on first use
- **UPSERT everywhere:** `ON CONFLICT ... DO UPDATE` for idempotent operations
- **Lazy singletons:** Anthropic, OpenAI, PFF clients initialized on first use
- **FastAPI lifespan:** Pool init/cleanup via async context manager
- **Auto-mocking in tests:** `conftest.py` auto-patches all LLM calls with prompt-based routing

## Commands

```bash
# Development
uvicorn src.api.main:app --reload   # Dev server

# Pipeline CLI (9 modes)
python scripts/run_pipeline.py --seed              # Seed initial data
python scripts/run_pipeline.py --process           # Process reports
python scripts/run_pipeline.py --crawl-247         # Crawl 247Sports
python scripts/run_pipeline.py --link              # Link entities to players
python scripts/run_pipeline.py --grade             # Run grading pipeline
python scripts/run_pipeline.py --fetch-pff         # Fetch PFF grades
python scripts/run_pipeline.py --evaluate-alerts   # Check and fire alerts
python scripts/run_pipeline.py --review-links      # Review pending links
python scripts/run_pipeline.py --all               # Run full pipeline

# Testing & linting
.venv/bin/ruff check .              # Lint
.venv/bin/ruff format --check .     # Format check
.venv/bin/pytest -q                 # Tests (requires live Supabase)
.venv/bin/pytest -m "not integration"  # Unit tests only
```

## Testing

- 25 test files covering all processing modules, API endpoints, clients, crawlers
- `conftest.py` auto-mocks Anthropic (prompt-routed responses) and OpenAI (embedding) clients; provides `mock_db_connection` fixture
- Integration tests require live Supabase connection
- Pre-push hook (`.githooks/pre-push`) runs ruff check + ruff format (no tests -- requires live DB)
- Coverage config: source `src/`, fail_under 50%

## CI/CD

- `.github/workflows/ci.yml` -- lint + format + unit tests on push/PR to main
- `.github/workflows/daily-pipeline.yml` -- daily cron (7:00 AM CT) runs crawl, process, link, grade, alerts with summary

## Environment Variables

```bash
DATABASE_URL=            # Supabase connection string (same instance as cfb-database)
ANTHROPIC_API_KEY=       # For Claude LLM calls
OPENAI_API_KEY=          # For text-embedding-3-small
PFF_API_KEY=             # PFF API access (api.pff.com/v1)
REDDIT_CLIENT_ID=        # Reddit API
REDDIT_CLIENT_SECRET=    # Reddit API
REDDIT_USER_AGENT=       # Reddit API user agent string
```

## Git Conventions

- Branch names: `feature/`, `fix/`, `refactor/`, `chore/` prefixes
- Commit messages: imperative mood, 50-char subject line

## Configuration

- `pyproject.toml` -- dependencies, ruff config (line-length 100, py312, rules: E/F/I/UP), pytest config
- `src/config.py` -- `Config` dataclass (frozen) with `from_env()` class method
- DB pool: min=2, max=10 connections (`MIN_POOL_CONNECTIONS`, `MAX_POOL_CONNECTIONS` in db.py)
