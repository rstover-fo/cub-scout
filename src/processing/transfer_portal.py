"""Transfer portal processing and analysis."""

import logging
import re
from datetime import date

from ..storage.db import (
    get_connection,
    get_active_portal_players,
    insert_portal_snapshot,
)

logger = logging.getLogger(__name__)

# Keywords indicating portal activity
PORTAL_KEYWORDS = [
    r"\btransfer portal\b",
    r"\bentered the portal\b",
    r"\bin the portal\b",
    r"\bcommitted to\b.*\btransfer\b",
    r"\bwithdrew from.*(portal|transfer)",
    r"\btransferring to\b",
    r"\btransfer from\b",
]

EVENT_PATTERNS = {
    "entered": [
        r"entered the (transfer )?portal",
        r"in the portal",
        r"entering the portal",
        r"has entered",
    ],
    "committed": [
        r"committed to",
        r"transferring to",
        r"will transfer to",
        r"announces commitment",
    ],
    "withdrawn": [
        r"withdrew from",
        r"withdrawn from the portal",
        r"removed.*from.*portal",
        r"staying at",
    ],
}


def extract_portal_mentions(text: str) -> dict:
    """Extract transfer portal mentions from text.

    Args:
        text: Text to analyze

    Returns:
        Dict with is_portal_related, event_type, confidence
    """
    text_lower = text.lower()

    # Check if portal-related
    is_related = any(re.search(kw, text_lower) for kw in PORTAL_KEYWORDS)

    if not is_related:
        return {
            "is_portal_related": False,
            "event_type": None,
            "confidence": 0.0,
        }

    # Determine event type
    event_type = None
    confidence = 0.5

    for etype, patterns in EVENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                event_type = etype
                confidence = 0.8
                break
        if event_type:
            break

    return {
        "is_portal_related": True,
        "event_type": event_type or "entered",  # Default to entered
        "confidence": confidence,
    }


def predict_destination(
    position: str,
    from_team: str,
    composite_grade: int | None = None,
    class_year: int | None = None,
) -> list[dict]:
    """Predict likely transfer destinations.

    Uses historical patterns and player profile to suggest destinations.

    Args:
        position: Player position
        from_team: Team player is leaving
        composite_grade: Player's composite grade
        class_year: Player's class year

    Returns:
        List of {team, probability, reasoning} dicts
    """
    # Historical destination patterns by position and grade tier
    # This is a simplified heuristic - could be enhanced with ML
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get historical commitments for similar players
        cur.execute(
            """
            SELECT te.to_team, COUNT(*) as count
            FROM scouting.transfer_events te
            JOIN scouting.players p ON te.player_id = p.id
            WHERE te.event_type = 'committed'
            AND te.to_team IS NOT NULL
            AND UPPER(p.position) = UPPER(%s)
            AND te.from_team != %s
            GROUP BY te.to_team
            ORDER BY count DESC
            LIMIT 10
            """,
            (position, from_team),
        )

        historical = cur.fetchall()

        if not historical:
            # Return generic predictions based on grade tier
            if composite_grade and composite_grade >= 80:
                return [
                    {"team": "Alabama", "probability": 0.15, "reasoning": "Elite program, high-grade target"},
                    {"team": "Georgia", "probability": 0.15, "reasoning": "Elite program, high-grade target"},
                    {"team": "Ohio State", "probability": 0.12, "reasoning": "Elite program, high-grade target"},
                ]
            else:
                return [
                    {"team": "Unknown", "probability": 0.5, "reasoning": "Insufficient historical data"},
                ]

        total_count = sum(row[1] for row in historical)
        predictions = []

        for team, count in historical[:5]:
            prob = round(count / total_count, 2)
            predictions.append({
                "team": team,
                "probability": prob,
                "reasoning": f"Historical {position} destination ({count} transfers)",
            })

        return predictions

    finally:
        cur.close()
        conn.close()


def generate_portal_snapshot() -> dict:
    """Generate a daily snapshot of portal activity.

    Returns:
        Summary dict of portal state
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get all active portal players
        active = get_active_portal_players(conn, limit=1000)

        # Count by position
        by_position = {}
        for player in active:
            pos = player.get("position") or "Unknown"
            by_position[pos] = by_position.get(pos, 0) + 1

        # Count by conference (if we have that data - simplified for now)
        by_conference = {}  # Would need conference mapping

        # Notable entries (top graded players)
        notable = [
            f"{p['name']} ({p['position']}, {p['composite_grade']})"
            for p in sorted(active, key=lambda x: x.get("composite_grade") or 0, reverse=True)[:10]
        ]

        # Insert snapshot
        snapshot_id = insert_portal_snapshot(
            conn,
            snapshot_date=date.today(),
            total_in_portal=len(active),
            by_position=by_position,
            by_conference=by_conference,
            notable_entries=notable,
        )

        return {
            "snapshot_id": snapshot_id,
            "date": date.today().isoformat(),
            "total_in_portal": len(active),
            "by_position": by_position,
            "notable_entries": notable,
        }

    finally:
        cur.close()
        conn.close()


def analyze_team_portal_impact(team: str) -> dict:
    """Analyze the impact of transfers on a team.

    Args:
        team: Team to analyze

    Returns:
        Impact analysis dict
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get outgoing players (grade lost)
        cur.execute(
            """
            SELECT p.position, p.composite_grade
            FROM scouting.transfer_events te
            JOIN scouting.players p ON te.player_id = p.id
            WHERE te.from_team = %s AND te.event_type = 'entered'
            AND te.event_date >= CURRENT_DATE - INTERVAL '1 year'
            """,
            (team,),
        )
        outgoing = cur.fetchall()
        outgoing_grades = [g for _, g in outgoing if g]
        avg_outgoing = sum(outgoing_grades) / len(outgoing_grades) if outgoing_grades else 0

        # Get incoming players (grade gained)
        cur.execute(
            """
            SELECT p.position, p.composite_grade
            FROM scouting.transfer_events te
            JOIN scouting.players p ON te.player_id = p.id
            WHERE te.to_team = %s AND te.event_type = 'committed'
            AND te.event_date >= CURRENT_DATE - INTERVAL '1 year'
            """,
            (team,),
        )
        incoming = cur.fetchall()
        incoming_grades = [g for _, g in incoming if g]
        avg_incoming = sum(incoming_grades) / len(incoming_grades) if incoming_grades else 0

        # Position group impact
        position_impact = {}
        for pos, grade in outgoing:
            if pos not in position_impact:
                position_impact[pos] = {"lost": 0, "gained": 0}
            position_impact[pos]["lost"] += 1

        for pos, grade in incoming:
            if pos not in position_impact:
                position_impact[pos] = {"lost": 0, "gained": 0}
            position_impact[pos]["gained"] += 1

        return {
            "team": team,
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
            "net_transfers": len(incoming) - len(outgoing),
            "avg_grade_lost": round(avg_outgoing, 1),
            "avg_grade_gained": round(avg_incoming, 1),
            "grade_delta": round(avg_incoming - avg_outgoing, 1),
            "position_impact": position_impact,
        }

    finally:
        cur.close()
        conn.close()
