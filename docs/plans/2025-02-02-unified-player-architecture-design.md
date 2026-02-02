# Unified Player Architecture Design

**Date:** 2025-02-02
**Status:** Approved
**Author:** Rob Stover

## Overview

This design unifies the CFB infrastructure (cfb-database, cfb-scout, cfb-app) around a single player entity that combines demographics, stats, recruiting data, and scouting intelligence. The goal is to provide a seamless experience for college football fans who want both game analytics and player evaluations.

## Current State

```
cfb-database ──▶ Supabase ──▶ materialized views ──▶ cfb-app
                    │
cfb-scout ─────────┘ (scouting.* tables exist, but cfb-app doesn't use them)
```

**Components:**
- **cfb-database:** dlt pipelines loading CFBD API data (games, plays, rosters, recruiting, ratings)
- **cfb-scout:** Python/FastAPI scouting intelligence (crawlers, Claude processing, alerts, portal)
- **cfb-app:** Next.js frontend querying Supabase for team analytics

**Problem:** Data lives in separate schemas with no unified player entity. cfb-app can't show scouting data alongside stats.

## Target Architecture

```
┌─────────────┐     ┌──────────────────────────────────┐     ┌───────────┐
│cfb-database │────▶│           Supabase               │◀────│  cfb-app  │
│ (dlt pipes) │     │                                  │     │ (Next.js) │
└─────────────┘     │  ┌────────────────────────────┐  │     └───────────┘
                    │  │   scouting.player_mart     │  │
┌─────────────┐     │  │   (unified player entity)  │  │
│  cfb-scout  │────▶│  └────────────────────────────┘  │
│ (pipelines) │     │  ┌────────────────────────────┐  │
└─────────────┘     │  │ scouting.player_embeddings │  │
                    │  │   (vector similarity)      │  │
                    │  └────────────────────────────┘  │
                    └──────────────────────────────────┘
```

**Key changes:**
1. Unified Player Mart joins roster + recruits + stats + scouting
2. Vector embeddings enable semantic player matching
3. cfb-scout becomes pipeline-only (FastAPI deprecated)
4. cfb-app queries Supabase directly for all data

## Data Layer

### Unified Player Mart

**Location:** `scouting.player_mart` (materialized view)

**Sources:**

| Schema.Table | Data |
|--------------|------|
| `core.roster` | id, name, team, position, height, weight, hometown |
| `recruiting.recruits` | stars, rating, ranking, high_school, recruit_year |
| `stats.player_season_stats` | passing/rushing/receiving stats |
| `metrics.ppa_players_*` | PPA, usage rate |
| `scouting.players` | composite_grade, traits, draft_projection, comps |
| `scouting.transfer_events` | portal status, origin/destination |

**Canonical identifier:** `core.roster.id`

All other tables link to this via:
- `recruiting.recruits.athlete_id` → `roster.id`
- `stats.player_season_stats.player_id` → `roster.id`
- `scouting.players.roster_player_id` → `roster.id`

### Schema

```sql
CREATE MATERIALIZED VIEW scouting.player_mart AS
SELECT
  -- Identity (canonical)
  r.id AS player_id,
  r.first_name || ' ' || r.last_name AS name,
  r.team,
  r.position,
  r.year AS roster_year,

  -- Demographics
  r.height,
  r.weight,
  r.home_city,
  r.home_state,

  -- Recruiting
  rec.stars,
  rec.rating AS recruit_rating,
  rec.ranking AS national_ranking,
  rec.year AS recruit_class,

  -- Scouting
  sp.composite_grade,
  sp.traits,
  sp.draft_projection,

  -- Portal
  te.status AS portal_status,
  te.destination_team

FROM core.roster r
LEFT JOIN recruiting.recruits rec ON rec.athlete_id = r.id::text
LEFT JOIN scouting.players sp ON sp.roster_player_id = r.id::bigint
LEFT JOIN scouting.transfer_events te ON te.player_id = sp.id
WHERE r.year = (SELECT MAX(year) FROM core.roster);

-- Refresh nightly via pg_cron
```

## Player Matching System

### Three-Tier Matching

When cfb-scout ingests a player mention, it links to the canonical `roster.id` using:

```
Tier 1: Deterministic (instant, 100% confidence)
├── recruit.athlete_id → roster.id (60% of recruits have this)
└── Exact name + team + year match

Tier 2: Vector Similarity (fast, high confidence)
├── Embed query: "Arch Manning QB Texas 2023"
├── pgvector cosine search against player_embeddings
└── Accept if similarity > 0.92 AND team matches

Tier 3: Fuzzy + Manual Review
├── rapidfuzz token_sort_ratio as fallback
├── Matches 0.80-0.92 go to review queue
└── Store in scouting.pending_links for human review
```

### Vector Embeddings

**Extension:** pgvector (v0.8.0 available in Supabase)

**What's embedded:**
- Name (normalized)
- Position (standardized)
- Team
- Class year
- Hometown (optional)

**Schema:**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE scouting.player_embeddings (
  id SERIAL PRIMARY KEY,
  roster_id TEXT NOT NULL,
  identity_text TEXT NOT NULL,
  embedding vector(1536),  -- OpenAI text-embedding-3-small
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON scouting.player_embeddings
  USING hnsw (embedding vector_cosine_ops);

CREATE TABLE scouting.pending_links (
  id SERIAL PRIMARY KEY,
  source_name TEXT,
  source_team TEXT,
  source_context JSONB,
  candidate_roster_id TEXT,
  match_score FLOAT,
  match_method TEXT,  -- 'vector' | 'fuzzy'
  status TEXT DEFAULT 'pending',  -- pending | approved | rejected
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Embedding Generation

```python
def embed_player_identity(player: dict) -> list[float]:
    identity = f"{player['name']} | {player['position']} | {player['team']} | {player['year']}"
    if player.get('hometown'):
        identity += f" | {player['hometown']}"
    return openai.embeddings.create(
        model="text-embedding-3-small",
        input=identity
    ).data[0].embedding
```

## Similar Players Feature

**Use case:** "Couch cushion GM" - Find replacement for graduating players

**Function:**

```sql
CREATE FUNCTION scouting.find_similar_players(
  target_player_id TEXT,
  limit_count INT DEFAULT 10,
  filter_portal BOOLEAN DEFAULT FALSE,
  filter_recruits BOOLEAN DEFAULT FALSE
) RETURNS TABLE (
  player_id TEXT,
  name TEXT,
  team TEXT,
  position TEXT,
  similarity FLOAT,
  stars INT,
  portal_status TEXT
) AS $$
  WITH target AS (
    SELECT embedding FROM scouting.player_embeddings
    WHERE roster_id = target_player_id
  )
  SELECT
    pm.player_id,
    pm.name,
    pm.team,
    pm.position,
    1 - (pe.embedding <=> (SELECT embedding FROM target)) as similarity,
    pm.stars,
    pm.portal_status
  FROM scouting.player_embeddings pe
  JOIN scouting.player_mart pm ON pe.roster_id = pm.player_id
  WHERE pe.roster_id != target_player_id
    AND (NOT filter_portal OR pm.portal_status = 'entered')
    AND (NOT filter_recruits OR pm.recruit_class = EXTRACT(YEAR FROM NOW()) + 1)
  ORDER BY pe.embedding <=> (SELECT embedding FROM target)
  LIMIT limit_count;
$$ LANGUAGE sql;
```

**What's embedded for similarity:**
- Physical profile (height, weight)
- Position + position archetype
- Playing style traits
- Production stats (normalized)
- Recruiting pedigree

## cfb-app Integration

**Query patterns:**

| Use Case | Query |
|----------|-------|
| Player profile | `SELECT * FROM scouting.player_mart WHERE player_id = ?` |
| Team roster | `SELECT * FROM scouting.player_mart WHERE team = ?` |
| Portal tracker | `SELECT * FROM scouting.player_mart WHERE portal_status = 'entered'` |
| Similar players | `SELECT * FROM scouting.find_similar_players(?)` |

**cfb-scout FastAPI:** Deprecated. cfb-app reads Supabase directly.

**cfb-scout role:** Pipeline/CLI tool only:
- Runs crawlers (247, portal sources)
- Processes reports through Claude
- Updates `scouting.*` tables
- Triggers embedding generation

## Operations

### Daily Pipeline Cadence

```
6:00 AM   cfb-database: dlt pipelines refresh CFBD data
6:30 AM   cfb-scout: generate embeddings for new players
7:00 AM   cfb-scout: crawl 247Sports, portal sources
7:30 AM   Supabase: REFRESH MATERIALIZED VIEW player_mart
On-demand: Alert evaluation after mart refresh
```

### Orchestration

- **pg_cron:** Mat view refresh (pure SQL)
- **GitHub Actions:** Python pipelines (dlt, crawlers, embeddings)

### GitHub Actions Workflow

```yaml
name: Daily CFB Pipeline
on:
  schedule:
    - cron: '0 12 * * *'  # 6 AM CT
  workflow_dispatch:

jobs:
  refresh-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run cfb-database pipelines
        run: |
          pip install -e .
          python -m src.pipelines.run --source games --mode incremental
          python -m src.pipelines.run --source roster

      - name: Run cfb-scout pipelines
        run: |
          pip install -e .
          python scripts/run_pipeline.py --crawl-247 --process --link --embed
```

## Implementation Phases

### Phase 6A: Foundation
- Enable `pgvector` extension
- Create `scouting.player_embeddings` table
- Create `scouting.pending_links` table
- Build embedding generation script
- Backfill embeddings for current roster + recruits (~30K players)

### Phase 6B: Unified Player Mart
- Create `scouting.player_mart` materialized view
- Set up `pg_cron` for nightly refresh
- Add indexes for common query patterns

### Phase 6C: Enhanced Matching
- Update cfb-scout's `player_matching.py` with 3-tier system
- Add vector similarity search tier
- Build pending_links review queue

### Phase 6D: cfb-app Integration
- Add player profile page using `player_mart`
- Add "Find Similar Players" component
- Add portal tracker view
- Deprecate cfb-scout FastAPI

### Phase 6E: Operations
- Set up GitHub Actions for daily pipelines
- Configure `pg_cron` for mat view refresh
- Add monitoring/alerting for pipeline failures

## Cleanup

- Delete `cfb-analytics` project (stale)

## Component Summary

| Component | Role |
|-----------|------|
| **cfb-database** | ETL from CFBD API → Supabase (dlt pipelines) |
| **cfb-scout** | Scouting pipelines: crawlers, Claude processing, embeddings |
| **Supabase** | Unified data layer: CFBD + scouting + player_mart + vectors |
| **cfb-app** | User-facing Next.js app, queries Supabase directly |
