# CFB Scout Agent Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add player profile aggregation, grading system, timeline tracking, and a FastAPI-based query API for scouting data.

**Architecture:** Aggregation pipeline collects all reports linked to a player, uses Claude to extract traits and calculate composite grades. Timeline snapshots capture player state over time. FastAPI provides REST endpoints for querying players, teams, and trends. All data stored in existing `scouting.*` schema tables.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Anthropic SDK, psycopg2, pydantic

---

## Task 1: Add FastAPI Dependencies

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/pyproject.toml`

**Step 1: Add fastapi and uvicorn**

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
]
```

**Step 2: Install updated dependencies**

```bash
cd /Users/robstover/Development/personal/cfb-scout
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: All packages install successfully.

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add fastapi and uvicorn dependencies"
```

---

## Task 2: Create Player Aggregation Module

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/aggregation.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_aggregation.py`

**Step 1: Write failing test for report aggregation**

```python
# tests/test_aggregation.py
"""Tests for player aggregation."""

from src.processing.aggregation import (
    get_player_reports,
    calculate_sentiment_average,
    extract_traits_from_reports,
)


def test_calculate_sentiment_average_empty():
    """Test sentiment average with empty list."""
    result = calculate_sentiment_average([])
    assert result is None


def test_calculate_sentiment_average_values():
    """Test sentiment average calculation."""
    reports = [
        {"sentiment_score": 0.5},
        {"sentiment_score": 0.3},
        {"sentiment_score": -0.2},
    ]
    result = calculate_sentiment_average(reports)
    assert result == 0.2  # (0.5 + 0.3 + -0.2) / 3 = 0.2


def test_calculate_sentiment_average_skips_none():
    """Test that None values are skipped."""
    reports = [
        {"sentiment_score": 0.6},
        {"sentiment_score": None},
        {"sentiment_score": 0.4},
    ]
    result = calculate_sentiment_average(reports)
    assert result == 0.5  # (0.6 + 0.4) / 2
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_aggregation.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# src/processing/aggregation.py
"""Player profile aggregation from scouting reports."""

import logging
import os
from decimal import Decimal

import anthropic

from ..storage.db import get_connection

logger = logging.getLogger(__name__)


def get_player_reports(player_id: int) -> list[dict]:
    """Get all reports linked to a player."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, source_url, source_name, raw_text, summary,
                   sentiment_score, crawled_at
            FROM scouting.reports
            WHERE %s = ANY(player_ids)
            ORDER BY crawled_at DESC
            """,
            (player_id,),
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def calculate_sentiment_average(reports: list[dict]) -> float | None:
    """Calculate average sentiment from reports."""
    scores = [
        float(r["sentiment_score"])
        for r in reports
        if r.get("sentiment_score") is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def extract_traits_from_reports(reports: list[dict]) -> dict:
    """Use Claude to extract player traits from report summaries.

    Returns dict with trait categories and ratings.
    """
    if not reports:
        return {}

    summaries = "\n\n".join(
        f"- {r.get('summary', r.get('raw_text', ''))[:500]}"
        for r in reports[:10]  # Limit to recent 10
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": f"""Analyze these scouting reports and extract player traits.

Reports:
{summaries}

Return a JSON object with trait categories as keys and ratings (1-10) as values.
Categories: arm_strength, accuracy, mobility, decision_making, leadership,
athleticism, technique, football_iq, consistency, upside

Only include traits that have evidence in the reports. Return only JSON, no other text.

Example: {{"arm_strength": 8, "mobility": 7, "leadership": 9}}""",
            }
        ],
    )

    try:
        import json

        response_text = response.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        return json.loads(response_text)
    except Exception as e:
        logger.warning(f"Failed to parse traits: {e}")
        return {}


def calculate_composite_grade(traits: dict, sentiment: float | None) -> int | None:
    """Calculate composite grade (0-100) from traits and sentiment."""
    if not traits:
        return None

    # Average trait scores (1-10 scale) -> 0-100
    trait_avg = sum(traits.values()) / len(traits)
    base_grade = int(trait_avg * 10)

    # Adjust for sentiment (-1 to 1 scale) -> +/- 5 points
    if sentiment is not None:
        sentiment_bonus = int(sentiment * 5)
        base_grade += sentiment_bonus

    return max(0, min(100, base_grade))


def aggregate_player_profile(player_id: int) -> dict:
    """Aggregate all data for a player profile.

    Returns dict with sentiment, traits, grade, and report count.
    """
    reports = get_player_reports(player_id)

    sentiment = calculate_sentiment_average(reports)
    traits = extract_traits_from_reports(reports)
    grade = calculate_composite_grade(traits, sentiment)

    return {
        "player_id": player_id,
        "report_count": len(reports),
        "sentiment_score": sentiment,
        "traits": traits,
        "composite_grade": grade,
    }
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_aggregation.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/aggregation.py tests/test_aggregation.py
git commit -m "feat: add player profile aggregation with traits extraction"
```

---

## Task 3: Create Timeline Snapshot Functions

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_timeline.py`

**Step 1: Write failing test**

```python
# tests/test_timeline.py
"""Tests for player timeline functions."""

from datetime import date

from src.storage.db import (
    get_connection,
    insert_timeline_snapshot,
    get_player_timeline,
)


def test_insert_timeline_snapshot():
    """Test inserting a timeline snapshot."""
    conn = get_connection()
    cur = conn.cursor()

    # Create temp player
    cur.execute(
        """
        INSERT INTO scouting.players (name, team, class_year)
        VALUES ('Timeline Test', 'Test Team', 2024)
        RETURNING id
        """
    )
    player_id = cur.fetchone()[0]
    conn.commit()

    try:
        snapshot_id = insert_timeline_snapshot(
            conn,
            player_id=player_id,
            snapshot_date=date.today(),
            status="active",
            sentiment_score=0.5,
            grade_at_time=75,
            traits_at_time={"arm_strength": 8},
            key_narratives=["Strong arm", "Good leader"],
            sources_count=5,
        )

        assert snapshot_id is not None
        assert snapshot_id > 0

    finally:
        # Cleanup
        cur.execute("DELETE FROM scouting.player_timeline WHERE player_id = %s", (player_id,))
        cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
        conn.commit()
        conn.close()


def test_get_player_timeline():
    """Test retrieving player timeline."""
    conn = get_connection()
    cur = conn.cursor()

    # Create temp player
    cur.execute(
        """
        INSERT INTO scouting.players (name, team, class_year)
        VALUES ('Timeline Test 2', 'Test Team', 2024)
        RETURNING id
        """
    )
    player_id = cur.fetchone()[0]
    conn.commit()

    try:
        # Insert two snapshots
        insert_timeline_snapshot(conn, player_id, date(2024, 1, 1), "active", 0.3, 70)
        insert_timeline_snapshot(conn, player_id, date(2024, 2, 1), "active", 0.5, 75)

        timeline = get_player_timeline(conn, player_id)

        assert len(timeline) == 2
        # Should be ordered newest first
        assert timeline[0]["grade_at_time"] == 75
        assert timeline[1]["grade_at_time"] == 70

    finally:
        cur.execute("DELETE FROM scouting.player_timeline WHERE player_id = %s", (player_id,))
        cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
        conn.commit()
        conn.close()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_timeline.py -v
```

Expected: FAIL with "cannot import name 'insert_timeline_snapshot'"

**Step 3: Add implementation to db.py**

Add to `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`:

```python
def insert_timeline_snapshot(
    conn: connection,
    player_id: int,
    snapshot_date: date,
    status: str | None = None,
    sentiment_score: float | None = None,
    grade_at_time: int | None = None,
    traits_at_time: dict | None = None,
    key_narratives: list[str] | None = None,
    sources_count: int | None = None,
) -> int:
    """Insert a player timeline snapshot."""
    import json
    from datetime import date

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.player_timeline
            (player_id, snapshot_date, status, sentiment_score,
             grade_at_time, traits_at_time, key_narratives, sources_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            player_id,
            snapshot_date,
            status,
            sentiment_score,
            grade_at_time,
            json.dumps(traits_at_time) if traits_at_time else None,
            key_narratives or [],
            sources_count or 0,
        ),
    )
    snapshot_id = cur.fetchone()[0]
    conn.commit()
    return snapshot_id


def get_player_timeline(
    conn: connection,
    player_id: int,
    limit: int = 30,
) -> list[dict]:
    """Get timeline snapshots for a player, newest first."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, player_id, snapshot_date, status, sentiment_score,
               grade_at_time, traits_at_time, key_narratives, sources_count
        FROM scouting.player_timeline
        WHERE player_id = %s
        ORDER BY snapshot_date DESC
        LIMIT %s
        """,
        (player_id, limit),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]
```

Also add the import at the top of db.py:

```python
from datetime import date
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_timeline.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/storage/db.py tests/test_timeline.py
git commit -m "feat: add timeline snapshot insert and retrieval functions"
```

---

## Task 4: Create Aggregation Pipeline Runner

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/grading.py`
- Modify: `/Users/robstover/Development/personal/cfb-scout/scripts/run_pipeline.py`

**Step 1: Create grading pipeline**

```python
# src/processing/grading.py
"""Player grading and timeline update pipeline."""

import logging
from datetime import date

from ..storage.db import (
    get_connection,
    upsert_scouting_player,
    insert_timeline_snapshot,
)
from .aggregation import aggregate_player_profile

logger = logging.getLogger(__name__)


def get_players_needing_update(limit: int = 50) -> list[dict]:
    """Get players who haven't been graded recently."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Players with reports but no grade, or stale grades
        cur.execute(
            """
            SELECT DISTINCT p.id, p.name, p.team, p.class_year
            FROM scouting.players p
            JOIN scouting.reports r ON p.id = ANY(r.player_ids)
            WHERE p.composite_grade IS NULL
               OR p.last_updated < NOW() - INTERVAL '7 days'
            ORDER BY p.last_updated ASC NULLS FIRST
            LIMIT %s
            """,
            (limit,),
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def update_player_grade(player_id: int) -> dict:
    """Aggregate reports, update grade, and create timeline snapshot."""
    conn = get_connection()

    try:
        # Get aggregated data
        agg = aggregate_player_profile(player_id)

        # Update player record
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE scouting.players
            SET composite_grade = %s,
                traits = %s,
                last_updated = NOW()
            WHERE id = %s
            """,
            (
                agg["composite_grade"],
                agg["traits"] if agg["traits"] else None,
                player_id,
            ),
        )
        conn.commit()

        # Create timeline snapshot
        insert_timeline_snapshot(
            conn,
            player_id=player_id,
            snapshot_date=date.today(),
            sentiment_score=agg["sentiment_score"],
            grade_at_time=agg["composite_grade"],
            traits_at_time=agg["traits"],
            sources_count=agg["report_count"],
        )

        return agg

    finally:
        conn.close()


def run_grading_pipeline(batch_size: int = 50) -> dict:
    """Run grading pipeline on players needing updates."""
    players = get_players_needing_update(batch_size)
    logger.info(f"Found {len(players)} players needing grade updates")

    updated = 0
    errors = 0

    for player in players:
        try:
            result = update_player_grade(player["id"])
            logger.debug(
                f"Updated {player['name']}: grade={result['composite_grade']}"
            )
            updated += 1
        except Exception as e:
            logger.error(f"Error grading {player['name']}: {e}")
            errors += 1

    return {
        "players_found": len(players),
        "players_updated": updated,
        "errors": errors,
    }
```

**Step 2: Update run_pipeline.py**

Add to imports:

```python
from src.processing.grading import run_grading_pipeline
```

Add to argparse:

```python
parser.add_argument(
    "--grade",
    action="store_true",
    help="Run grading pipeline to update player grades",
)
```

Add to main():

```python
if args.grade or args.all:
    logger.info("Running grading pipeline...")
    result = run_grading_pipeline(batch_size=args.batch_size)
    logger.info(f"Grading complete: {result['players_updated']} players updated")
```

**Step 3: Verify pipeline runs**

```bash
python scripts/run_pipeline.py --help
```

Expected: `--grade` option visible

**Step 4: Commit**

```bash
git add src/processing/grading.py scripts/run_pipeline.py
git commit -m "feat: add grading pipeline with timeline snapshots"
```

---

## Task 5: Create FastAPI Application Structure

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/api/__init__.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/src/api/main.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/src/api/models.py`

**Step 1: Create API package**

```bash
mkdir -p /Users/robstover/Development/personal/cfb-scout/src/api
touch /Users/robstover/Development/personal/cfb-scout/src/api/__init__.py
```

**Step 2: Create Pydantic models**

```python
# src/api/models.py
"""Pydantic models for API responses."""

from datetime import date, datetime
from pydantic import BaseModel


class PlayerSummary(BaseModel):
    """Brief player info for lists."""

    id: int
    name: str
    team: str | None
    position: str | None
    class_year: int | None
    composite_grade: int | None
    current_status: str | None


class PlayerDetail(BaseModel):
    """Full player profile."""

    id: int
    name: str
    team: str | None
    position: str | None
    class_year: int | None
    current_status: str | None
    composite_grade: int | None
    traits: dict | None
    draft_projection: str | None
    comps: list[str] | None
    roster_player_id: int | None
    recruit_id: int | None
    last_updated: datetime | None


class TimelineSnapshot(BaseModel):
    """Player timeline entry."""

    id: int
    snapshot_date: date
    status: str | None
    sentiment_score: float | None
    grade_at_time: int | None
    traits_at_time: dict | None
    key_narratives: list[str] | None
    sources_count: int | None


class PlayerWithTimeline(BaseModel):
    """Player detail with timeline history."""

    player: PlayerDetail
    timeline: list[TimelineSnapshot]
    report_count: int


class TeamSummary(BaseModel):
    """Team scouting summary."""

    team: str
    player_count: int
    avg_grade: float | None
    top_players: list[PlayerSummary]
```

**Step 3: Create FastAPI app**

```python
# src/api/main.py
"""FastAPI application for CFB Scout API."""

from fastapi import FastAPI, HTTPException, Query
from dotenv import load_dotenv

load_dotenv()

from ..storage.db import get_connection, get_scouting_player, get_player_timeline
from ..processing.aggregation import get_player_reports
from .models import (
    PlayerSummary,
    PlayerDetail,
    PlayerWithTimeline,
    TimelineSnapshot,
    TeamSummary,
)

app = FastAPI(
    title="CFB Scout API",
    description="College Football Scouting Intelligence API",
    version="0.3.0",
)


@app.get("/")
def root():
    """API root - health check."""
    return {"status": "ok", "version": "0.3.0"}


@app.get("/players", response_model=list[PlayerSummary])
def list_players(
    team: str | None = None,
    position: str | None = None,
    min_grade: int | None = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List players with optional filters."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        query = """
            SELECT id, name, team, position, class_year,
                   composite_grade, current_status
            FROM scouting.players
            WHERE 1=1
        """
        params = []

        if team:
            query += " AND LOWER(team) = LOWER(%s)"
            params.append(team)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        if min_grade is not None:
            query += " AND composite_grade >= %s"
            params.append(min_grade)

        query += " ORDER BY composite_grade DESC NULLS LAST LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        return [PlayerSummary(**row) for row in rows]

    finally:
        cur.close()
        conn.close()


@app.get("/players/{player_id}", response_model=PlayerWithTimeline)
def get_player(player_id: int):
    """Get player detail with timeline."""
    conn = get_connection()

    try:
        player = get_scouting_player(conn, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        timeline = get_player_timeline(conn, player_id)
        reports = get_player_reports(player_id)

        return PlayerWithTimeline(
            player=PlayerDetail(**player),
            timeline=[TimelineSnapshot(**t) for t in timeline],
            report_count=len(reports),
        )

    finally:
        conn.close()


@app.get("/teams", response_model=list[TeamSummary])
def list_teams(limit: int = Query(25, ge=1, le=100)):
    """List teams with player stats."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT team,
                   COUNT(*) as player_count,
                   AVG(composite_grade) as avg_grade
            FROM scouting.players
            WHERE team IS NOT NULL
            GROUP BY team
            ORDER BY avg_grade DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )

        teams = []
        for row in cur.fetchall():
            team_name, player_count, avg_grade = row

            # Get top 3 players for this team
            cur.execute(
                """
                SELECT id, name, team, position, class_year,
                       composite_grade, current_status
                FROM scouting.players
                WHERE team = %s
                ORDER BY composite_grade DESC NULLS LAST
                LIMIT 3
                """,
                (team_name,),
            )
            columns = [desc[0] for desc in cur.description]
            top_players = [
                PlayerSummary(**dict(zip(columns, p)))
                for p in cur.fetchall()
            ]

            teams.append(
                TeamSummary(
                    team=team_name,
                    player_count=player_count,
                    avg_grade=round(float(avg_grade), 1) if avg_grade else None,
                    top_players=top_players,
                )
            )

        return teams

    finally:
        cur.close()
        conn.close()


@app.get("/teams/{team_name}/players", response_model=list[PlayerSummary])
def get_team_players(team_name: str):
    """Get all players for a team."""
    return list_players(team=team_name, limit=100)
```

**Step 4: Test API starts**

```bash
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8000 &
sleep 2
curl http://localhost:8000/
pkill -f "uvicorn src.api.main"
```

Expected: `{"status":"ok","version":"0.3.0"}`

**Step 5: Commit**

```bash
git add src/api/
git commit -m "feat: add FastAPI application with player and team endpoints"
```

---

## Task 6: Add API Tests

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_api.py`

**Step 1: Write API tests**

```python
# tests/test_api.py
"""Tests for FastAPI endpoints."""

from fastapi.testclient import TestClient

from src.api.main import app


client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_players():
    """Test listing players."""
    response = client.get("/players")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_players_with_filters():
    """Test listing players with filters."""
    response = client.get("/players?team=Texas&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10


def test_get_player_not_found():
    """Test 404 for missing player."""
    response = client.get("/players/999999")
    assert response.status_code == 404


def test_list_teams():
    """Test listing teams."""
    response = client.get("/teams")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

**Step 2: Run tests**

```bash
pip install httpx  # Required for TestClient
python -m pytest tests/test_api.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_api.py
git commit -m "test: add FastAPI endpoint tests"
```

---

## Task 7: Create API Run Script

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/scripts/run_api.py`
- Modify: `/Users/robstover/Development/personal/cfb-scout/README.md`

**Step 1: Create API runner script**

```python
#!/usr/bin/env python3
# scripts/run_api.py
"""Run the CFB Scout API server."""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Run CFB Scout API")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    args = parser.parse_args()

    uvicorn.run(
        "src.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
```

**Step 2: Update README**

Add to Usage section:

```markdown
## API Server

```bash
# Start the API server (development)
python scripts/run_api.py --reload

# Start on specific host/port
python scripts/run_api.py --host 0.0.0.0 --port 8080

# API docs available at http://localhost:8000/docs
```

## Phase 3 Status

- [x] Player profile aggregation
- [x] Composite grading system
- [x] Timeline tracking snapshots
- [x] FastAPI REST endpoints
- [x] Player/team query API
```

**Step 3: Verify API**

```bash
python scripts/run_api.py &
sleep 2
curl http://localhost:8000/docs
pkill -f "run_api.py"
```

Expected: OpenAPI docs HTML

**Step 4: Commit**

```bash
chmod +x scripts/run_api.py
git add scripts/run_api.py README.md
git commit -m "feat: add API server script and update documentation"
```

---

## Task 8: Run Full Test Suite and Final Verification

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass.

**Step 2: Run lint**

```bash
ruff check src/ tests/ --fix
ruff format src/ tests/
```

**Step 3: Verify complete pipeline**

```bash
# Seed data
python scripts/run_pipeline.py --seed

# Process reports
python scripts/run_pipeline.py --process

# Link entities
python scripts/run_pipeline.py --link

# Grade players
python scripts/run_pipeline.py --grade

# Start API
python scripts/run_api.py &
sleep 2

# Test endpoints
curl http://localhost:8000/players
curl http://localhost:8000/teams

pkill -f "run_api.py"
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: phase 3 complete - lint fixes and verification"
git push origin main
```

---

## Success Criteria Checklist

- [ ] Player aggregation collects reports and calculates sentiment
- [ ] Traits extracted via Claude from report summaries
- [ ] Composite grades calculated (0-100)
- [ ] Timeline snapshots created on grade updates
- [ ] FastAPI server starts and serves endpoints
- [ ] `/players` endpoint lists and filters players
- [ ] `/players/{id}` returns player with timeline
- [ ] `/teams` returns team summaries with top players
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] API documentation accessible at `/docs`
