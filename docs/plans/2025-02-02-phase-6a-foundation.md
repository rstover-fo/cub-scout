# Phase 6A: Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable pgvector in Supabase and build the embedding infrastructure for semantic player matching.

**Architecture:** Player identities are embedded as vectors using OpenAI's text-embedding-3-small model. Embeddings are stored in Supabase with HNSW indexes for fast similarity search. A pending_links table captures uncertain matches for human review.

**Tech Stack:** Python 3.12, psycopg2, OpenAI API, pgvector, Supabase

---

## Task 1: Add OpenAI Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add openai to dependencies**

Edit `pyproject.toml` to add the OpenAI package:

```toml
dependencies = [
    "praw>=7.7.0",
    "anthropic>=0.18.0",
    "psycopg2-binary>=2.9.9",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",
    "rapidfuzz>=3.6.0",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "numpy>=1.26.0",
    "openai>=1.12.0",
]
```

**Step 2: Reinstall package**

Run: `cd /Users/robstover/Development/personal/cfb-scout && pip install -e ".[dev]"`

Expected: Successfully installed openai

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add openai dependency for embeddings"
```

---

## Task 2: Enable pgvector Extension

**Files:**
- Create: `src/storage/migrations/001_enable_pgvector.sql`

**Step 1: Create migration file**

```sql
-- Enable pgvector extension for semantic player matching
-- Run via Supabase SQL Editor or psql

CREATE EXTENSION IF NOT EXISTS vector;
```

**Step 2: Apply migration via Supabase MCP**

Use the Supabase MCP tool:
```
mcp__supabase__apply_migration(
  name="enable_pgvector",
  query="CREATE EXTENSION IF NOT EXISTS vector;"
)
```

**Step 3: Verify extension is enabled**

```
mcp__supabase__execute_sql(
  query="SELECT * FROM pg_extension WHERE extname = 'vector';"
)
```

Expected: One row showing vector extension

**Step 4: Commit**

```bash
mkdir -p src/storage/migrations
git add src/storage/migrations/001_enable_pgvector.sql
git commit -m "feat: enable pgvector extension for embeddings"
```

---

## Task 3: Create player_embeddings Table

**Files:**
- Create: `src/storage/migrations/002_player_embeddings.sql`

**Step 1: Create migration file**

```sql
-- Player identity embeddings for semantic matching
-- Uses OpenAI text-embedding-3-small (1536 dimensions)

CREATE TABLE IF NOT EXISTS scouting.player_embeddings (
    id SERIAL PRIMARY KEY,
    roster_id TEXT NOT NULL,
    identity_text TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_player_embeddings_hnsw
    ON scouting.player_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- Index for roster_id lookups
CREATE INDEX IF NOT EXISTS idx_player_embeddings_roster
    ON scouting.player_embeddings (roster_id);

-- Prevent duplicate embeddings per roster player
CREATE UNIQUE INDEX IF NOT EXISTS idx_player_embeddings_unique_roster
    ON scouting.player_embeddings (roster_id);
```

**Step 2: Apply migration via Supabase MCP**

```
mcp__supabase__apply_migration(
  name="create_player_embeddings",
  query=<the SQL above>
)
```

**Step 3: Verify table exists**

```
mcp__supabase__execute_sql(
  query="SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'scouting' AND table_name = 'player_embeddings';"
)
```

Expected: 5 columns (id, roster_id, identity_text, embedding, created_at)

**Step 4: Commit**

```bash
git add src/storage/migrations/002_player_embeddings.sql
git commit -m "feat: add player_embeddings table with pgvector"
```

---

## Task 4: Create pending_links Table

**Files:**
- Create: `src/storage/migrations/003_pending_links.sql`

**Step 1: Create migration file**

```sql
-- Pending player links for manual review
-- Captures uncertain matches from fuzzy/vector matching

CREATE TABLE IF NOT EXISTS scouting.pending_links (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_team TEXT,
    source_context JSONB DEFAULT '{}',
    candidate_roster_id TEXT,
    match_score FLOAT,
    match_method TEXT CHECK (match_method IN ('vector', 'fuzzy', 'deterministic')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_links_status
    ON scouting.pending_links (status)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pending_links_created
    ON scouting.pending_links (created_at DESC);
```

**Step 2: Apply migration via Supabase MCP**

```
mcp__supabase__apply_migration(
  name="create_pending_links",
  query=<the SQL above>
)
```

**Step 3: Verify table exists**

```
mcp__supabase__execute_sql(
  query="SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'scouting' AND table_name = 'pending_links';"
)
```

Expected: 10 columns

**Step 4: Commit**

```bash
git add src/storage/migrations/003_pending_links.sql
git commit -m "feat: add pending_links table for match review queue"
```

---

## Task 5: Write Failing Test for Embedding Module

**Files:**
- Create: `tests/test_embeddings.py`

**Step 1: Write the failing test**

```python
"""Tests for player embedding generation."""

import pytest
from unittest.mock import patch, MagicMock

from src.processing.embeddings import (
    build_identity_text,
    generate_embedding,
    EmbeddingResult,
)


def test_build_identity_text_basic():
    """Test building identity text from player dict."""
    player = {
        "name": "Arch Manning",
        "position": "QB",
        "team": "Texas",
        "year": 2024,
    }
    result = build_identity_text(player)
    assert result == "Arch Manning | QB | Texas | 2024"


def test_build_identity_text_with_hometown():
    """Test identity text includes hometown when present."""
    player = {
        "name": "Arch Manning",
        "position": "QB",
        "team": "Texas",
        "year": 2024,
        "hometown": "New Orleans, LA",
    }
    result = build_identity_text(player)
    assert result == "Arch Manning | QB | Texas | 2024 | New Orleans, LA"


def test_build_identity_text_missing_fields():
    """Test identity text handles missing optional fields."""
    player = {
        "name": "John Smith",
        "team": "Alabama",
        "year": 2024,
    }
    result = build_identity_text(player)
    assert result == "John Smith | Alabama | 2024"


@patch("src.processing.embeddings.openai_client")
def test_generate_embedding_returns_result(mock_client):
    """Test generating embedding returns EmbeddingResult."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response

    result = generate_embedding("Arch Manning | QB | Texas | 2024")

    assert isinstance(result, EmbeddingResult)
    assert len(result.embedding) == 1536
    assert result.identity_text == "Arch Manning | QB | Texas | 2024"


@patch("src.processing.embeddings.openai_client")
def test_generate_embedding_calls_openai(mock_client):
    """Test that generate_embedding calls OpenAI with correct params."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response

    generate_embedding("test text")

    mock_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input="test text",
    )
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/robstover/Development/personal/cfb-scout && pytest tests/test_embeddings.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.processing.embeddings'"

**Step 3: Commit failing test**

```bash
git add tests/test_embeddings.py
git commit -m "test: add failing tests for embedding module"
```

---

## Task 6: Implement Embedding Module

**Files:**
- Create: `src/processing/embeddings.py`

**Step 1: Write minimal implementation**

```python
"""Player identity embedding generation using OpenAI."""

import os
from dataclasses import dataclass

from openai import OpenAI

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""

    identity_text: str
    embedding: list[float]


def build_identity_text(player: dict) -> str:
    """Build identity text string from player data.

    Format: "Name | Position | Team | Year | Hometown"
    Missing fields are omitted.

    Args:
        player: Dict with keys: name, team, year, and optionally
                position, hometown

    Returns:
        Identity string for embedding
    """
    parts = [player["name"]]

    if player.get("position"):
        parts.append(player["position"])

    parts.append(player["team"])
    parts.append(str(player["year"]))

    if player.get("hometown"):
        parts.append(player["hometown"])

    return " | ".join(parts)


def generate_embedding(identity_text: str) -> EmbeddingResult:
    """Generate embedding vector for identity text.

    Args:
        identity_text: Player identity string

    Returns:
        EmbeddingResult with text and 1536-dim vector
    """
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=identity_text,
    )

    return EmbeddingResult(
        identity_text=identity_text,
        embedding=response.data[0].embedding,
    )
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/robstover/Development/personal/cfb-scout && pytest tests/test_embeddings.py -v`

Expected: All 5 tests PASS

**Step 3: Run linter**

Run: `cd /Users/robstover/Development/personal/cfb-scout && ruff check src/processing/embeddings.py`

Expected: No errors

**Step 4: Commit**

```bash
git add src/processing/embeddings.py
git commit -m "feat: add embedding generation module"
```

---

## Task 7: Write Failing Test for DB Embedding Functions

**Files:**
- Modify: `tests/test_embeddings.py`

**Step 1: Add database function tests**

Append to `tests/test_embeddings.py`:

```python
# Additional tests for database functions

def test_upsert_player_embedding_new(mock_db_connection):
    """Test inserting a new player embedding."""
    from src.storage.db import upsert_player_embedding

    embedding_id = upsert_player_embedding(
        conn=mock_db_connection,
        roster_id="12345",
        identity_text="Arch Manning | QB | Texas | 2024",
        embedding=[0.1] * 1536,
    )

    assert embedding_id > 0


def test_get_player_embedding(mock_db_connection):
    """Test retrieving a player embedding by roster_id."""
    from src.storage.db import upsert_player_embedding, get_player_embedding

    upsert_player_embedding(
        conn=mock_db_connection,
        roster_id="12345",
        identity_text="Arch Manning | QB | Texas | 2024",
        embedding=[0.1] * 1536,
    )

    result = get_player_embedding(mock_db_connection, roster_id="12345")

    assert result is not None
    assert result["roster_id"] == "12345"
    assert result["identity_text"] == "Arch Manning | QB | Texas | 2024"


def test_find_similar_by_embedding(mock_db_connection):
    """Test finding similar players by embedding vector."""
    from src.storage.db import upsert_player_embedding, find_similar_by_embedding

    # Insert a few players
    upsert_player_embedding(
        conn=mock_db_connection,
        roster_id="111",
        identity_text="Player One | QB | Texas | 2024",
        embedding=[0.1] * 1536,
    )
    upsert_player_embedding(
        conn=mock_db_connection,
        roster_id="222",
        identity_text="Player Two | QB | Texas | 2024",
        embedding=[0.11] * 1536,  # Similar
    )
    upsert_player_embedding(
        conn=mock_db_connection,
        roster_id="333",
        identity_text="Player Three | RB | Alabama | 2024",
        embedding=[0.9] * 1536,  # Different
    )

    # Search for similar to first player
    results = find_similar_by_embedding(
        conn=mock_db_connection,
        embedding=[0.1] * 1536,
        limit=2,
        exclude_roster_id="111",
    )

    assert len(results) == 2
    # Player Two should be most similar
    assert results[0]["roster_id"] == "222"
```

**Step 2: Add mock fixture to conftest.py**

We need a real database connection for these tests. Update `tests/conftest.py`:

```python
"""Pytest configuration for cfb-scout tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


@pytest.fixture
def mock_db_connection():
    """Provide a database connection for tests.

    Uses real database - tests that modify data should clean up.
    """
    from src.storage.db import get_connection

    conn = get_connection()
    yield conn
    conn.close()
```

**Step 3: Run test to verify it fails**

Run: `cd /Users/robstover/Development/personal/cfb-scout && pytest tests/test_embeddings.py::test_upsert_player_embedding_new -v`

Expected: FAIL with "cannot import name 'upsert_player_embedding' from 'src.storage.db'"

**Step 4: Commit failing tests**

```bash
git add tests/test_embeddings.py tests/conftest.py
git commit -m "test: add failing tests for embedding db functions"
```

---

## Task 8: Implement DB Embedding Functions

**Files:**
- Modify: `src/storage/db.py`

**Step 1: Add embedding database functions**

Append to `src/storage/db.py`:

```python
# Embedding functions


def upsert_player_embedding(
    conn: connection,
    roster_id: str,
    identity_text: str,
    embedding: list[float],
) -> int:
    """Upsert a player embedding.

    Args:
        conn: Database connection
        roster_id: The canonical roster ID
        identity_text: The text that was embedded
        embedding: The 1536-dim vector

    Returns:
        The embedding record ID
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.player_embeddings (roster_id, identity_text, embedding)
        VALUES (%s, %s, %s)
        ON CONFLICT (roster_id) DO UPDATE SET
            identity_text = EXCLUDED.identity_text,
            embedding = EXCLUDED.embedding,
            created_at = NOW()
        RETURNING id
        """,
        (roster_id, identity_text, embedding),
    )
    embedding_id = cur.fetchone()[0]
    conn.commit()
    return embedding_id


def get_player_embedding(
    conn: connection,
    roster_id: str,
) -> dict | None:
    """Get embedding for a roster player.

    Args:
        conn: Database connection
        roster_id: The roster ID to look up

    Returns:
        Dict with id, roster_id, identity_text, created_at or None
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, roster_id, identity_text, created_at
        FROM scouting.player_embeddings
        WHERE roster_id = %s
        """,
        (roster_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def find_similar_by_embedding(
    conn: connection,
    embedding: list[float],
    limit: int = 10,
    exclude_roster_id: str | None = None,
) -> list[dict]:
    """Find similar players by embedding vector.

    Uses cosine distance for similarity (lower = more similar).

    Args:
        conn: Database connection
        embedding: Query embedding vector
        limit: Max results to return
        exclude_roster_id: Optional roster_id to exclude from results

    Returns:
        List of dicts with roster_id, identity_text, similarity score
    """
    cur = conn.cursor()

    query = """
        SELECT
            roster_id,
            identity_text,
            1 - (embedding <=> %s::vector) as similarity
        FROM scouting.player_embeddings
        WHERE 1=1
    """
    params = [embedding]

    if exclude_roster_id:
        query += " AND roster_id != %s"
        params.append(exclude_roster_id)

    query += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params.extend([embedding, limit])

    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def insert_pending_link(
    conn: connection,
    source_name: str,
    source_team: str | None,
    source_context: dict | None,
    candidate_roster_id: str | None,
    match_score: float,
    match_method: str,
) -> int:
    """Insert a pending link for review.

    Args:
        conn: Database connection
        source_name: Name from source data
        source_team: Team from source data
        source_context: Additional context as JSON
        candidate_roster_id: Best matching roster ID
        match_score: Confidence score (0-1)
        match_method: 'vector', 'fuzzy', or 'deterministic'

    Returns:
        The pending link ID
    """
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.pending_links
            (source_name, source_team, source_context, candidate_roster_id,
             match_score, match_method)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            source_name,
            source_team,
            json.dumps(source_context) if source_context else None,
            candidate_roster_id,
            match_score,
            match_method,
        ),
    )
    link_id = cur.fetchone()[0]
    conn.commit()
    return link_id


def get_pending_links(
    conn: connection,
    status: str = "pending",
    limit: int = 100,
) -> list[dict]:
    """Get pending links for review.

    Args:
        conn: Database connection
        status: Filter by status ('pending', 'approved', 'rejected')
        limit: Max results

    Returns:
        List of pending link dicts
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_name, source_team, source_context,
               candidate_roster_id, match_score, match_method,
               status, created_at
        FROM scouting.pending_links
        WHERE status = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (status, limit),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def update_pending_link_status(
    conn: connection,
    link_id: int,
    status: str,
) -> None:
    """Update pending link status.

    Args:
        conn: Database connection
        link_id: The pending link ID
        status: New status ('approved' or 'rejected')
    """
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.pending_links
        SET status = %s, reviewed_at = NOW()
        WHERE id = %s
        """,
        (status, link_id),
    )
    conn.commit()
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/robstover/Development/personal/cfb-scout && pytest tests/test_embeddings.py -v`

Expected: All tests PASS (may skip DB tests if no connection)

**Step 3: Run linter**

Run: `cd /Users/robstover/Development/personal/cfb-scout && ruff check src/storage/db.py`

Expected: No errors

**Step 4: Commit**

```bash
git add src/storage/db.py
git commit -m "feat: add embedding and pending_links db functions"
```

---

## Task 9: Create Embedding Backfill Script

**Files:**
- Create: `scripts/backfill_embeddings.py`

**Step 1: Write the backfill script**

```python
#!/usr/bin/env python3
"""Backfill player embeddings for existing roster data.

Usage:
    python scripts/backfill_embeddings.py --year 2025 --batch-size 100
    python scripts/backfill_embeddings.py --year 2025 --dry-run
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.processing.embeddings import build_identity_text, generate_embedding
from src.storage.db import get_connection, upsert_player_embedding

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limiting: OpenAI allows 3000 RPM for text-embedding-3-small
REQUESTS_PER_MINUTE = 2500
DELAY_BETWEEN_BATCHES = 60 / (REQUESTS_PER_MINUTE / 100)  # seconds


def get_roster_players_without_embeddings(
    conn,
    year: int,
    limit: int = 1000,
) -> list[dict]:
    """Get roster players that don't have embeddings yet."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            r.id,
            r.first_name || ' ' || r.last_name as name,
            r.team,
            r.position,
            r.year,
            r.home_city || ', ' || r.home_state as hometown
        FROM core.roster r
        LEFT JOIN scouting.player_embeddings pe ON r.id = pe.roster_id
        WHERE r.year = %s
        AND pe.id IS NULL
        ORDER BY r.team, r.last_name
        LIMIT %s
        """,
        (year, limit),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def backfill_embeddings(
    year: int,
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict:
    """Backfill embeddings for roster players.

    Args:
        year: Roster year to process
        batch_size: Players per batch
        dry_run: If True, don't actually insert

    Returns:
        Stats dict with processed, skipped, errors counts
    """
    stats = {"processed": 0, "skipped": 0, "errors": 0}

    conn = get_connection()

    try:
        while True:
            players = get_roster_players_without_embeddings(conn, year, batch_size)

            if not players:
                logger.info("No more players to process")
                break

            logger.info(f"Processing batch of {len(players)} players")

            for player in players:
                try:
                    # Build identity text
                    identity_text = build_identity_text({
                        "name": player["name"],
                        "position": player["position"],
                        "team": player["team"],
                        "year": player["year"],
                        "hometown": player["hometown"] if player["hometown"] != ", " else None,
                    })

                    if dry_run:
                        logger.info(f"[DRY RUN] Would embed: {identity_text}")
                        stats["processed"] += 1
                        continue

                    # Generate embedding
                    result = generate_embedding(identity_text)

                    # Store in database
                    upsert_player_embedding(
                        conn=conn,
                        roster_id=str(player["id"]),
                        identity_text=result.identity_text,
                        embedding=result.embedding,
                    )

                    stats["processed"] += 1

                    if stats["processed"] % 100 == 0:
                        logger.info(f"Processed {stats['processed']} players")

                except Exception as e:
                    logger.error(f"Error processing {player['name']}: {e}")
                    stats["errors"] += 1

            # Rate limiting between batches
            if not dry_run and len(players) == batch_size:
                logger.info(f"Sleeping {DELAY_BETWEEN_BATCHES:.1f}s for rate limiting")
                time.sleep(DELAY_BETWEEN_BATCHES)

    finally:
        conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill player embeddings")
    parser.add_argument("--year", type=int, default=2025, help="Roster year")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)

    logger.info(f"Starting backfill for year {args.year}")
    stats = backfill_embeddings(
        year=args.year,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    logger.info(f"Completed: {stats}")


if __name__ == "__main__":
    main()
```

**Step 2: Make script executable**

Run: `chmod +x /Users/robstover/Development/personal/cfb-scout/scripts/backfill_embeddings.py`

**Step 3: Test dry run**

Run: `cd /Users/robstover/Development/personal/cfb-scout && python scripts/backfill_embeddings.py --year 2025 --batch-size 5 --dry-run`

Expected: Logs showing players that would be processed

**Step 4: Commit**

```bash
git add scripts/backfill_embeddings.py
git commit -m "feat: add embedding backfill script"
```

---

## Task 10: Add OPENAI_API_KEY to .env.example

**Files:**
- Modify: `.env.example` (create if doesn't exist)

**Step 1: Update .env.example**

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Anthropic (for Claude summarization)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (for embeddings)
OPENAI_API_KEY=sk-...

# Reddit (optional, for Reddit crawler)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=cfb-scout/1.0
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add OPENAI_API_KEY to .env.example"
```

---

## Task 11: Run Full Test Suite

**Files:**
- None (verification only)

**Step 1: Run all tests**

Run: `cd /Users/robstover/Development/personal/cfb-scout && pytest tests/ -v`

Expected: All tests pass

**Step 2: Run linter on all code**

Run: `cd /Users/robstover/Development/personal/cfb-scout && ruff check src/ tests/ && ruff format src/ tests/`

Expected: No errors, code formatted

**Step 3: Final commit if any formatting changes**

```bash
git add -A
git commit -m "style: format code" || echo "Nothing to commit"
```

---

## Task 12: Update README

**Files:**
- Modify: `README.md`

**Step 1: Add Phase 6A section to README**

Add after Phase 5 Status:

```markdown
## Phase 6A Status (Foundation)

- [x] pgvector extension enabled
- [x] player_embeddings table with HNSW index
- [x] pending_links table for review queue
- [x] Embedding generation module (OpenAI)
- [x] Database functions for embeddings
- [ ] Backfill embeddings for current roster (~30K players)
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with Phase 6A status"
```

---

## Summary

After completing all tasks:

1. **pgvector enabled** in Supabase
2. **player_embeddings table** with HNSW index for fast similarity search
3. **pending_links table** for uncertain match review
4. **embeddings.py module** for generating identity embeddings
5. **db.py extended** with embedding CRUD functions
6. **backfill_embeddings.py** script ready to populate vectors

**Next:** Run the backfill script to populate embeddings for ~30K roster players, then proceed to Phase 6B (Unified Player Mart).
