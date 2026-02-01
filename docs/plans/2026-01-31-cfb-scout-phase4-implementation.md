# CFB Scout Agent Phase 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PFF integration, trend analysis, player comparisons, watch lists, and draft board features to the scouting intelligence platform.

**Architecture:** PFF client wraps licensed API for grade/snap data. Trend analyzer detects rising/falling stocks via timeline analysis. Comparison engine generates radar charts and head-to-head stats. Watch lists use user-scoped tables with notification hooks. Draft board aggregates grades into mock draft rankings. All features exposed via extended FastAPI endpoints.

**Tech Stack:** Python 3.12, FastAPI, httpx (PFF client), numpy (trend calculations), pydantic

---

## Task 1: Add Phase 4 Dependencies

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/pyproject.toml`

**Step 1: Add numpy for trend calculations**

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
git commit -m "feat: add numpy dependency for trend analysis"
```

---

## Task 2: Create PFF Client Module

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/clients/__init__.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/src/clients/pff.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_pff_client.py`

**Step 1: Create clients package**

```bash
mkdir -p /Users/robstover/Development/personal/cfb-scout/src/clients
touch /Users/robstover/Development/personal/cfb-scout/src/clients/__init__.py
```

**Step 2: Write failing test for PFF client**

```python
# tests/test_pff_client.py
"""Tests for PFF API client."""

import pytest
from unittest.mock import patch, MagicMock

from src.clients.pff import PFFClient, PFFPlayerGrade


def test_pff_client_init_requires_api_key():
    """Test that client requires API key."""
    with pytest.raises(ValueError, match="PFF_API_KEY"):
        PFFClient(api_key=None)


def test_pff_client_init_with_key():
    """Test client initializes with API key."""
    client = PFFClient(api_key="test-key")
    assert client.api_key == "test-key"


def test_pff_player_grade_model():
    """Test PFFPlayerGrade pydantic model."""
    grade = PFFPlayerGrade(
        player_id="12345",
        name="Arch Manning",
        position="QB",
        team="Texas",
        overall_grade=85.5,
        passing_grade=87.2,
        rushing_grade=72.1,
        snaps=450,
        season=2025,
    )
    assert grade.overall_grade == 85.5
    assert grade.position == "QB"
```

**Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_pff_client.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 4: Write PFF client implementation**

```python
# src/clients/pff.py
"""PFF API client for grade and snap data."""

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PFF_BASE_URL = "https://api.pff.com/v1"


class PFFPlayerGrade(BaseModel):
    """PFF player grade data."""

    player_id: str
    name: str
    position: str
    team: str
    overall_grade: float
    passing_grade: float | None = None
    rushing_grade: float | None = None
    receiving_grade: float | None = None
    blocking_grade: float | None = None
    defense_grade: float | None = None
    coverage_grade: float | None = None
    pass_rush_grade: float | None = None
    run_defense_grade: float | None = None
    snaps: int
    season: int


class PFFClient:
    """Client for PFF API."""

    def __init__(self, api_key: str | None = None):
        """Initialize PFF client.

        Args:
            api_key: PFF API key. Falls back to PFF_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("PFF_API_KEY")
        if not self.api_key:
            raise ValueError("PFF_API_KEY environment variable or api_key required")

        self.client = httpx.Client(
            base_url=PFF_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def get_player_grades(
        self,
        team: str | None = None,
        position: str | None = None,
        season: int = 2025,
        limit: int = 100,
    ) -> list[PFFPlayerGrade]:
        """Get player grades from PFF API.

        Args:
            team: Filter by team name
            position: Filter by position (QB, RB, WR, etc.)
            season: Season year
            limit: Max results

        Returns:
            List of PFFPlayerGrade objects
        """
        params: dict[str, Any] = {
            "season": season,
            "limit": limit,
            "league": "ncaa",
        }
        if team:
            params["team"] = team
        if position:
            params["position"] = position

        try:
            response = self.client.get("/grades/players", params=params)
            response.raise_for_status()
            data = response.json()

            return [
                PFFPlayerGrade(
                    player_id=str(p["id"]),
                    name=p["name"],
                    position=p["position"],
                    team=p["team"],
                    overall_grade=p["overall_grade"],
                    passing_grade=p.get("passing_grade"),
                    rushing_grade=p.get("rushing_grade"),
                    receiving_grade=p.get("receiving_grade"),
                    blocking_grade=p.get("blocking_grade"),
                    defense_grade=p.get("defense_grade"),
                    coverage_grade=p.get("coverage_grade"),
                    pass_rush_grade=p.get("pass_rush_grade"),
                    run_defense_grade=p.get("run_defense_grade"),
                    snaps=p["snaps"],
                    season=season,
                )
                for p in data.get("players", [])
            ]
        except httpx.HTTPError as e:
            logger.error(f"PFF API error: {e}")
            raise

    def get_player_by_name(
        self,
        name: str,
        team: str | None = None,
        season: int = 2025,
    ) -> PFFPlayerGrade | None:
        """Look up a player by name.

        Args:
            name: Player name to search
            team: Optional team filter
            season: Season year

        Returns:
            PFFPlayerGrade if found, None otherwise
        """
        params: dict[str, Any] = {
            "search": name,
            "season": season,
            "league": "ncaa",
        }
        if team:
            params["team"] = team

        try:
            response = self.client.get("/grades/players/search", params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get("players"):
                return None

            p = data["players"][0]
            return PFFPlayerGrade(
                player_id=str(p["id"]),
                name=p["name"],
                position=p["position"],
                team=p["team"],
                overall_grade=p["overall_grade"],
                passing_grade=p.get("passing_grade"),
                rushing_grade=p.get("rushing_grade"),
                receiving_grade=p.get("receiving_grade"),
                blocking_grade=p.get("blocking_grade"),
                defense_grade=p.get("defense_grade"),
                coverage_grade=p.get("coverage_grade"),
                pass_rush_grade=p.get("pass_rush_grade"),
                run_defense_grade=p.get("run_defense_grade"),
                snaps=p["snaps"],
                season=season,
            )
        except httpx.HTTPError as e:
            logger.error(f"PFF API error searching for {name}: {e}")
            return None

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

**Step 5: Run tests**

```bash
python -m pytest tests/test_pff_client.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add src/clients/ tests/test_pff_client.py
git commit -m "feat: add PFF API client for grade data"
```

---

## Task 3: Add PFF Grade Storage

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/schema.sql`
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`

**Step 1: Add pff_grades table to schema**

Add to end of schema.sql:

```sql
-- PFF grade snapshots
CREATE TABLE IF NOT EXISTS scouting.pff_grades (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES scouting.players(id) ON DELETE CASCADE,
    pff_player_id TEXT NOT NULL,
    season INT NOT NULL,
    week INT,  -- NULL for season-long grades
    overall_grade NUMERIC(4,1) NOT NULL,
    position_grades JSONB DEFAULT '{}',
    snaps INT DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, season, week)
);

CREATE INDEX idx_pff_grades_player ON scouting.pff_grades (player_id);
CREATE INDEX idx_pff_grades_season ON scouting.pff_grades (season, week);
```

**Step 2: Add db functions for PFF grades**

Add to db.py:

```python
def upsert_pff_grade(
    conn: connection,
    player_id: int,
    pff_player_id: str,
    season: int,
    overall_grade: float,
    position_grades: dict | None = None,
    snaps: int = 0,
    week: int | None = None,
) -> int:
    """Upsert a PFF grade for a player."""
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.pff_grades
            (player_id, pff_player_id, season, week, overall_grade, position_grades, snaps)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_id, season, week) DO UPDATE SET
            overall_grade = EXCLUDED.overall_grade,
            position_grades = EXCLUDED.position_grades,
            snaps = EXCLUDED.snaps,
            fetched_at = NOW()
        RETURNING id
        """,
        (
            player_id,
            pff_player_id,
            season,
            week,
            overall_grade,
            json.dumps(position_grades) if position_grades else None,
            snaps,
        ),
    )
    grade_id = cur.fetchone()[0]
    conn.commit()
    return grade_id


def get_player_pff_grades(
    conn: connection,
    player_id: int,
    season: int | None = None,
) -> list[dict]:
    """Get PFF grades for a player."""
    cur = conn.cursor()

    query = """
        SELECT id, player_id, pff_player_id, season, week,
               overall_grade, position_grades, snaps, fetched_at
        FROM scouting.pff_grades
        WHERE player_id = %s
    """
    params = [player_id]

    if season:
        query += " AND season = %s"
        params.append(season)

    query += " ORDER BY season DESC, week DESC NULLS FIRST"

    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]
```

**Step 3: Apply migration**

```bash
# Run via Supabase MCP or psql
psql "$DATABASE_URL" -c "
CREATE TABLE IF NOT EXISTS scouting.pff_grades (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES scouting.players(id) ON DELETE CASCADE,
    pff_player_id TEXT NOT NULL,
    season INT NOT NULL,
    week INT,
    overall_grade NUMERIC(4,1) NOT NULL,
    position_grades JSONB DEFAULT '{}',
    snaps INT DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, season, week)
);
CREATE INDEX IF NOT EXISTS idx_pff_grades_player ON scouting.pff_grades (player_id);
CREATE INDEX IF NOT EXISTS idx_pff_grades_season ON scouting.pff_grades (season, week);
"
```

**Step 4: Commit**

```bash
git add src/storage/schema.sql src/storage/db.py
git commit -m "feat: add PFF grade storage table and functions"
```

---

## Task 4: Create Trend Analyzer

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/trends.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_trends.py`

**Step 1: Write failing test for trend detection**

```python
# tests/test_trends.py
"""Tests for trend analysis."""

from datetime import date, timedelta

from src.processing.trends import (
    calculate_trend,
    TrendDirection,
    PlayerTrend,
)


def test_calculate_trend_rising():
    """Test detecting rising trend."""
    grades = [60, 65, 70, 75, 80]  # Consistently increasing
    result = calculate_trend(grades)
    assert result == TrendDirection.RISING


def test_calculate_trend_falling():
    """Test detecting falling trend."""
    grades = [80, 75, 70, 65, 60]  # Consistently decreasing
    result = calculate_trend(grades)
    assert result == TrendDirection.FALLING


def test_calculate_trend_stable():
    """Test detecting stable trend."""
    grades = [70, 72, 69, 71, 70]  # Minor fluctuations
    result = calculate_trend(grades)
    assert result == TrendDirection.STABLE


def test_calculate_trend_insufficient_data():
    """Test with insufficient data points."""
    grades = [70, 75]  # Only 2 points
    result = calculate_trend(grades)
    assert result == TrendDirection.UNKNOWN
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_trends.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write trend analyzer implementation**

```python
# src/processing/trends.py
"""Player trend analysis and trajectory detection."""

import logging
from datetime import date, timedelta
from enum import Enum

import numpy as np

from ..storage.db import get_connection, get_player_timeline

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Direction of player trend."""

    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNKNOWN = "unknown"


class PlayerTrend:
    """Player trend analysis result."""

    def __init__(
        self,
        player_id: int,
        direction: TrendDirection,
        slope: float,
        grade_change: float,
        data_points: int,
        period_days: int,
    ):
        self.player_id = player_id
        self.direction = direction
        self.slope = slope
        self.grade_change = grade_change
        self.data_points = data_points
        self.period_days = period_days

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "direction": self.direction.value,
            "slope": round(self.slope, 3),
            "grade_change": round(self.grade_change, 1),
            "data_points": self.data_points,
            "period_days": self.period_days,
        }


def calculate_trend(
    grades: list[float],
    threshold: float = 0.5,
) -> TrendDirection:
    """Calculate trend direction from a series of grades.

    Args:
        grades: List of grades in chronological order (oldest first)
        threshold: Minimum slope to consider rising/falling

    Returns:
        TrendDirection enum value
    """
    if len(grades) < 3:
        return TrendDirection.UNKNOWN

    # Use linear regression to find slope
    x = np.arange(len(grades))
    y = np.array(grades)

    # Calculate slope using least squares
    n = len(grades)
    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (
        n * np.sum(x**2) - np.sum(x) ** 2
    )

    if slope > threshold:
        return TrendDirection.RISING
    elif slope < -threshold:
        return TrendDirection.FALLING
    else:
        return TrendDirection.STABLE


def analyze_player_trend(
    player_id: int,
    days: int = 90,
) -> PlayerTrend:
    """Analyze trend for a specific player.

    Args:
        player_id: Player to analyze
        days: Number of days to look back

    Returns:
        PlayerTrend object with analysis results
    """
    conn = get_connection()

    try:
        timeline = get_player_timeline(conn, player_id, limit=30)

        if len(timeline) < 3:
            return PlayerTrend(
                player_id=player_id,
                direction=TrendDirection.UNKNOWN,
                slope=0.0,
                grade_change=0.0,
                data_points=len(timeline),
                period_days=0,
            )

        # Filter to specified period
        cutoff = date.today() - timedelta(days=days)
        recent = [
            t for t in timeline
            if t["snapshot_date"] >= cutoff and t["grade_at_time"] is not None
        ]

        if len(recent) < 3:
            return PlayerTrend(
                player_id=player_id,
                direction=TrendDirection.UNKNOWN,
                slope=0.0,
                grade_change=0.0,
                data_points=len(recent),
                period_days=days,
            )

        # Sort chronologically (oldest first)
        recent.sort(key=lambda x: x["snapshot_date"])
        grades = [float(t["grade_at_time"]) for t in recent]

        direction = calculate_trend(grades)

        # Calculate slope for reporting
        x = np.arange(len(grades))
        y = np.array(grades)
        n = len(grades)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (
            n * np.sum(x**2) - np.sum(x) ** 2
        )

        grade_change = grades[-1] - grades[0]

        return PlayerTrend(
            player_id=player_id,
            direction=direction,
            slope=float(slope),
            grade_change=grade_change,
            data_points=len(recent),
            period_days=days,
        )

    finally:
        conn.close()


def get_rising_stocks(
    limit: int = 20,
    min_data_points: int = 3,
    days: int = 90,
) -> list[dict]:
    """Get players with rising trends.

    Returns list of players sorted by slope (steepest rise first).
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get players with recent timeline entries
        cur.execute(
            """
            SELECT DISTINCT p.id, p.name, p.team, p.position
            FROM scouting.players p
            JOIN scouting.player_timeline t ON p.id = t.player_id
            WHERE t.snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
            AND t.grade_at_time IS NOT NULL
            GROUP BY p.id
            HAVING COUNT(*) >= %s
            """,
            (days, min_data_points),
        )

        players = cur.fetchall()
        trends = []

        for player_id, name, team, position in players:
            trend = analyze_player_trend(player_id, days)
            if trend.direction == TrendDirection.RISING:
                trends.append({
                    "player_id": player_id,
                    "name": name,
                    "team": team,
                    "position": position,
                    **trend.to_dict(),
                })

        # Sort by slope descending
        trends.sort(key=lambda x: x["slope"], reverse=True)
        return trends[:limit]

    finally:
        cur.close()
        conn.close()


def get_falling_stocks(
    limit: int = 20,
    min_data_points: int = 3,
    days: int = 90,
) -> list[dict]:
    """Get players with falling trends.

    Returns list of players sorted by slope (steepest fall first).
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT DISTINCT p.id, p.name, p.team, p.position
            FROM scouting.players p
            JOIN scouting.player_timeline t ON p.id = t.player_id
            WHERE t.snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
            AND t.grade_at_time IS NOT NULL
            GROUP BY p.id
            HAVING COUNT(*) >= %s
            """,
            (days, min_data_points),
        )

        players = cur.fetchall()
        trends = []

        for player_id, name, team, position in players:
            trend = analyze_player_trend(player_id, days)
            if trend.direction == TrendDirection.FALLING:
                trends.append({
                    "player_id": player_id,
                    "name": name,
                    "team": team,
                    "position": position,
                    **trend.to_dict(),
                })

        # Sort by slope ascending (most negative first)
        trends.sort(key=lambda x: x["slope"])
        return trends[:limit]

    finally:
        cur.close()
        conn.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_trends.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/trends.py tests/test_trends.py
git commit -m "feat: add trend analysis with rising/falling stock detection"
```

---

## Task 5: Create Player Comparison Engine

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/comparison.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_comparison.py`

**Step 1: Write failing test for comparison**

```python
# tests/test_comparison.py
"""Tests for player comparison engine."""

from src.processing.comparison import (
    compare_players,
    PlayerComparison,
    build_radar_data,
)


def test_build_radar_data():
    """Test building radar chart data."""
    traits = {
        "arm_strength": 8,
        "accuracy": 7,
        "mobility": 6,
        "decision_making": 9,
    }
    result = build_radar_data(traits)

    assert len(result) == 4
    assert result[0]["trait"] == "arm_strength"
    assert result[0]["value"] == 8


def test_build_radar_data_empty():
    """Test radar data with empty traits."""
    result = build_radar_data({})
    assert result == []


def test_build_radar_data_normalizes():
    """Test that values are normalized to 0-10 scale."""
    traits = {"speed": 95}  # If somehow > 10
    result = build_radar_data(traits, max_value=100)
    assert result[0]["value"] == 9.5  # Normalized to 10-scale
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_comparison.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write comparison engine**

```python
# src/processing/comparison.py
"""Player comparison engine for head-to-head analysis."""

import logging
from dataclasses import dataclass

from ..storage.db import get_connection, get_scouting_player, get_player_pff_grades

logger = logging.getLogger(__name__)

TRAIT_CATEGORIES = [
    "arm_strength",
    "accuracy",
    "mobility",
    "decision_making",
    "leadership",
    "athleticism",
    "technique",
    "football_iq",
    "consistency",
    "upside",
]


@dataclass
class PlayerComparison:
    """Result of comparing two players."""

    player1: dict
    player2: dict
    trait_comparison: list[dict]
    grade_comparison: dict
    pff_comparison: dict | None
    advantages: dict


def build_radar_data(
    traits: dict,
    max_value: float = 10.0,
) -> list[dict]:
    """Build radar chart data from player traits.

    Args:
        traits: Dict of trait name -> value
        max_value: Maximum value for normalization

    Returns:
        List of {trait, value} dicts for radar chart
    """
    if not traits:
        return []

    result = []
    for trait, value in traits.items():
        normalized = (value / max_value) * 10 if max_value != 10 else value
        result.append({
            "trait": trait,
            "value": round(normalized, 1),
        })

    return result


def compare_players(player1_id: int, player2_id: int) -> PlayerComparison:
    """Compare two players head-to-head.

    Args:
        player1_id: First player ID
        player2_id: Second player ID

    Returns:
        PlayerComparison with detailed comparison data
    """
    conn = get_connection()

    try:
        p1 = get_scouting_player(conn, player1_id)
        p2 = get_scouting_player(conn, player2_id)

        if not p1 or not p2:
            raise ValueError(f"Player not found: {player1_id if not p1 else player2_id}")

        # Trait comparison
        p1_traits = p1.get("traits") or {}
        p2_traits = p2.get("traits") or {}

        trait_comparison = []
        p1_advantages = []
        p2_advantages = []

        for trait in TRAIT_CATEGORIES:
            v1 = p1_traits.get(trait)
            v2 = p2_traits.get(trait)

            if v1 is not None or v2 is not None:
                diff = (v1 or 0) - (v2 or 0)
                trait_comparison.append({
                    "trait": trait,
                    "player1_value": v1,
                    "player2_value": v2,
                    "difference": diff,
                })

                if diff > 0.5:
                    p1_advantages.append(trait)
                elif diff < -0.5:
                    p2_advantages.append(trait)

        # Grade comparison
        grade_comparison = {
            "player1_grade": p1.get("composite_grade"),
            "player2_grade": p2.get("composite_grade"),
            "difference": (
                (p1.get("composite_grade") or 0) - (p2.get("composite_grade") or 0)
            ),
        }

        # PFF comparison
        pff1 = get_player_pff_grades(conn, player1_id)
        pff2 = get_player_pff_grades(conn, player2_id)

        pff_comparison = None
        if pff1 and pff2:
            pff_comparison = {
                "player1_overall": pff1[0].get("overall_grade"),
                "player2_overall": pff2[0].get("overall_grade"),
                "player1_snaps": pff1[0].get("snaps"),
                "player2_snaps": pff2[0].get("snaps"),
            }

        return PlayerComparison(
            player1={
                "id": p1["id"],
                "name": p1["name"],
                "team": p1.get("team"),
                "position": p1.get("position"),
                "radar_data": build_radar_data(p1_traits),
            },
            player2={
                "id": p2["id"],
                "name": p2["name"],
                "team": p2.get("team"),
                "position": p2.get("position"),
                "radar_data": build_radar_data(p2_traits),
            },
            trait_comparison=trait_comparison,
            grade_comparison=grade_comparison,
            pff_comparison=pff_comparison,
            advantages={
                "player1": p1_advantages,
                "player2": p2_advantages,
            },
        )

    finally:
        conn.close()


def find_similar_players(
    player_id: int,
    limit: int = 5,
) -> list[dict]:
    """Find players with similar trait profiles.

    Uses cosine similarity on trait vectors.
    """
    import numpy as np

    conn = get_connection()
    cur = conn.cursor()

    try:
        player = get_scouting_player(conn, player_id)
        if not player or not player.get("traits"):
            return []

        player_traits = player["traits"]
        player_vector = np.array([
            player_traits.get(t, 0) for t in TRAIT_CATEGORIES
        ])

        if np.linalg.norm(player_vector) == 0:
            return []

        # Get other players with traits
        cur.execute(
            """
            SELECT id, name, team, position, traits
            FROM scouting.players
            WHERE id != %s
            AND traits IS NOT NULL
            AND traits != '{}'
            """,
            (player_id,),
        )

        similarities = []
        for row in cur.fetchall():
            other_id, name, team, position, other_traits = row
            if not other_traits:
                continue

            other_vector = np.array([
                other_traits.get(t, 0) for t in TRAIT_CATEGORIES
            ])

            if np.linalg.norm(other_vector) == 0:
                continue

            # Cosine similarity
            similarity = np.dot(player_vector, other_vector) / (
                np.linalg.norm(player_vector) * np.linalg.norm(other_vector)
            )

            similarities.append({
                "player_id": other_id,
                "name": name,
                "team": team,
                "position": position,
                "similarity": round(float(similarity), 3),
            })

        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:limit]

    finally:
        cur.close()
        conn.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_comparison.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/comparison.py tests/test_comparison.py
git commit -m "feat: add player comparison engine with radar charts"
```

---

## Task 6: Create Watch List Feature

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/schema.sql`
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_watchlist.py`

**Step 1: Add watch_lists table to schema**

Add to schema.sql:

```sql
-- User watch lists
CREATE TABLE IF NOT EXISTS scouting.watch_lists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    user_id TEXT NOT NULL,  -- External user identifier
    description TEXT,
    player_ids INT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);

CREATE INDEX idx_watch_lists_user ON scouting.watch_lists (user_id);
```

**Step 2: Write failing test**

```python
# tests/test_watchlist.py
"""Tests for watch list functions."""

from src.storage.db import (
    get_connection,
    create_watch_list,
    get_watch_lists,
    add_to_watch_list,
    remove_from_watch_list,
)


def test_create_watch_list():
    """Test creating a watch list."""
    conn = get_connection()

    try:
        list_id = create_watch_list(
            conn,
            user_id="test-user",
            name="Top QBs",
            description="Tracking top quarterback prospects",
        )

        assert list_id is not None
        assert list_id > 0

    finally:
        # Cleanup
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.watch_lists WHERE user_id = 'test-user'")
        conn.commit()
        conn.close()


def test_get_watch_lists():
    """Test retrieving user's watch lists."""
    conn = get_connection()

    try:
        create_watch_list(conn, "test-user-2", "List 1")
        create_watch_list(conn, "test-user-2", "List 2")

        lists = get_watch_lists(conn, "test-user-2")

        assert len(lists) == 2

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.watch_lists WHERE user_id = 'test-user-2'")
        conn.commit()
        conn.close()
```

**Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_watchlist.py -v
```

Expected: FAIL with import error

**Step 4: Add watch list db functions**

Add to db.py:

```python
def create_watch_list(
    conn: connection,
    user_id: str,
    name: str,
    description: str | None = None,
) -> int:
    """Create a new watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.watch_lists (user_id, name, description)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (user_id, name, description),
    )
    list_id = cur.fetchone()[0]
    conn.commit()
    return list_id


def get_watch_lists(
    conn: connection,
    user_id: str,
) -> list[dict]:
    """Get all watch lists for a user."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, description, player_ids, created_at, updated_at
        FROM scouting.watch_lists
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_watch_list(
    conn: connection,
    list_id: int,
) -> dict | None:
    """Get a specific watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user_id, name, description, player_ids, created_at, updated_at
        FROM scouting.watch_lists
        WHERE id = %s
        """,
        (list_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def add_to_watch_list(
    conn: connection,
    list_id: int,
    player_id: int,
) -> None:
    """Add a player to a watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.watch_lists
        SET player_ids = array_append(
            COALESCE(player_ids, '{}'),
            %s
        ),
        updated_at = NOW()
        WHERE id = %s
        AND NOT (%s = ANY(COALESCE(player_ids, '{}')))
        """,
        (player_id, list_id, player_id),
    )
    conn.commit()


def remove_from_watch_list(
    conn: connection,
    list_id: int,
    player_id: int,
) -> None:
    """Remove a player from a watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.watch_lists
        SET player_ids = array_remove(player_ids, %s),
            updated_at = NOW()
        WHERE id = %s
        """,
        (player_id, list_id),
    )
    conn.commit()


def delete_watch_list(
    conn: connection,
    list_id: int,
) -> None:
    """Delete a watch list."""
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.watch_lists WHERE id = %s", (list_id,))
    conn.commit()
```

**Step 5: Apply migration**

```bash
psql "$DATABASE_URL" -c "
CREATE TABLE IF NOT EXISTS scouting.watch_lists (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    description TEXT,
    player_ids INT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_watch_lists_user ON scouting.watch_lists (user_id);
"
```

**Step 6: Run tests**

```bash
python -m pytest tests/test_watchlist.py -v
```

Expected: PASS

**Step 7: Commit**

```bash
git add src/storage/schema.sql src/storage/db.py tests/test_watchlist.py
git commit -m "feat: add watch list feature with CRUD operations"
```

---

## Task 7: Create Draft Board

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/draft.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_draft.py`

**Step 1: Write failing test**

```python
# tests/test_draft.py
"""Tests for draft board functionality."""

from src.processing.draft import (
    calculate_draft_score,
    DraftProjection,
)


def test_calculate_draft_score_first_round():
    """Test draft score calculation for elite player."""
    score = calculate_draft_score(
        composite_grade=92,
        pff_grade=90.5,
        trend_slope=1.2,
    )
    assert score > 80


def test_calculate_draft_score_no_pff():
    """Test draft score without PFF grade."""
    score = calculate_draft_score(
        composite_grade=75,
        pff_grade=None,
        trend_slope=0.5,
    )
    assert 50 < score < 80


def test_draft_projection_enum():
    """Test DraftProjection values."""
    assert DraftProjection.FIRST_ROUND.value == "1st Round"
    assert DraftProjection.UDFA.value == "UDFA"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_draft.py -v
```

Expected: FAIL

**Step 3: Write draft board implementation**

```python
# src/processing/draft.py
"""Draft board and projection system."""

import logging
from dataclasses import dataclass
from enum import Enum

from ..storage.db import get_connection, get_player_pff_grades
from .trends import analyze_player_trend, TrendDirection

logger = logging.getLogger(__name__)


class DraftProjection(Enum):
    """Draft round projection."""

    FIRST_ROUND = "1st Round"
    SECOND_ROUND = "2nd Round"
    THIRD_ROUND = "3rd Round"
    DAY_TWO = "Day 2 (Rounds 2-3)"
    DAY_THREE = "Day 3 (Rounds 4-7)"
    UDFA = "UDFA"
    NOT_DRAFT_ELIGIBLE = "Not Draft Eligible"


@dataclass
class DraftPlayer:
    """Player on draft board."""

    player_id: int
    name: str
    position: str
    team: str
    class_year: int | None
    draft_score: float
    projection: DraftProjection
    composite_grade: int | None
    pff_grade: float | None
    trend_direction: str


def calculate_draft_score(
    composite_grade: int | None,
    pff_grade: float | None = None,
    trend_slope: float = 0.0,
) -> float:
    """Calculate draft score from multiple inputs.

    Args:
        composite_grade: Scout composite grade (0-100)
        pff_grade: PFF overall grade (0-100)
        trend_slope: Trend slope (positive = rising)

    Returns:
        Draft score (0-100)
    """
    if composite_grade is None and pff_grade is None:
        return 0.0

    # Base score from composite grade (60% weight)
    base = (composite_grade or 50) * 0.6

    # PFF grade contribution (30% weight if available)
    if pff_grade is not None:
        base += pff_grade * 0.3
    else:
        # If no PFF, composite gets more weight
        base += (composite_grade or 50) * 0.3

    # Trend bonus/penalty (10% max)
    trend_bonus = min(max(trend_slope * 5, -10), 10)
    base += trend_bonus

    return max(0, min(100, base))


def get_projection(draft_score: float) -> DraftProjection:
    """Get draft projection from score."""
    if draft_score >= 85:
        return DraftProjection.FIRST_ROUND
    elif draft_score >= 75:
        return DraftProjection.SECOND_ROUND
    elif draft_score >= 65:
        return DraftProjection.THIRD_ROUND
    elif draft_score >= 55:
        return DraftProjection.DAY_THREE
    else:
        return DraftProjection.UDFA


def build_draft_board(
    class_year: int | None = None,
    position: str | None = None,
    limit: int = 100,
) -> list[DraftPlayer]:
    """Build draft board with rankings.

    Args:
        class_year: Filter by class year (seniors/juniors)
        position: Filter by position
        limit: Max players to return

    Returns:
        List of DraftPlayer sorted by draft score
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        query = """
            SELECT id, name, position, team, class_year,
                   composite_grade, current_status
            FROM scouting.players
            WHERE current_status IN ('active', 'draft_eligible')
        """
        params = []

        if class_year:
            query += " AND class_year = %s"
            params.append(class_year)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        query += " ORDER BY composite_grade DESC NULLS LAST LIMIT %s"
        params.append(limit * 2)  # Get extra for filtering

        cur.execute(query, params)

        players = []
        for row in cur.fetchall():
            player_id, name, pos, team, year, grade, status = row

            # Get PFF grade
            pff_grades = get_player_pff_grades(conn, player_id)
            pff_grade = pff_grades[0]["overall_grade"] if pff_grades else None

            # Get trend
            trend = analyze_player_trend(player_id, days=90)

            draft_score = calculate_draft_score(
                composite_grade=grade,
                pff_grade=pff_grade,
                trend_slope=trend.slope,
            )

            projection = get_projection(draft_score)

            players.append(DraftPlayer(
                player_id=player_id,
                name=name,
                position=pos or "Unknown",
                team=team or "Unknown",
                class_year=year,
                draft_score=round(draft_score, 1),
                projection=projection,
                composite_grade=grade,
                pff_grade=round(pff_grade, 1) if pff_grade else None,
                trend_direction=trend.direction.value,
            ))

        # Sort by draft score
        players.sort(key=lambda x: x.draft_score, reverse=True)
        return players[:limit]

    finally:
        cur.close()
        conn.close()


def get_position_rankings(position: str, limit: int = 25) -> list[DraftPlayer]:
    """Get draft rankings for a specific position."""
    return build_draft_board(position=position, limit=limit)


def get_team_draft_prospects(team: str) -> list[DraftPlayer]:
    """Get draft-eligible players for a team."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, name, position, team, class_year,
                   composite_grade, current_status
            FROM scouting.players
            WHERE LOWER(team) = LOWER(%s)
            AND current_status IN ('active', 'draft_eligible')
            ORDER BY composite_grade DESC NULLS LAST
            """,
            (team,),
        )

        players = []
        for row in cur.fetchall():
            player_id, name, pos, team, year, grade, status = row

            pff_grades = get_player_pff_grades(conn, player_id)
            pff_grade = pff_grades[0]["overall_grade"] if pff_grades else None

            trend = analyze_player_trend(player_id, days=90)

            draft_score = calculate_draft_score(
                composite_grade=grade,
                pff_grade=pff_grade,
                trend_slope=trend.slope,
            )

            players.append(DraftPlayer(
                player_id=player_id,
                name=name,
                position=pos or "Unknown",
                team=team or "Unknown",
                class_year=year,
                draft_score=round(draft_score, 1),
                projection=get_projection(draft_score),
                composite_grade=grade,
                pff_grade=round(pff_grade, 1) if pff_grade else None,
                trend_direction=trend.direction.value,
            ))

        players.sort(key=lambda x: x.draft_score, reverse=True)
        return players

    finally:
        cur.close()
        conn.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_draft.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/draft.py tests/test_draft.py
git commit -m "feat: add draft board with projections and rankings"
```

---

## Task 8: Extend API with Phase 4 Endpoints

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/api/models.py`
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/api/main.py`

**Step 1: Add new Pydantic models**

Add to models.py:

```python
class TrendData(BaseModel):
    """Player trend analysis."""

    player_id: int
    name: str | None = None
    team: str | None = None
    position: str | None = None
    direction: str
    slope: float
    grade_change: float
    data_points: int
    period_days: int


class ComparisonResult(BaseModel):
    """Player comparison result."""

    player1: dict
    player2: dict
    trait_comparison: list[dict]
    grade_comparison: dict
    pff_comparison: dict | None
    advantages: dict


class WatchList(BaseModel):
    """Watch list."""

    id: int
    name: str
    description: str | None
    player_ids: list[int]
    created_at: datetime
    updated_at: datetime


class WatchListCreate(BaseModel):
    """Watch list creation request."""

    name: str
    description: str | None = None


class DraftPlayerResponse(BaseModel):
    """Draft board player."""

    player_id: int
    name: str
    position: str
    team: str
    class_year: int | None
    draft_score: float
    projection: str
    composite_grade: int | None
    pff_grade: float | None
    trend_direction: str
```

**Step 2: Add new API endpoints**

Add to main.py:

```python
from ..processing.trends import get_rising_stocks, get_falling_stocks, analyze_player_trend
from ..processing.comparison import compare_players, find_similar_players
from ..processing.draft import build_draft_board, get_position_rankings
from ..storage.db import (
    create_watch_list,
    get_watch_lists,
    get_watch_list,
    add_to_watch_list,
    remove_from_watch_list,
    delete_watch_list,
)
from .models import (
    TrendData,
    ComparisonResult,
    WatchList,
    WatchListCreate,
    DraftPlayerResponse,
)


# Trends endpoints
@app.get("/trends/rising", response_model=list[TrendData])
def get_rising(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get players with rising trends."""
    return get_rising_stocks(limit=limit, days=days)


@app.get("/trends/falling", response_model=list[TrendData])
def get_falling(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get players with falling trends."""
    return get_falling_stocks(limit=limit, days=days)


@app.get("/players/{player_id}/trend", response_model=TrendData)
def get_player_trend(player_id: int, days: int = Query(90, ge=7, le=365)):
    """Get trend analysis for a specific player."""
    trend = analyze_player_trend(player_id, days=days)
    return TrendData(
        player_id=player_id,
        direction=trend.direction.value,
        slope=trend.slope,
        grade_change=trend.grade_change,
        data_points=trend.data_points,
        period_days=trend.period_days,
    )


# Comparison endpoints
@app.get("/compare/{player1_id}/{player2_id}", response_model=ComparisonResult)
def compare(player1_id: int, player2_id: int):
    """Compare two players head-to-head."""
    result = compare_players(player1_id, player2_id)
    return ComparisonResult(
        player1=result.player1,
        player2=result.player2,
        trait_comparison=result.trait_comparison,
        grade_comparison=result.grade_comparison,
        pff_comparison=result.pff_comparison,
        advantages=result.advantages,
    )


@app.get("/players/{player_id}/similar", response_model=list[dict])
def get_similar(player_id: int, limit: int = Query(5, ge=1, le=20)):
    """Find similar players based on trait profile."""
    return find_similar_players(player_id, limit=limit)


# Watch list endpoints
@app.get("/watchlists", response_model=list[WatchList])
def list_watchlists(user_id: str = Query(...)):
    """Get user's watch lists."""
    conn = get_connection()
    try:
        lists = get_watch_lists(conn, user_id)
        return [WatchList(**wl) for wl in lists]
    finally:
        conn.close()


@app.post("/watchlists", response_model=WatchList)
def create_watchlist(user_id: str = Query(...), data: WatchListCreate = ...):
    """Create a new watch list."""
    conn = get_connection()
    try:
        list_id = create_watch_list(conn, user_id, data.name, data.description)
        wl = get_watch_list(conn, list_id)
        return WatchList(**wl)
    finally:
        conn.close()


@app.post("/watchlists/{list_id}/players/{player_id}")
def add_player_to_watchlist(list_id: int, player_id: int):
    """Add a player to a watch list."""
    conn = get_connection()
    try:
        add_to_watch_list(conn, list_id, player_id)
        return {"status": "added"}
    finally:
        conn.close()


@app.delete("/watchlists/{list_id}/players/{player_id}")
def remove_player_from_watchlist(list_id: int, player_id: int):
    """Remove a player from a watch list."""
    conn = get_connection()
    try:
        remove_from_watch_list(conn, list_id, player_id)
        return {"status": "removed"}
    finally:
        conn.close()


@app.delete("/watchlists/{list_id}")
def delete_watchlist(list_id: int):
    """Delete a watch list."""
    conn = get_connection()
    try:
        delete_watch_list(conn, list_id)
        return {"status": "deleted"}
    finally:
        conn.close()


# Draft board endpoints
@app.get("/draft/board", response_model=list[DraftPlayerResponse])
def get_draft_board(
    class_year: int | None = None,
    position: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get draft board rankings."""
    players = build_draft_board(class_year=class_year, position=position, limit=limit)
    return [
        DraftPlayerResponse(
            player_id=p.player_id,
            name=p.name,
            position=p.position,
            team=p.team,
            class_year=p.class_year,
            draft_score=p.draft_score,
            projection=p.projection.value,
            composite_grade=p.composite_grade,
            pff_grade=p.pff_grade,
            trend_direction=p.trend_direction,
        )
        for p in players
    ]


@app.get("/draft/position/{position}", response_model=list[DraftPlayerResponse])
def get_position_draft_rankings(
    position: str,
    limit: int = Query(25, ge=1, le=100),
):
    """Get draft rankings by position."""
    players = get_position_rankings(position, limit=limit)
    return [
        DraftPlayerResponse(
            player_id=p.player_id,
            name=p.name,
            position=p.position,
            team=p.team,
            class_year=p.class_year,
            draft_score=p.draft_score,
            projection=p.projection.value,
            composite_grade=p.composite_grade,
            pff_grade=p.pff_grade,
            trend_direction=p.trend_direction,
        )
        for p in players
    ]
```

**Step 3: Commit**

```bash
git add src/api/models.py src/api/main.py
git commit -m "feat: add Phase 4 API endpoints for trends, compare, watchlists, draft"
```

---

## Task 9: Add API Tests for New Endpoints

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/tests/test_api.py`

**Step 1: Add new endpoint tests**

```python
# Add to tests/test_api.py

def test_get_rising_trends():
    """Test rising stocks endpoint."""
    response = client.get("/trends/rising")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_falling_trends():
    """Test falling stocks endpoint."""
    response = client.get("/trends/falling")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_draft_board():
    """Test draft board endpoint."""
    response = client.get("/draft/board")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_draft_board_by_position():
    """Test draft board by position."""
    response = client.get("/draft/position/QB")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_watchlist_requires_user_id():
    """Test that watchlist endpoints require user_id."""
    response = client.get("/watchlists")
    assert response.status_code == 422  # Validation error
```

**Step 2: Run all tests**

```bash
python -m pytest tests/test_api.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_api.py
git commit -m "test: add API tests for Phase 4 endpoints"
```

---

## Task 10: Update Documentation and Final Verification

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/README.md`

**Step 1: Update README with Phase 4 features**

Add to README:

```markdown
## Phase 4 Status

- [x] PFF API integration
- [x] Trend analysis (rising/falling stocks)
- [x] Player comparison engine
- [x] Watch lists
- [x] Draft board with projections

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
```

**Step 2: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass

**Step 3: Run lint**

```bash
ruff check src/ tests/ --fix
ruff format src/ tests/
```

**Step 4: Final commit and push**

```bash
git add -A
git commit -m "docs: update README with Phase 4 features and API docs"
git push origin main
```

---

## Success Criteria Checklist

- [ ] PFF client connects and fetches grade data
- [ ] PFF grades stored in database
- [ ] Trend analysis detects rising/falling players
- [ ] Player comparison generates radar chart data
- [ ] Watch lists CRUD operations work
- [ ] Draft board calculates scores and projections
- [ ] All new API endpoints return correct responses
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] API documentation accessible at `/docs`
