"""Entity linking pipeline - connects reports to player profiles."""

import logging
from datetime import datetime

from ..storage.db import (
    get_connection,
    link_report_to_player,
    upsert_scouting_player,
)
from .entity_extraction import extract_player_mentions, extract_player_mentions_claude
from .player_matching import match_player_with_review

logger = logging.getLogger(__name__)


async def link_report_entities(
    report: dict,
    use_claude: bool = False,
) -> list[int]:
    """Extract and link player entities from a report.

    Args:
        report: Report dict with id, raw_text, team_ids.
        use_claude: Use Claude for entity extraction (more accurate, costs tokens).

    Returns:
        List of scouting.players IDs that were linked.
    """
    async with get_connection() as conn:
        linked_player_ids = []

        # Extract player mentions
        if use_claude:
            mentions = await extract_player_mentions_claude(report["raw_text"])
            names = [(m["name"], m.get("position"), m.get("team")) for m in mentions]
        else:
            names = [(name, None, None) for name in extract_player_mentions(report["raw_text"])]

        # Get team context from report
        team_context = report.get("team_ids", [])
        default_team = team_context[0] if team_context else None

        for name, position, team in names:
            # Try to find existing roster/recruit match
            match, pending_link_id = await match_player_with_review(
                name,
                team=team or default_team,
                position=position,
                year=2025,
                source_context={
                    "report_id": report["id"],
                    "source_url": report.get("source_url"),
                },
            )

            if pending_link_id:
                logger.info(f"Created pending link {pending_link_id} for {name}")
                continue  # Skip this player, needs review

            if match:
                # Create/update scouting player linked to roster/recruit
                player_id = await upsert_scouting_player(
                    conn,
                    name=f"{match.first_name} {match.last_name}",
                    team=match.team,
                    position=match.position,
                    class_year=match.year,
                    current_status="active" if match.source == "roster" else "recruit",
                    roster_player_id=int(match.source_id) if match.source == "roster" else None,
                    recruit_id=int(match.source_id) if match.source == "recruit" else None,
                )
            else:
                # Create scouting player without link (new mention)
                player_id = await upsert_scouting_player(
                    conn,
                    name=name,
                    team=team or default_team or "Unknown",
                    position=position,
                    class_year=datetime.now().year,  # Dynamic current year
                    current_status="active",
                )

            # Link report to player
            await link_report_to_player(conn, report["id"], player_id)
            linked_player_ids.append(player_id)
            logger.debug(f"Linked player {player_id} ({name}) to report {report['id']}")

        return linked_player_ids


async def run_entity_linking(
    batch_size: int = 50,
    use_claude: bool = False,
) -> dict:
    """Run entity linking on processed reports without player links.

    Args:
        batch_size: Number of reports to process.
        use_claude: Use Claude for extraction.

    Returns:
        Stats dict.
    """
    async with get_connection() as conn:
        # Get reports that are processed but have no player links
        cur = conn.cursor()
        await cur.execute(
            """
            SELECT id, source_url, source_name, content_type, raw_text, team_ids
            FROM scouting.reports
            WHERE processed_at IS NOT NULL
            AND (player_ids IS NULL OR array_length(player_ids, 1) IS NULL)
            ORDER BY crawled_at ASC
            LIMIT %s
            """,
            (batch_size,),
        )
        columns = [desc[0] for desc in cur.description]
        reports = [dict(zip(columns, row)) for row in await cur.fetchall()]

    logger.info(f"Found {len(reports)} reports needing entity linking")

    linked = 0
    errors = 0
    total_players = 0

    for report in reports:
        try:
            player_ids = await link_report_entities(report, use_claude=use_claude)
            total_players += len(player_ids)
            linked += 1
        except Exception as e:
            logger.error(f"Error linking report {report['id']}: {e}")
            errors += 1

    return {
        "reports_processed": len(reports),
        "reports_linked": linked,
        "players_linked": total_players,
        "errors": errors,
    }
