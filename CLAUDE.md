# CFB Scout

College football scouting intelligence agent. Crawls recruiting sites, extracts player entities, grades prospects, and serves data via API.

## Tech Stack

- Python 3.12, FastAPI, psycopg2 (connection pooling), anthropic, openai, pgvector
- Database: Supabase Postgres (`scouting` schema)
- LLM: Claude (model constant in `src/config.py` as `CLAUDE_MODEL`)

## Project Structure

```
src/
  api/          FastAPI app (main.py, models.py) - 29 endpoints
  clients/      External service clients (pff.py)
  crawlers/     Recruiting site crawlers (base.py, recruiting/)
  processing/   Entity extraction, grading, summarization, comparison,
                draft boards, transfer portal, trends, alerting, embeddings
  storage/      db.py (pooled connections, migrations, schema.sql)
  config.py     App config dataclass + CLAUDE_MODEL constant
```

## Key Commands

```bash
.venv/bin/ruff check .              # Lint
.venv/bin/ruff format --check .     # Format check
.venv/bin/pytest -q                 # Tests
uvicorn src.api.main:app --reload   # Dev server
```

## Git Conventions

- Branch names: `feature/`, `fix/`, `refactor/`, `chore/` prefixes
- Commit messages: imperative mood, 50-char subject line

## Environment Variables

`DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
