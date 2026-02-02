"""Entity linking pipeline - connects reports to player profiles."""

import logging

from ..storage.db import (
    get_connection,
    upsert_scouting_player,
    link_report_to_player,
)
from .entity_extraction import extract_player_mentions, extract_player_mentions_claude
from .player_matching import match_player_with_review

logger = logging.getLogger(__name__)


def link_report_entities(
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
    conn = get_connection()
    linked_player_ids = []

    try:
        # Extract player mentions
        if use_claude:
            mentions = extract_player_mentions_claude(report["raw_text"])
            names = [(m["name"], m.get("position"), m.get("team")) for m in mentions]
        else:
            names = [(name, None, None) for name in extract_player_mentions(report["raw_text"])]

        # Get team context from report
        team_context = report.get("team_ids", [])
        default_team = team_context[0] if team_context else None

        for name, position, team in names:
            # Try to find existing roster/recruit match
            match, pending_link_id = match_player_with_review(
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
                player_id = upsert_scouting_player(
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
                player_id = upsert_scouting_player(
                    conn,
                    name=name,
                    team=team or default_team or "Unknown",
                    position=position,
                    class_year=2024,  # Default assumption
                    current_status="active",
                )

            # Link report to player
            link_report_to_player(conn, report["id"], player_id)
            linked_player_ids.append(player_id)
            logger.debug(f"Linked player {player_id} ({name}) to report {report['id']}")

        return linked_player_ids

    finally:
        conn.close()


def run_entity_linking(
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
    conn = get_connection()

    try:
        # Get reports that are processed but have no player links
        cur = conn.cursor()
        cur.execute(
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
        reports = [dict(zip(columns, row)) for row in cur.fetchall()]

    finally:
        conn.close()

    logger.info(f"Found {len(reports)} reports needing entity linking")

    linked = 0
    errors = 0
    total_players = 0

    for report in reports:
        try:
            player_ids = link_report_entities(report, use_claude=use_claude)
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
