"""Draft board and projection system."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

import numpy as np

from ..storage.db import get_connection
from .trends import TrendDirection, calculate_trend

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


async def _batch_load_pff_grades(
    conn,
    player_ids: list[int],
) -> dict[int, float]:
    """Batch-load the most recent PFF overall grade for each player.

    Returns:
        Map of player_id -> overall_grade (most recent season first).
    """
    if not player_ids:
        return {}
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT player_id, overall_grade
        FROM scouting.pff_grades
        WHERE player_id = ANY(%s)
        ORDER BY season DESC, week DESC NULLS FIRST
        """,
        (player_ids,),
    )
    pff_map: dict[int, float] = {}
    for pid, grade in await cur.fetchall():
        if pid not in pff_map:  # keep most recent (first due to ORDER BY)
            pff_map[pid] = float(grade)
    return pff_map


async def _batch_load_trends(
    conn,
    player_ids: list[int],
    days: int = 90,
) -> dict[int, tuple[float, str]]:
    """Batch-load timeline data and compute trend slope/direction in-memory.

    Returns:
        Map of player_id -> (slope, direction_value).
    """
    if not player_ids:
        return {}
    cur = conn.cursor()
    cutoff = date.today() - timedelta(days=days)
    await cur.execute(
        """
        SELECT player_id, grade_at_time, snapshot_date
        FROM scouting.player_timeline
        WHERE player_id = ANY(%s)
          AND snapshot_date >= %s
          AND grade_at_time IS NOT NULL
        ORDER BY player_id, snapshot_date ASC
        """,
        (player_ids, cutoff),
    )

    # Group grades by player
    grades_by_player: dict[int, list[float]] = defaultdict(list)
    for pid, grade, _ in await cur.fetchall():
        grades_by_player[pid].append(float(grade))

    trend_map: dict[int, tuple[float, str]] = {}
    for pid in player_ids:
        grades = grades_by_player.get(pid, [])
        if len(grades) < 3:
            trend_map[pid] = (0.0, TrendDirection.UNKNOWN.value)
            continue

        direction = calculate_trend(grades)
        x = np.arange(len(grades))
        y = np.array(grades)
        n = len(grades)
        slope = float(
            (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x) ** 2)
        )
        trend_map[pid] = (slope, direction.value)

    return trend_map


async def build_draft_board(
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
    async with get_connection() as conn:
        cur = conn.cursor()

        query = """
            SELECT id, name, position, team, class_year,
                   composite_grade, current_status
            FROM scouting.players
            WHERE current_status IN ('active', 'draft_eligible')
        """
        params: list = []

        if class_year:
            query += " AND class_year = %s"
            params.append(class_year)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        query += " ORDER BY composite_grade DESC NULLS LAST LIMIT %s"
        params.append(limit * 2)  # Get extra for filtering

        await cur.execute(query, params)
        rows = await cur.fetchall()

        player_ids = [row[0] for row in rows]

        # Batch-load PFF grades and trends (2 queries instead of 2N)
        pff_map = await _batch_load_pff_grades(conn, player_ids)
        trend_map = await _batch_load_trends(conn, player_ids)

        players = []
        for row in rows:
            player_id, name, pos, team, year, grade, status = row

            pff_grade = pff_map.get(player_id)
            slope, direction = trend_map.get(player_id, (0.0, TrendDirection.UNKNOWN.value))

            draft_score = calculate_draft_score(
                composite_grade=grade,
                pff_grade=pff_grade,
                trend_slope=slope,
            )

            projection = get_projection(draft_score)

            players.append(
                DraftPlayer(
                    player_id=player_id,
                    name=name,
                    position=pos or "Unknown",
                    team=team or "Unknown",
                    class_year=year,
                    draft_score=round(draft_score, 1),
                    projection=projection,
                    composite_grade=grade,
                    pff_grade=round(pff_grade, 1) if pff_grade else None,
                    trend_direction=direction,
                )
            )

        # Sort by draft score
        players.sort(key=lambda x: x.draft_score, reverse=True)
        return players[:limit]


async def get_position_rankings(position: str, limit: int = 25) -> list[DraftPlayer]:
    """Get draft rankings for a specific position."""
    return await build_draft_board(position=position, limit=limit)


# TODO: expose via GET /teams/{name}/draft-prospects endpoint
async def get_team_draft_prospects(team: str) -> list[DraftPlayer]:
    """Get draft-eligible players for a team."""
    async with get_connection() as conn:
        cur = conn.cursor()

        await cur.execute(
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
        rows = await cur.fetchall()

        player_ids = [row[0] for row in rows]

        # Batch-load PFF grades and trends (2 queries instead of 2N)
        pff_map = await _batch_load_pff_grades(conn, player_ids)
        trend_map = await _batch_load_trends(conn, player_ids)

        players = []
        for row in rows:
            player_id, name, pos, team_name, year, grade, status = row

            pff_grade = pff_map.get(player_id)
            slope, direction = trend_map.get(player_id, (0.0, TrendDirection.UNKNOWN.value))

            draft_score = calculate_draft_score(
                composite_grade=grade,
                pff_grade=pff_grade,
                trend_slope=slope,
            )

            players.append(
                DraftPlayer(
                    player_id=player_id,
                    name=name,
                    position=pos or "Unknown",
                    team=team_name or "Unknown",
                    class_year=year,
                    draft_score=round(draft_score, 1),
                    projection=get_projection(draft_score),
                    composite_grade=grade,
                    pff_grade=round(pff_grade, 1) if pff_grade else None,
                    trend_direction=direction,
                )
            )

        players.sort(key=lambda x: x.draft_score, reverse=True)
        return players
