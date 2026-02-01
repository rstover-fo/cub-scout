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
    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x) ** 2)

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
            t for t in timeline if t["snapshot_date"] >= cutoff and t["grade_at_time"] is not None
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
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x) ** 2)

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
                trends.append(
                    {
                        "player_id": player_id,
                        "name": name,
                        "team": team,
                        "position": position,
                        **trend.to_dict(),
                    }
                )

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
                trends.append(
                    {
                        "player_id": player_id,
                        "name": name,
                        "team": team,
                        "position": position,
                        **trend.to_dict(),
                    }
                )

        # Sort by slope ascending (most negative first)
        trends.sort(key=lambda x: x["slope"])
        return trends[:limit]

    finally:
        cur.close()
        conn.close()
