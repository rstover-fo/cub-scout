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
            pff_grade = float(pff_grades[0]["overall_grade"]) if pff_grades else None

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
            player_id, name, pos, team_name, year, grade, status = row

            pff_grades = get_player_pff_grades(conn, player_id)
            pff_grade = float(pff_grades[0]["overall_grade"]) if pff_grades else None

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
                team=team_name or "Unknown",
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
