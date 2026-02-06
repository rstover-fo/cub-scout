"""PFF grade pipeline - fetch and store PFF grades for scouting players."""

import logging
import os

from ..clients.pff import PFFClient
from ..storage.db import get_connection, upsert_pff_grade

logger = logging.getLogger(__name__)


async def fetch_and_store_pff_grade(
    client: PFFClient,
    conn,
    player: dict,
) -> bool | None:
    """Fetch a PFF grade for a single player and store it.

    Args:
        client: Initialized PFF API client.
        conn: Async database connection.
        player: Dict with keys id, name, team, position.

    Returns:
        True if a grade was stored, False if not found, None on error.
    """
    player_id = player["id"]
    name = player["name"]
    team = player.get("team")

    try:
        pff_grade = await client.get_player_by_name(name, team=team)
        if pff_grade is None:
            logger.debug("No PFF grade found for %s (%s)", name, team)
            return False

        position_grades = {
            k: getattr(pff_grade, k)
            for k in (
                "passing_grade",
                "rushing_grade",
                "receiving_grade",
                "blocking_grade",
                "defense_grade",
                "coverage_grade",
                "pass_rush_grade",
                "run_defense_grade",
            )
            if getattr(pff_grade, k) is not None
        }

        await upsert_pff_grade(
            conn,
            player_id=player_id,
            pff_player_id=pff_grade.player_id,
            season=pff_grade.season,
            overall_grade=pff_grade.overall_grade,
            position_grades=position_grades or None,
            snaps=pff_grade.snaps,
        )
        logger.info(
            "Stored PFF grade for %s (overall=%.1f, snaps=%d)",
            name,
            pff_grade.overall_grade,
            pff_grade.snaps,
        )
        return True

    except Exception:
        logger.exception("Error fetching PFF grade for %s", name)
        return None


async def run_pff_pipeline(batch_size: int = 50) -> dict:
    """Fetch and store PFF grades for players missing recent data.

    Args:
        batch_size: Max players to process per run.

    Returns:
        Stats dict with players_checked, grades_stored, errors.
    """
    api_key = os.environ.get("PFF_API_KEY")
    if not api_key:
        logger.warning("PFF_API_KEY not set — skipping PFF pipeline")
        return {"players_checked": 0, "grades_stored": 0, "errors": 0}

    stats = {"players_checked": 0, "grades_stored": 0, "errors": 0}

    async with get_connection() as conn:
        cur = conn.cursor()
        await cur.execute(
            """
            SELECT p.id, p.name, p.team, p.position
            FROM scouting.players p
            WHERE NOT EXISTS (
                SELECT 1 FROM scouting.pff_grades g
                WHERE g.player_id = p.id
                  AND g.fetched_at > NOW() - INTERVAL '30 days'
            )
            ORDER BY p.last_updated DESC
            LIMIT %s
            """,
            (batch_size,),
        )
        columns = [desc[0] for desc in cur.description]
        rows = await cur.fetchall()
        players = [dict(zip(columns, row)) for row in rows]

    if not players:
        logger.info("No players need PFF grade updates")
        return stats

    logger.info("Fetching PFF grades for %d players", len(players))

    async with PFFClient(api_key=api_key) as client:
        async with get_connection() as conn:
            for player in players:
                stats["players_checked"] += 1
                result = await fetch_and_store_pff_grade(client, conn, player)
                if result is True:
                    stats["grades_stored"] += 1
                elif result is None:
                    stats["errors"] += 1

    logger.info(
        "PFF pipeline complete: checked=%d, stored=%d, errors=%d",
        stats["players_checked"],
        stats["grades_stored"],
        stats["errors"],
    )
    return stats
