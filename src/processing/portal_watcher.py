"""Portal watcher: detect high-value transfer portal entrants and fire alerts."""

import logging
from dataclasses import dataclass

from ..storage.db import (
    create_alert,
    fire_alert,
    get_connection,
    get_player_pff_grades,
    get_scouting_player,
)

logger = logging.getLogger(__name__)

PORTAL_VALUE_THRESHOLD = 80
SYSTEM_USER_ID = "system"

# Scoring weights (must sum to 1.0)
WEIGHT_COMPOSITE = 0.40
WEIGHT_PFF = 0.40
WEIGHT_SENTIMENT = 0.20


@dataclass
class PortalValueResult:
    """Computed portal value score for a single player."""

    player_id: int
    player_name: str
    score: float
    composite_grade: int | None
    pff_grade: float | None
    avg_sentiment: float | None


async def _get_recent_portal_entries(
    conn,
    hours: int = 24,
) -> list[dict]:
    """Return transfer_events with event_type='entered' created in the last *hours*."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT te.id, te.player_id, te.from_team, te.event_date, te.created_at
        FROM scouting.transfer_events te
        WHERE te.event_type = 'entered'
          AND te.created_at >= NOW() - MAKE_INTERVAL(hours => %s)
        ORDER BY te.created_at DESC
        """,
        (hours,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def _get_avg_sentiment(conn, player_id: int) -> float | None:
    """Return average sentiment_score across all reports linked to *player_id*."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT AVG(sentiment_score)
        FROM scouting.reports
        WHERE %s = ANY(player_ids)
          AND sentiment_score IS NOT NULL
        """,
        (player_id,),
    )
    row = await cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def compute_portal_value_score(
    composite_grade: int | None,
    pff_grade: float | None,
    avg_sentiment: float | None,
) -> float:
    """Compute a 0-100 Portal Value Score.

    Components (when available):
      - composite_grade (0-100): scouting evaluation  — weight 40 %
      - pff_grade (0-100): PFF overall grade           — weight 40 %
      - avg_sentiment (-1 to 1 → scaled to 0-100)      — weight 20 %

    Missing components are excluded and weights are re-normalised over the
    components that *are* present so the score stays on a 0-100 scale.
    """
    parts: list[tuple[float, float]] = []

    if composite_grade is not None:
        parts.append((float(composite_grade), WEIGHT_COMPOSITE))

    if pff_grade is not None:
        parts.append((float(pff_grade), WEIGHT_PFF))

    if avg_sentiment is not None:
        # Map -1…1 → 0…100
        scaled = (avg_sentiment + 1) * 50
        parts.append((scaled, WEIGHT_SENTIMENT))

    if not parts:
        return 0.0

    total_weight = sum(w for _, w in parts)
    return round(sum(val * (w / total_weight) for val, w in parts), 1)


async def _ensure_portal_alert(conn, player_id: int, player_name: str) -> int:
    """Return the alert id for a system portal_entry alert, creating one if needed."""
    cur = conn.cursor()
    alert_name = f"portal-value-{player_id}"

    await cur.execute(
        """
        SELECT id FROM scouting.alerts
        WHERE user_id = %s AND name = %s
        """,
        (SYSTEM_USER_ID, alert_name),
    )
    row = await cur.fetchone()
    if row:
        return row[0]

    alert_id = await create_alert(
        conn,
        user_id=SYSTEM_USER_ID,
        name=alert_name,
        alert_type="portal_entry",
        player_id=player_id,
        threshold={"min_score": PORTAL_VALUE_THRESHOLD},
    )
    logger.info("Created portal_entry alert %d for %s", alert_id, player_name)
    return alert_id


async def evaluate_portal_entrant(conn, player_id: int) -> PortalValueResult | None:
    """Score a single portal entrant. Returns None if the player doesn't exist.
    
    Automatically triggers a profile refresh to ensure we are scoring with the
    freshest AI intelligence possible.
    """
    from ..processing.aggregation import refresh_player_sentiment
    
    # Force a refresh of sentiment/traits before scoring
    try:
        await refresh_player_sentiment(player_id)
    except Exception as e:
        logger.warning("Failed to refresh sentiment for player %d during portal evaluation: %s", player_id, e)

    player = await get_scouting_player(conn, player_id)
    if not player:
        logger.warning("Player %d not found in scouting.players — skipping", player_id)
        return None

    composite_grade = player.get("composite_grade")

    # Latest PFF overall grade (season-level first, then weekly)
    pff_rows = await get_player_pff_grades(conn, player_id)
    pff_grade = float(pff_rows[0]["overall_grade"]) if pff_rows else None

    avg_sentiment = await _get_avg_sentiment(conn, player_id)

    score = compute_portal_value_score(composite_grade, pff_grade, avg_sentiment)

    return PortalValueResult(
        player_id=player_id,
        player_name=player["name"],
        score=score,
        composite_grade=composite_grade,
        pff_grade=pff_grade,
        avg_sentiment=round(avg_sentiment, 2) if avg_sentiment is not None else None,
    )


async def run_portal_watcher(
    *,
    hours: int = 24,
    threshold: float = PORTAL_VALUE_THRESHOLD,
) -> dict:
    """Main entry-point: scan recent portal entries and fire alerts for high-value players.

    Returns a summary dict suitable for pipeline logging.
    """
    async with get_connection() as conn:
        entries = await _get_recent_portal_entries(conn, hours=hours)
        logger.info("Found %d portal entries in the last %d hours", len(entries), hours)

        results: list[PortalValueResult] = []
        fired: list[dict] = []

        for entry in entries:
            player_id = entry["player_id"]
            result = await evaluate_portal_entrant(conn, player_id)
            if result is None:
                continue
            results.append(result)

            if result.score >= threshold:
                alert_id = await _ensure_portal_alert(conn, player_id, result.player_name)
                history_id = await fire_alert(
                    conn,
                    alert_id,
                    trigger_data={
                        "portal_value_score": result.score,
                        "composite_grade": result.composite_grade,
                        "pff_grade": result.pff_grade,
                        "avg_sentiment": result.avg_sentiment,
                        "from_team": entry.get("from_team"),
                    },
                    message=(
                        f"High-value portal entrant: {result.player_name} "
                        f"(score {result.score}/{100})"
                    ),
                )
                fired.append(
                    {
                        "player_id": player_id,
                        "player_name": result.player_name,
                        "score": result.score,
                        "alert_id": alert_id,
                        "history_id": history_id,
                    }
                )
                logger.info(
                    "Fired portal-value alert for %s (score %.1f)",
                    result.player_name,
                    result.score,
                )

    return {
        "entries_scanned": len(entries),
        "players_scored": len(results),
        "alerts_fired": len(fired),
        "fired_details": fired,
    }
