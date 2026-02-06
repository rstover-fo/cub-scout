# src/processing/grading.py
"""Player grading and timeline update pipeline."""

import logging
from datetime import date

from ..storage.db import (
    get_connection,
    insert_timeline_snapshot,
)
from .aggregation import aggregate_player_profile

logger = logging.getLogger(__name__)


async def get_players_needing_update(limit: int = 50) -> list[dict]:
    """Get players who haven't been graded recently."""
    async with get_connection() as conn:
        cur = conn.cursor()

        # Players with reports but no grade, or stale grades
        await cur.execute(
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
        return [dict(zip(columns, row)) for row in await cur.fetchall()]


async def update_player_grade(player_id: int) -> dict:
    """Aggregate reports, update grade, and create timeline snapshot."""
    async with get_connection() as conn:
        # Get aggregated data
        agg = await aggregate_player_profile(player_id)

        # Update player record
        cur = conn.cursor()
        await cur.execute(
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
        await conn.commit()

        # Create timeline snapshot
        await insert_timeline_snapshot(
            conn,
            player_id=player_id,
            snapshot_date=date.today(),
            sentiment_score=agg["sentiment_score"],
            grade_at_time=agg["composite_grade"],
            traits_at_time=agg["traits"],
            sources_count=agg["report_count"],
        )

        return agg


async def run_grading_pipeline(batch_size: int = 50) -> dict:
    """Run grading pipeline on players needing updates."""
    players = await get_players_needing_update(batch_size)
    logger.info(f"Found {len(players)} players needing grade updates")

    updated = 0
    errors = 0

    for player in players:
        try:
            result = await update_player_grade(player["id"])
            logger.debug(f"Updated {player['name']}: grade={result['composite_grade']}")
            updated += 1
        except Exception as e:
            logger.error(f"Error grading {player['name']}: {e}")
            errors += 1

    return {
        "players_found": len(players),
        "players_updated": updated,
        "errors": errors,
    }
