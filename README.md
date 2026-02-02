# CFB Scout

AI-powered college football scouting intelligence agent.

## Setup

1. Create virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials:
   # - DATABASE_URL: Supabase connection string
   # - ANTHROPIC_API_KEY: Claude API key
   # - REDDIT_* (optional): Reddit API credentials when approved
   ```

3. Deploy schema (first time only):
   ```bash
   psql "$DATABASE_URL" -f src/storage/schema.sql
   ```
   Or use the Supabase SQL Editor.

## Usage

```bash
# Seed test data for development
python scripts/run_pipeline.py --seed

# Crawl 247Sports recruiting data
python scripts/run_pipeline.py --crawl-247 --teams texas ohio-state --years 2025

# Process reports through Claude summarization
python scripts/run_pipeline.py --process

# Link entities (connect reports to player profiles)
python scripts/run_pipeline.py --link

# Run full pipeline
python scripts/run_pipeline.py --all --teams texas --years 2025

# Run grading pipeline (update player grades)
python scripts/run_pipeline.py --grade

# Review pending player links (interactive)
python scripts/run_pipeline.py --review-links
```

## API Server

```bash
# Start the API server (development)
python scripts/run_api.py --reload

# Start on specific host/port
python scripts/run_api.py --host 0.0.0.0 --port 8080

# API docs available at http://localhost:8000/docs
```

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
cfb-scout/
├── src/
│   ├── api/            # REST API
│   │   ├── main.py         # FastAPI application
│   │   └── models.py       # Pydantic response models
│   ├── crawlers/       # Data source crawlers
│   │   ├── base.py         # BaseCrawler, CrawlResult
│   │   └── recruiting/     # Recruiting site crawlers
│   │       └── two47.py    # 247Sports commits crawler
│   ├── processing/     # Processing pipeline
│   │   ├── summarizer.py       # Sentiment & summary extraction
│   │   ├── pipeline.py         # Batch processing orchestration
│   │   ├── entity_extraction.py # Player name extraction (regex + Claude)
│   │   ├── entity_linking.py   # Connect reports to player profiles
│   │   ├── player_matching.py  # 3-tier matching (deterministic/vector/fuzzy)
│   │   ├── aggregation.py      # Player profile aggregation
│   │   └── grading.py          # Grading pipeline
│   └── storage/        # Database operations
│       ├── db.py           # Connection & CRUD helpers
│       └── schema.sql      # Supabase schema
├── scripts/            # CLI tools
│   ├── run_pipeline.py     # Main pipeline entry point
│   └── run_api.py          # API server launcher
└── tests/              # Test suite
```

## Database Schema

All tables live in the `scouting` schema:

- **reports** - Raw crawled content with summaries
- **players** - Player scouting profiles with grades/traits
- **player_timeline** - Longitudinal tracking snapshots
- **team_rosters** - Position group analysis
- **crawl_jobs** - Crawl job tracking

## Phase 1 Status

- [x] Schema deployed to Supabase
- [x] Claude summarization working
- [x] Processing pipeline functional
- [ ] Reddit crawler (awaiting API approval)
- [x] End-to-end pipeline verified

## Phase 2 Status

- [x] 247Sports commits crawler
- [x] Player entity extraction (regex + Claude)
- [x] Fuzzy name matching against roster/recruits
- [x] Scouting player profile creation
- [x] Report-to-player linking

## Phase 3 Status

- [x] Player profile aggregation
- [x] Composite grading system
- [x] Timeline tracking snapshots
- [x] FastAPI REST endpoints
- [x] Player/team query API

## Phase 4 Status

- [x] PFF API integration
- [x] Trend analysis (rising/falling stocks)
- [x] Player comparison engine
- [x] Watch lists
- [x] Draft board with projections

## Phase 5 Status

- [x] Alert system (grade/status/report changes)
- [x] Alert history and notifications
- [x] Transfer portal tracking
- [x] Destination predictions
- [x] Team portal impact analysis

## Phase 6A Status (Foundation)

- [x] pgvector extension enabled
- [x] player_embeddings table with HNSW index
- [x] pending_links table for review queue
- [x] Embedding generation module (OpenAI)
- [x] Database functions for embeddings
- [x] Backfill embeddings for current roster (in progress)

## Phase 6B Status (Unified Player Mart)

- [x] player_mart materialized view (30K players)
- [x] Joins roster, recruiting, scouting, portal data
- [x] Indexes for team/position/portal queries
- [x] Refresh function (CONCURRENTLY)
- [x] pg_cron nightly refresh (7:30 AM CT)

## Phase 6C Status (Enhanced Matching)

- [x] Tier 1: Deterministic matching (exact name+team+year, athlete_id)
- [x] Tier 2: Vector similarity via pgvector (>= 0.92 threshold)
- [x] Tier 3: Fuzzy fallback with rapidfuzz
- [x] Pending links review queue for 0.80-0.92 confidence
- [x] CLI command: `--review-links`

## API Endpoints

### Players
- `GET /players` - List players with filters
- `GET /players/{id}` - Player detail with timeline
- `GET /players/{id}/trend` - Player trend analysis
- `GET /players/{id}/similar` - Find similar players

### Teams
- `GET /teams` - Team summaries
- `GET /teams/{name}/players` - Team roster

### Trends
- `GET /trends/rising` - Players with rising grades
- `GET /trends/falling` - Players with falling grades

### Comparisons
- `GET /compare/{id1}/{id2}` - Head-to-head comparison

### Watch Lists
- `GET /watchlists?user_id=X` - User's watch lists
- `POST /watchlists?user_id=X` - Create watch list
- `POST /watchlists/{id}/players/{player_id}` - Add to list
- `DELETE /watchlists/{id}/players/{player_id}` - Remove from list
- `DELETE /watchlists/{id}` - Delete list

### Draft Board
- `GET /draft/board` - Full draft rankings
- `GET /draft/position/{pos}` - Position rankings

### Alerts
- `GET /alerts?user_id=X` - User's active alerts
- `POST /alerts?user_id=X` - Create alert rule
- `DELETE /alerts/{id}` - Delete alert
- `POST /alerts/{id}/deactivate` - Deactivate alert
- `GET /alerts/history?user_id=X` - Fired alerts
- `POST /alerts/history/{id}/read` - Mark as read

### Transfer Portal
- `GET /transfer-portal/active` - Current portal players
- `GET /transfer-portal/player/{id}` - Player transfer history
- `GET /transfer-portal/player/{id}/predict` - Destination predictions
- `GET /teams/{name}/transfers` - Team transfer activity
- `GET /teams/{name}/portal-impact` - Portal impact analysis
- `POST /transfer-portal/snapshot` - Generate daily snapshot
