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
```

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
cfb-scout/
├── src/
│   ├── crawlers/       # Data source crawlers
│   │   ├── base.py         # BaseCrawler, CrawlResult
│   │   └── recruiting/     # Recruiting site crawlers
│   │       └── two47.py    # 247Sports commits crawler
│   ├── processing/     # Processing pipeline
│   │   ├── summarizer.py       # Sentiment & summary extraction
│   │   ├── pipeline.py         # Batch processing orchestration
│   │   ├── entity_extraction.py # Player name extraction (regex + Claude)
│   │   ├── entity_linking.py   # Connect reports to player profiles
│   │   └── player_matching.py  # Fuzzy matching against roster/recruits
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

## Phase 2 Status

- [x] 247Sports commits crawler
- [x] Player entity extraction (regex + Claude)
- [x] Fuzzy name matching against roster/recruits
- [x] Scouting player profile creation
- [x] Report-to-player linking

## Next Steps (Phase 3)

- Player profile aggregation and grading
- Trend analysis over time
- Dashboard/API for querying scouting data
