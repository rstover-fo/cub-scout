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

# Process unprocessed reports through Claude
python scripts/run_pipeline.py --process

# Run full pipeline (seed + process)
python scripts/run_pipeline.py --all
```

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
cfb-scout/
├── src/
│   ├── crawlers/       # Data source crawlers (Reddit pending)
│   ├── processing/     # Claude summarization pipeline
│   │   ├── summarizer.py   # Sentiment & summary extraction
│   │   └── pipeline.py     # Batch processing orchestration
│   └── storage/        # Database operations
│       ├── db.py           # Connection & CRUD helpers
│       └── schema.sql      # Supabase schema
├── scripts/            # CLI tools
│   └── run_pipeline.py     # Main entry point
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

## Next Steps (Phase 2)

- Add 247Sports scraper
- Entity linking to existing roster data
- Player profile aggregation
