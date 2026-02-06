# CFB Scout Gap Analysis

**Date:** 2026-02-05
**Scope:** Full review of codebase vs. plan documents (Phases 1-6E)

---

## Executive Summary

CFB Scout has a solid foundation. Phases 1-5 are **code-complete** — the API layer (29 endpoints), processing pipeline, storage layer, and all core features (entity extraction, grading, trends, comparisons, draft board, alerts, transfer portal) are implemented and functional. Phase 6A-6C (vector embeddings, player mart, enhanced matching) are also implemented at the code level.

The primary gaps are:

1. **Phase 6D (cfb-app integration) and 6E (operations/CI) are unbuilt** — the two phases that take this from a standalone tool to a production system
2. **Sync/async mismatch** — 5 modules make synchronous HTTP/LLM calls inside async contexts, blocking the event loop
3. **Alert system is incomplete** — only 2 of 5 alert types are wired; evaluation engine never runs
4. **Test quality issues** — several tests have always-passing assertions, and 3 core modules have zero test coverage
5. **Dead code and unused tables** — `team_rosters`, `crawl_jobs` tables and several functions are never called
6. **No Reddit crawler** — the original Phase 1 data source is still missing (awaiting API approval)
7. **PFF integration gap** — client exists but nothing populates `scouting.pff_grades` from the API
8. **No CI/CD, no scheduling, no monitoring** — everything runs manually

---

## What's Built (Current State)

### Data Ingestion
| Feature | Status | Notes |
|---------|--------|-------|
| 247Sports commits crawler | Built | URL construction + parsing in `two47.py` |
| Base crawler class | Built | Async httpx client with rate limiting in `base.py` |
| PFF API client | Built | `pff.py` — httpx client with Pydantic models |
| Reddit crawler | **Not built** | Config references Reddit creds, but no crawler module exists |

### AI Processing (src/processing/)
| Module | Status | Notes |
|--------|--------|-------|
| `summarizer.py` | Built | Claude summarization + sentiment extraction |
| `entity_extraction.py` | Built | Regex + Claude extraction paths |
| `entity_linking.py` | Built | Links reports to players via matching pipeline |
| `aggregation.py` | Built | Report aggregation, Claude trait extraction, composite grades |
| `grading.py` | Built | Full grading pipeline with timeline snapshots |
| `pipeline.py` | Built | Report processing orchestrator (summarize unprocessed) |
| `player_matching.py` | Built | 3-tier matching: deterministic, vector, fuzzy + review queue |
| `embeddings.py` | Built | OpenAI text-embedding-3-small, 1536 dimensions |
| `trends.py` | Built | Linear regression trend detection (rising/falling/stable) |
| `comparison.py` | Built | Head-to-head comparison, radar data, cosine similarity |
| `draft.py` | Built | Draft score calculation, projection enum, board generation |
| `transfer_portal.py` | Built | Portal mention extraction, destination prediction, impact analysis |
| `alerting.py` | Partial | 5 check functions exist, only 2 wired into evaluator |

### API Layer (src/api/)
| Category | Endpoints | Status |
|----------|-----------|--------|
| Health | `GET /` | Built |
| Players | `GET /players`, `GET /players/{id}` | Built |
| Teams | `GET /teams`, `GET /teams/{name}/players` | Built |
| Trends | `GET /trends/rising`, `GET /trends/falling`, `GET /players/{id}/trend` | Built |
| Comparison | `GET /compare/{id1}/{id2}`, `GET /players/{id}/similar` | Built |
| Watchlists | Full CRUD (5 endpoints) | Built |
| Draft | `GET /draft/board`, `GET /draft/position/{pos}` | Built |
| Alerts | Full CRUD + history (6 endpoints) | Built (minor bug) |
| Transfer Portal | 5 endpoints including predict + snapshot | Built |
| **Total** | **29 endpoints** | **All implemented** |

### Storage Layer (src/storage/)
| Component | Status | Notes |
|-----------|--------|-------|
| Async connection pool | Built | psycopg v3 AsyncConnectionPool (2-10 connections) |
| Schema (13 tables) | Built | All tables in `scouting` schema |
| 6 migrations | Applied | pgvector, embeddings, pending_links, player_mart, indexes, refresh |
| ~30 DB functions | Built | Full CRUD for all entities |

### Scripts
| Script | Purpose | Status |
|--------|---------|--------|
| `run_pipeline.py` | CLI orchestrator (--seed, --process, --crawl-247, --link, --grade, --review-links) | Built |
| `run_api.py` | Uvicorn launcher | Built |
| `backfill_embeddings.py` | Batch generate embeddings from player_mart | Built |

---

## What's Planned but Not Built (Gaps)

### Phase 6D — cfb-app Frontend Integration (Unbuilt)
The unified architecture design calls for:
- Player profile page in cfb-app (Next.js) querying `player_mart` via Supabase
- "Find Similar Players" UI component using embedding similarity
- Portal tracker view
- Deprecation of cfb-scout's FastAPI in favor of direct Supabase queries from cfb-app

**Impact:** cfb-scout currently has no consumer. The 29 API endpoints work but nothing calls them in production.

### Phase 6E — Operations (Unbuilt)
- GitHub Actions for daily pipeline automation
- pg_cron for materialized view refresh (migration exists, but no cron job configured)
- Monitoring/alerting for pipeline failures
- Daily cadence orchestration (6:00 AM database refresh -> 6:30 AM embeddings -> 7:00 AM crawl -> 7:30 AM mart refresh)

**Impact:** Everything runs manually. No automated data freshness.

### Reddit Crawler (Phase 1 — Never Built)
- Config has `reddit_client_id`, `reddit_client_secret`, `reddit_user_agent`
- No crawler module in `src/crawlers/` for Reddit
- Original plan noted "awaiting API approval"

**Impact:** The primary unstructured data source (Reddit scouting discussions) is missing. 247Sports is the only active crawler.

### Alert System (Mostly Incomplete)
- `alerting.py` has all 5 check functions (`check_grade_change_alert`, `check_status_change_alert`, `check_new_report_alert`, `check_trend_change_alert`, plus portal_entry)
- `process_alerts_for_player()` exists but **only wires grade_change and status_change** — the other 3 types have check functions that are never called
- `run_alert_check()` exists but is **never called** from any API endpoint or script
- The alert DB schema and CRUD are complete, but no scheduling triggers evaluation

**Impact:** Users can create alerts via API, but alerts never fire. Even if triggered manually, 3 of 5 alert types would be silently skipped.

### PFF Pipeline Integration (Missing)
- `src/clients/pff.py` has a full HTTP client (`get_player_grades()`, `get_player_by_name()`)
- `scouting.pff_grades` table exists with upsert/query functions in `db.py`
- **No code connects the two** — nothing fetches from PFF API and writes to the DB table
- Draft score formula weights PFF at 30%, but grades can only be inserted manually

**Impact:** Draft projections are degraded without PFF data. The client code is untested beyond constructor.

### Dead Code and Unused Tables
- `scouting.team_rosters` — defined in schema, never read or written by any Python code
- `scouting.crawl_jobs` — defined in schema, never read or written by any Python code
- `scouting.player_mart` — materialized view exists at DB level, never queried by Python code (intended for cfb-app Phase 6D)
- `extract_portal_mentions()` in `transfer_portal.py` — defined but never called
- `get_team_draft_prospects()` in `draft.py` — defined but never exposed via API
- `get_config()` in `config.py` — defined but never called; modules use `os.environ` directly

---

## Implementation Quality Assessment

### Strengths
- **Clean async patterns**: Consistent use of `async with get_connection() as conn:` throughout
- **Proper connection pooling**: psycopg v3 AsyncConnectionPool with lazy init
- **Well-structured schema**: Good use of indexes, constraints, upsert patterns
- **Good separation of concerns**: API -> Processing -> Storage layers are clean
- **Pydantic models** for API request/response validation

### Concerns

#### 1. Sync/Async Mismatch (Event Loop Blocking)
Multiple modules make synchronous HTTP/LLM calls inside async contexts:

| Module | Issue |
|--------|-------|
| `summarizer.py` | Sync `anthropic.Anthropic()` client — blocks event loop on every summarize call |
| `entity_extraction.py` | Sync Anthropic client — creates new client per call |
| `aggregation.py` | Sync Anthropic client — creates new client per call |
| `embeddings.py` | Sync `openai.OpenAI()` client — blocks on embedding generation |
| `pff.py` | Sync `httpx.Client` — entire PFF client is synchronous |
| `two47.py` | `_fetch_page()` uses sync `httpx.Client` with blocking `time.sleep(2)` |

Additionally, `summarizer.py` and `aggregation.py` create **new Anthropic client instances on every function call** rather than reusing a shared client.

#### 2. Alert History Bug (`api/main.py:405`)
```python
if unread_only:
    history = await get_unread_alerts(conn, user_id)
else:
    history = await get_unread_alerts(conn, user_id)  # For now, just unread
```
The `unread_only=False` path returns the same unread results. No `get_all_alerts_history()` function exists.

#### 3. Hardcoded Year in Entity Linking
`entity_linking.py:79` defaults to `class_year=2024` for unmatched players. Should use current year dynamically.

#### 4. N+1 Query Patterns
- `api/main.py:152-201` — `list_teams` runs one query to get teams, then N queries for top players. Should use a window function or lateral join.
- `draft.py:build_draft_board()` — calls `get_player_pff_grades()` and `analyze_player_trend()` per-player in a loop.

#### 5. In-Memory Scalability Limits
- `comparison.py:find_similar_players()` loads ALL players with traits into memory for cosine similarity. Should use pgvector.
- `player_matching.py:find_roster_match()` loads all roster candidates into memory for fuzzy matching.

#### 6. No Pagination Metadata
List endpoints return arrays but no total count, next/prev links, or pagination metadata.

#### 7. No Auth, CORS, or Rate Limiting
API has no authentication, authorization, CORS configuration, or rate limiting. Acceptable if Phase 6D deprecates the API, but a risk if it stays.

---

## Test Coverage Gaps

### Modules with Zero Tests
| Module | Risk Level | Notes |
|--------|-----------|-------|
| `entity_linking.py` | **High** | Core domain logic — links reports to players |
| `grading.py` | **High** | Grading pipeline — updates grades and creates snapshots |
| `pipeline.py` | **Medium** | Orchestration — lower risk if sub-functions tested |
| `config.py` | Low | Simple dataclass |
| `api/models.py` | Low | Pydantic models (validated at runtime) |
| `crawlers/base.py` | Medium | Base crawler class with HTTP logic |

### Tests That Always Pass (False Coverage)
| File | Issue |
|------|-------|
| `test_player_matching.py` (4 tests) | `assert result is None or isinstance(result, ...)` — passes regardless |
| `test_summarizer.py` | `assert "Texas" in str(prompt) or True` — always True |
| `test_portal_processing.py` (1 test) | Permissive assertion on prediction return |

### Missing Test Categories
- **No error path testing** across the board (malformed Claude responses, API failures, timeouts)
- **No POST/PUT/DELETE endpoint testing** — only GET endpoints tested in API
- **No crawler HTTP testing** — only URL builders tested, no httpx mocking
- **No PFF client HTTP testing** — only constructor tested
- **No concurrent operation testing** (race conditions on upserts)
- **No pytest-cov** configured — no coverage measurement

### API Endpoint Coverage
- 14 of 29 endpoints tested (**48%**)
- Missing: all mutation endpoints (POST/PUT/DELETE), comparison, similarity, detailed player
- Tests are smoke-level: status code + type checks, no response body validation

---

## Recommended Next Steps

### Priority 1: Fix Quality Issues (Low effort, high value)
1. Fix alert history bug (`unread_only=False` path)
2. Fix always-passing test assertions (5 tests across 3 files)
3. Replace hardcoded `class_year=2024` with dynamic year
4. Add tests for `entity_linking.py` and `grading.py`
5. Clean up dead code: remove unused `get_config()`, `extract_portal_mentions()` calls, or wire them in

### Priority 2: Sync-to-Async Migration (Medium effort, high value)
- Convert `summarizer.py`, `entity_extraction.py`, `aggregation.py` to use `anthropic.AsyncAnthropic`
- Convert `embeddings.py` to use `openai.AsyncOpenAI`
- Convert `pff.py` to use `httpx.AsyncClient`
- Convert `two47.py` fetch to use async httpx with `asyncio.sleep()`
- Share a single async client instance per module instead of creating per-call

### Priority 3: Complete Alert System (Medium effort, high value)
- Wire `new_report`, `trend_change`, and `portal_entry` into `process_alerts_for_player()`
- Add `--evaluate-alerts` to `run_pipeline.py` calling `run_alert_check()`
- This completes the alert feature which is currently 40% wired

### Priority 4: Operations Foundation — Phase 6E (Medium effort, critical path)
- GitHub Actions workflow for daily pipeline
- pg_cron configuration for player_mart refresh
- Basic health monitoring (pipeline run success/failure logging)
- This is the bridge to making cfb-scout useful without manual intervention

### Priority 5: Test Hardening (Medium effort, ongoing)
- Add pytest-cov to dev dependencies and pyproject.toml config
- Write tests for mutation API endpoints
- Mock httpx for crawler and PFF client tests
- Add error path tests for Claude response parsing

### Priority 6: PFF Pipeline Integration (Medium effort)
- Build a pipeline step that calls `PFFClient.get_player_grades()` and writes to `scouting.pff_grades` via `db.upsert_pff_grade()`
- Add `--fetch-pff` to `run_pipeline.py`
- This unlocks the full draft score formula (currently PFF component is always 0)

### Priority 7: cfb-app Integration — Phase 6D (High effort, end goal)
- Define Supabase RLS policies for player_mart access
- Build player profile page in cfb-app
- Build similarity search component
- Evaluate whether to keep FastAPI or go Supabase-direct

### Priority 8: Reddit Crawler (Medium effort, dependent on API approval)
- Implement when Reddit API access is available
- Would significantly expand the unstructured data pipeline

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| No CI/CD — regressions go undetected | High | Priority 3: GitHub Actions |
| Sync calls block event loop in 6 modules | High | Convert summarizer, entity_extraction, aggregation, embeddings, PFF, 247 to async clients |
| Always-passing tests mask real failures | High | Priority 1: Fix 5 assertions |
| Manual pipeline execution means stale data | High | Priority 3: Scheduling |
| Alert system is 60% incomplete (3 of 5 types unwired, evaluator never runs) | Medium | Priority 2: Wire remaining types + add --evaluate-alerts |
| PFF data pipeline missing — draft scores degraded | Medium | Build fetch->store pipeline connecting pff.py to db.py |
| No Reddit data source limits scouting intelligence | Medium | Blocked on API approval |
| In-memory player loading won't scale | Medium | Replace comparison.py and player_matching.py with pgvector queries |
| No authentication on API endpoints | Medium | Phase 6D may deprecate API; if keeping, add auth |
| N+1 queries in teams + draft endpoints | Low | Refactor to window functions / batch queries |
| Dead tables and unreachable code add confusion | Low | Clean up team_rosters, crawl_jobs, unused functions |
| player_mart depends on cross-schema joins | Low | Already handled in migration 004; monitor for schema drift |
| New Anthropic client created per function call | Low | Share a module-level async client instance |

---

## Summary Scorecard

| Area | Score | Notes |
|------|-------|-------|
| Feature completeness (vs plan) | **70%** | Phases 1-6C built; 6D, 6E, Reddit, PFF pipeline remain |
| Code quality | **B** | Clean architecture but pervasive sync/async mismatch, N+1 queries, dead code |
| Test coverage | **C** | 48% API coverage, 3 untested core modules, 5 false-positive tests |
| Production readiness | **D** | No CI/CD, no scheduling, no monitoring, no auth |
| Data pipeline completeness | **C+** | 247 crawler working; PFF client exists but unconnected; Reddit missing; alerts 40% wired |
