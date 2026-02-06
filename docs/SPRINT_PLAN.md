# CFB Scout Sprint Plan

**Generated:** 2026-02-05
**Source:** `docs/GAP_ANALYSIS.md`
**Structure:** 6 sprints, 28 tasks, each task scoped for a single agent context window

---

## Sprint 1: Quality Fixes & Dead Code Cleanup
**Goal:** Fix known bugs, eliminate false-positive tests, clean up dead code. Zero new features — just make what exists correct.

**Deliverable:** All existing tests pass with real assertions. No dead code confusing future work.

### Task 1.1: Fix alert history endpoint bug
- **File:** `src/api/main.py:398-406`
- **What:** The `unread_only=False` branch calls `get_unread_alerts()` — same as the `True` branch
- **Fix:** Add `get_all_alert_history(conn, user_id)` to `src/storage/db.py` that queries without `is_read = FALSE` filter. Wire it into the `else` branch.
- **Test:** Update `tests/test_api.py` to verify the history endpoint returns read alerts when `unread_only=false`
- **Validation:** `pytest tests/test_api.py -k alert`

### Task 1.2: Fix always-passing test assertions
- **Files:** `tests/test_player_matching.py`, `tests/test_summarizer.py`, `tests/test_portal_processing.py`
- **What:** 5 tests use `assert X or True` or `assert X is None or isinstance(X, ...)` patterns that always pass
- **Fix for test_player_matching.py (4 tests):** Replace `assert result is None or isinstance(result, ...)` with proper assertions. If the DB-dependent tests can't guarantee data, mark them with `@pytest.mark.integration` and skip in default runs, or set up test fixtures.
- **Fix for test_summarizer.py:** Replace `assert "Texas" in str(prompt) or True` with a real assertion that verifies team context is passed to Claude
- **Fix for test_portal_processing.py:** Replace permissive assertion on `predict_destination` with type + structure check
- **Validation:** `pytest tests/test_player_matching.py tests/test_summarizer.py tests/test_portal_processing.py -v`

### Task 1.3: Fix hardcoded class_year
- **File:** `src/processing/entity_linking.py:79`
- **What:** `class_year=2024` hardcoded for unmatched players
- **Fix:** Replace with `datetime.now().year` (import `datetime` at top)
- **Validation:** `ruff check src/processing/entity_linking.py`

### Task 1.4: Clean up dead code
- **What:** Remove or wire unused functions and document unused tables
- **Actions:**
  1. `src/config.py`: Remove `get_config()` function (never called; modules use `os.environ` directly). Keep `Config` dataclass if desired for future use, but remove the factory.
  2. `src/processing/transfer_portal.py`: `extract_portal_mentions()` is defined but never called. Either wire it into `entity_linking.py` as a portal detection step, or remove it. Recommend: keep it, add a `# TODO: wire into pipeline` comment.
  3. `src/processing/draft.py`: `get_team_draft_prospects()` is defined but not exposed via API. Either add a `GET /teams/{name}/draft-prospects` endpoint or add a TODO comment.
  4. Add comments to `schema.sql` noting `team_rosters` and `crawl_jobs` tables are currently unused.
- **Validation:** `ruff check src/`

---

## Sprint 2: Sync-to-Async Migration
**Goal:** Convert all synchronous HTTP/LLM calls to async. Eliminate event loop blocking. Share client instances.

**Deliverable:** Every external call (Anthropic, OpenAI, httpx) uses async clients. No sync HTTP inside async functions.

### Task 2.1: Create shared async Anthropic client
- **File:** New module `src/clients/anthropic.py` (or add to existing pattern)
- **What:** Create a module-level `anthropic.AsyncAnthropic` client with lazy initialization, similar to `db.py`'s pool pattern
- **Interface:**
  ```python
  _client: AsyncAnthropic | None = None

  def get_anthropic_client() -> AsyncAnthropic:
      global _client
      if _client is None:
          _client = AsyncAnthropic()
      return _client
  ```
- **Validation:** Import works, `ruff check src/clients/`

### Task 2.2: Convert summarizer.py to async
- **File:** `src/processing/summarizer.py`
- **What:** Replace `anthropic.Anthropic()` with shared async client from Task 2.1
- **Changes:**
  1. `extract_sentiment()` -> `async def extract_sentiment()` using `await client.messages.create()`
  2. `summarize_report()` -> `async def summarize_report()` using `await client.messages.create()`
  3. Remove per-call client creation
- **Callers to update:** `src/processing/pipeline.py:30` (already in async context, just needs `await`)
- **Tests to update:** `tests/test_summarizer.py` — update mock to patch the shared client, make tests async
- **Validation:** `pytest tests/test_summarizer.py -v`

### Task 2.3: Convert entity_extraction.py to async
- **File:** `src/processing/entity_extraction.py`
- **What:** `extract_player_mentions_claude()` uses sync Anthropic client
- **Changes:**
  1. `extract_player_mentions_claude()` -> `async def` using shared async client
  2. Remove per-call `anthropic.Anthropic()` creation
  3. `extract_player_mentions()` (regex) stays sync — it's pure logic
- **Callers to update:** `src/processing/entity_linking.py:34` — already async, just add `await`
- **Tests to update:** `tests/test_entity_extraction.py` — update Claude test to be async
- **Validation:** `pytest tests/test_entity_extraction.py -v`

### Task 2.4: Convert aggregation.py to async
- **File:** `src/processing/aggregation.py`
- **What:** `extract_traits_from_reports()` uses sync Anthropic client
- **Changes:**
  1. `extract_traits_from_reports()` -> `async def` using shared async client
  2. `aggregate_player_profile()` already async — just add `await` to trait extraction call
  3. Remove per-call client creation
- **Callers to update:** `src/processing/grading.py:42` — already async
- **Tests to update:** `tests/test_aggregation.py`
- **Validation:** `pytest tests/test_aggregation.py -v`

### Task 2.5: Convert embeddings.py to async
- **File:** `src/processing/embeddings.py`
- **What:** `generate_embedding()` uses sync `openai.OpenAI()` with lazy init
- **Changes:**
  1. Replace `openai.OpenAI()` with `openai.AsyncOpenAI()`
  2. `generate_embedding()` -> `async def generate_embedding()`
  3. Use `await client.embeddings.create()`
- **Callers to update:** `scripts/backfill_embeddings.py`, `src/processing/player_matching.py`
- **Tests to update:** `tests/test_embeddings.py` — update mock target and make generate tests async
- **Validation:** `pytest tests/test_embeddings.py -v`

### Task 2.6: Convert PFF client to async
- **File:** `src/clients/pff.py`
- **What:** Entire client uses sync `httpx.Client`
- **Changes:**
  1. Replace `httpx.Client` with `httpx.AsyncClient`
  2. All methods -> `async def`
  3. Add `async close()` method
  4. Update context manager to async
- **Tests to update:** `tests/test_pff_client.py`
- **Validation:** `pytest tests/test_pff_client.py -v`

### Task 2.7: Convert 247Sports crawler to async
- **File:** `src/crawlers/recruiting/two47.py`
- **What:** `_fetch_page()` and `crawl_team_commits()` use sync `httpx.Client` with blocking `time.sleep(2)`
- **Changes:**
  1. Replace `httpx.Client` with `httpx.AsyncClient`
  2. Replace `time.sleep(2)` with `await asyncio.sleep(2)`
  3. `_fetch_page()` -> `async def _fetch_page()`
  4. `crawl_team_commits()` -> `async def crawl_team_commits()`
- **Tests to update:** `tests/test_two47_crawler.py` (URL builders stay sync)
- **Validation:** `pytest tests/test_two47_crawler.py -v` and `ruff check src/crawlers/`

### Task 2.8: Update conftest.py mock strategy
- **File:** `tests/conftest.py`
- **What:** After Tasks 2.2-2.5, the Anthropic and OpenAI mocks need to target the new shared async clients
- **Changes:**
  1. Update `mock_anthropic` to patch `src.clients.anthropic.get_anthropic_client` (or wherever the shared client lives)
  2. Update mock to return `AsyncMock` for `messages.create`
  3. Update `mock_openai` to patch async OpenAI client
  4. Verify all autouse fixtures still intercept correctly
- **Validation:** `pytest -v` (full suite)

---

## Sprint 3: Complete Alert System
**Goal:** Wire all 5 alert types, integrate evaluation into pipeline, verify alerts fire correctly.

**Deliverable:** `run_pipeline.py --evaluate-alerts` triggers all alert types. Fired alerts appear in history.

### Task 3.1: Wire remaining alert types
- **File:** `src/processing/alerting.py`
- **What:** `process_alerts_for_player()` (around line 210-223) only handles `grade_change` and `status_change`. Three check functions exist but aren't called: `check_new_report_alert()`, `check_trend_change_alert()`, and portal_entry.
- **Fix:** Add the missing alert types to the `process_alerts_for_player()` dispatch:
  - `new_report`: Check if new reports exist for the player since last check
  - `trend_change`: Call existing `check_trend_change_alert()` with player trend data
  - `portal_entry`: Check transfer_events for recent portal entries
- **Validation:** Unit test each alert type fires when conditions are met

### Task 3.2: Add --evaluate-alerts to pipeline
- **File:** `scripts/run_pipeline.py`
- **What:** Add `--evaluate-alerts` CLI flag that calls `run_alert_check()` from `alerting.py`
- **Changes:**
  1. Add argparse argument `--evaluate-alerts`
  2. Import and call `run_alert_check()` when flag is set
  3. Also add it to the `--all` flow (after grading)
- **Validation:** `python scripts/run_pipeline.py --evaluate-alerts` runs without error

### Task 3.3: Write alert system tests
- **File:** `tests/test_alerting.py` (extend existing)
- **What:** Current tests only cover `check_grade_change_alert()`. Add tests for:
  1. `check_status_change_alert()` — triggers on status change, doesn't trigger on same status
  2. `check_new_report_alert()` — triggers when new reports exist
  3. `check_trend_change_alert()` — triggers on direction change
  4. `process_alerts_for_player()` — integration test dispatching to all types
  5. Edge cases: None inputs, zero threshold, equal values
- **Validation:** `pytest tests/test_alerting.py -v`

---

## Sprint 4: Test Hardening
**Goal:** Add pytest-cov, write tests for untested modules, add mutation endpoint tests, mock external HTTP.

**Deliverable:** Coverage above 70%. All API mutation endpoints tested. No untested core modules.

### Task 4.1: Add pytest-cov and coverage config
- **File:** `pyproject.toml`
- **What:** Add `pytest-cov` to dev dependencies and configure coverage settings
- **Changes:**
  1. Add `pytest-cov >= 5.0.0` to `[project.optional-dependencies.dev]`
  2. Add `[tool.coverage.run]` config: `source = ["src"]`, `omit = ["tests/*"]`
  3. Add `[tool.coverage.report]` config: `fail_under = 50` (start conservative), `show_missing = true`
  4. Update pytest config to include `--cov=src --cov-report=term-missing`
- **Validation:** `pip install -e ".[dev]" && pytest --cov=src`

### Task 4.2: Write tests for entity_linking.py
- **File:** New `tests/test_entity_linking.py`
- **What:** Zero tests exist for this core module
- **Tests to write:**
  1. `test_link_report_entities_with_match` — mock player_matching to return a match, verify upsert + link
  2. `test_link_report_entities_pending_review` — mock matching to return pending link, verify skipped
  3. `test_link_report_entities_no_match` — verify creates unlinked scouting player
  4. `test_link_report_entities_claude_extraction` — verify Claude path called when use_claude=True
  5. `test_run_entity_linking_batch` — verify batch processing with stats
- **Mock strategy:** Mock `player_matching.match_player_with_review`, `entity_extraction` functions, and DB functions
- **Validation:** `pytest tests/test_entity_linking.py -v`

### Task 4.3: Write tests for grading.py
- **File:** New `tests/test_grading.py`
- **What:** Zero tests exist for this core module
- **Tests to write:**
  1. `test_get_players_needing_update` — verify SQL query returns stale/ungraded players
  2. `test_update_player_grade` — mock aggregation, verify grade update + timeline snapshot created
  3. `test_run_grading_pipeline` — verify batch processing with error handling
  4. `test_update_player_grade_error_handling` — verify errors don't crash the pipeline
- **Mock strategy:** Mock `aggregation.aggregate_player_profile` and DB functions
- **Validation:** `pytest tests/test_grading.py -v`

### Task 4.4: Write mutation endpoint tests for API
- **File:** `tests/test_api.py` (extend)
- **What:** Only GET endpoints are tested. Add tests for POST/PUT/DELETE:
  1. `POST /watchlists` — create a watchlist, verify response
  2. `POST /watchlists/{id}/players/{pid}` — add player, verify 200
  3. `DELETE /watchlists/{id}/players/{pid}` — remove player, verify 200
  4. `DELETE /watchlists/{id}` — delete watchlist, verify 200
  5. `POST /alerts` — create alert with valid/invalid data
  6. `DELETE /alerts/{id}` — delete alert
  7. `POST /alerts/{id}/deactivate` — deactivate alert
  8. `POST /alerts/history/{id}/read` — mark alert read
  9. `GET /compare/{id1}/{id2}` — comparison endpoint
  10. `GET /players/{id}/similar` — similarity endpoint
  11. `POST /transfer-portal/snapshot` — snapshot generation
- **Validation:** `pytest tests/test_api.py -v`

### Task 4.5: Add httpx mocks for crawlers and PFF client
- **Files:** `tests/test_two47_crawler.py`, `tests/test_pff_client.py`
- **What:** Only URL builders and constructors are tested. Add HTTP-level tests.
- **For two47_crawler:**
  1. Mock `httpx.AsyncClient.get` to return sample HTML
  2. Test `_parse_commits_page()` with real HTML fixture
  3. Test `crawl_team_commits()` end-to-end with mocked HTTP
  4. Test error handling (HTTP 404, parse errors)
- **For pff_client:**
  1. Mock `httpx.AsyncClient` responses
  2. Test `get_player_grades()` with sample JSON
  3. Test `get_player_by_name()` with match and no-match
  4. Test error handling (HTTP errors, invalid JSON)
- **Validation:** `pytest tests/test_two47_crawler.py tests/test_pff_client.py -v`

---

## Sprint 5: Operations Foundation (Phase 6E)
**Goal:** Automate the daily pipeline with GitHub Actions and pg_cron. Add basic monitoring.

**Deliverable:** Pipeline runs daily without manual intervention. player_mart refreshes on schedule.

### Task 5.1: Create GitHub Actions daily pipeline workflow
- **File:** `.github/workflows/daily-pipeline.yml`
- **What:** Scheduled workflow that runs the full pipeline daily
- **Contents:**
  1. Cron trigger: `0 12 * * *` (7:00 AM CT = 12:00 UTC)
  2. Steps: checkout, setup Python 3.12, install deps, run pipeline stages in order
  3. Pipeline stages: `--crawl-247` -> `--process` -> `--link` -> `--grade` -> `--evaluate-alerts`
  4. Environment: secrets for `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
  5. Error handling: continue-on-error per stage, summary output at end
- **Validation:** Workflow file passes `actionlint` or manual review

### Task 5.2: Create GitHub Actions CI workflow
- **File:** `.github/workflows/ci.yml`
- **What:** Run tests and linting on every push/PR
- **Contents:**
  1. Trigger: push to main, pull requests
  2. Steps: checkout, setup Python 3.12, install dev deps, ruff check, ruff format --check, pytest
  3. Skip DB-dependent tests in CI (use marker `@pytest.mark.integration`)
- **Validation:** Push to trigger workflow

### Task 5.3: Configure pg_cron for player_mart refresh
- **What:** The `scouting.refresh_player_mart()` function exists (migration 006) but no cron job is configured
- **Approach:** Use Supabase dashboard or SQL to create the pg_cron job
- **SQL:**
  ```sql
  SELECT cron.schedule(
      'refresh-player-mart',
      '30 12 * * *',  -- 7:30 AM CT = 12:30 UTC (after pipeline completes)
      $$SELECT scouting.refresh_player_mart()$$
  );
  ```
- **Validation:** `SELECT * FROM cron.job;` shows the scheduled job

### Task 5.4: Add pipeline health logging
- **File:** `scripts/run_pipeline.py`
- **What:** Add structured logging output summarizing each pipeline stage result
- **Changes:**
  1. Configure logging format with timestamps
  2. After each stage, log JSON summary: `{"stage": "crawl-247", "status": "ok", "records": 15, "errors": 0}`
  3. At end, log overall summary with total time
  4. On critical failure, exit with non-zero code (for GitHub Actions failure detection)
- **Validation:** `python scripts/run_pipeline.py --process 2>&1 | grep '"stage"'`

---

## Sprint 6: PFF Pipeline & Performance
**Goal:** Connect PFF client to DB, fix N+1 queries, address in-memory scalability.

**Deliverable:** PFF grades flow into the system. Draft scores use full formula. Key queries optimized.

### Task 6.1: Build PFF fetch-to-store pipeline
- **File:** New `src/processing/pff_pipeline.py`
- **What:** Connect `src/clients/pff.py` to `src/storage/db.py`
- **Functions:**
  1. `fetch_and_store_pff_grades(player_id)` — calls PFF client, writes to `scouting.pff_grades`
  2. `run_pff_pipeline(batch_size)` — gets players needing PFF update, fetches grades in batch
- **Integration:** Add `--fetch-pff` flag to `scripts/run_pipeline.py`
- **Error handling:** Per-player try/except, rate limiting to respect PFF API limits
- **Tests:** Mock PFF client, verify grades written to DB
- **Validation:** `pytest tests/test_pff_pipeline.py -v`

### Task 6.2: Fix N+1 query in list_teams endpoint
- **File:** `src/api/main.py:152-201`
- **What:** Runs N+1 queries (1 for teams, N for top players per team)
- **Fix:** Replace with a single query using `ROW_NUMBER() OVER (PARTITION BY team ORDER BY composite_grade DESC)` window function to get top 3 players per team in one pass
- **Validation:** `pytest tests/test_api.py -k teams`

### Task 6.3: Fix N+1 query in draft board
- **File:** `src/processing/draft.py`
- **What:** `build_draft_board()` calls `get_player_pff_grades()` and `analyze_player_trend()` per player
- **Fix:** Batch-load PFF grades and trends for all candidate players in two queries, then join in-memory
- **Validation:** `pytest tests/test_draft.py -v`

### Task 6.4: Replace in-memory similarity with pgvector
- **File:** `src/processing/comparison.py`
- **What:** `find_similar_players()` loads ALL players into memory for numpy cosine similarity
- **Fix:** Use `scouting.player_embeddings` table with pgvector's `<=>` operator via `db.find_similar_by_embedding()` (already exists in db.py)
- **Validation:** `pytest tests/test_comparison.py -v`

---

## Task Dependency Graph

```
Sprint 1 (Quality Fixes)
  1.1 ──┐
  1.2 ──┤
  1.3 ──┼── All independent, can run in parallel
  1.4 ──┘

Sprint 2 (Async Migration)
  2.1 ──┬── 2.2 ──┐
        ├── 2.3 ──┤
        ├── 2.4 ──┼── 2.8 (update conftest after all conversions)
        └── 2.5 ──┤
  2.6 ────────────┤
  2.7 ────────────┘

Sprint 3 (Alerts) — depends on Sprint 2 (async clients)
  3.1 ──┬── 3.2
        └── 3.3

Sprint 4 (Tests) — depends on Sprint 2 (async mocks)
  4.1 ──┬── 4.2 ──┐
        ├── 4.3 ──┤
        ├── 4.4 ──┼── (all independent after 4.1)
        └── 4.5 ──┘

Sprint 5 (Operations) — depends on Sprint 3 (--evaluate-alerts)
  5.1 ──┐
  5.2 ──┤── All independent
  5.3 ──┤
  5.4 ──┘

Sprint 6 (PFF & Performance) — depends on Sprint 2 (async PFF client)
  6.1 ──┐
  6.2 ──┤── All independent
  6.3 ──┤
  6.4 ──┘
```

## Parallelization Strategy

For an agent team:

| Sprint | Parallelizable? | Strategy |
|--------|----------------|----------|
| Sprint 1 | **Yes** — 4 tasks, all independent | 4 agents in parallel |
| Sprint 2 | **Partial** — 2.1 first, then 2.2-2.7 in parallel, then 2.8 | 1 agent for 2.1, then 6 agents, then 1 for 2.8 |
| Sprint 3 | **Partial** — 3.1 first, then 3.2 + 3.3 in parallel | 1 agent then 2 agents |
| Sprint 4 | **Yes after 4.1** — 4.2-4.5 all independent | 1 agent for 4.1, then 4 agents |
| Sprint 5 | **Yes** — all 4 tasks independent | 4 agents in parallel |
| Sprint 6 | **Yes** — all 4 tasks independent | 4 agents in parallel |
