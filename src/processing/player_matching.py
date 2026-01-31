"""Player matching against roster and recruit data."""

import logging
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from ..storage.db import get_connection

logger = logging.getLogger(__name__)

# Minimum score to consider a match
MATCH_THRESHOLD = 80


@dataclass
class PlayerMatch:
    """A matched player from roster or recruit data."""

    source: Literal["roster", "recruit"]
    source_id: str
    first_name: str
    last_name: str
    team: str
    position: str | None
    year: int | None
    confidence: float  # 0-100


def fuzzy_match_name(name1: str, name2: str) -> float:
    """Calculate fuzzy match score between two names.

    Returns score from 0-100.
    """
    # Normalize names
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()

    # Use token sort ratio which handles word order differences
    return fuzz.token_sort_ratio(n1, n2)


def find_roster_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int = 2024,
) -> PlayerMatch | None:
    """Find best matching player in core.roster.

    Args:
        name: Player name to match.
        team: Optional team filter.
        position: Optional position filter.
        year: Roster year to search.

    Returns:
        PlayerMatch if found above threshold, else None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Build query with optional filters
        query = """
            SELECT id, first_name, last_name, team, position, year
            FROM core.roster
            WHERE year = %s
        """
        params = [year]

        if team:
            query += " AND LOWER(team) = LOWER(%s)"
            params.append(team)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        cur.execute(query, params)
        candidates = cur.fetchall()

        best_match = None
        best_score = 0

        for row in candidates:
            player_id, first, last, player_team, player_pos, player_year = row
            full_name = f"{first} {last}"

            score = fuzzy_match_name(name, full_name)

            if score > best_score and score >= MATCH_THRESHOLD:
                best_score = score
                best_match = PlayerMatch(
                    source="roster",
                    source_id=str(player_id),
                    first_name=first,
                    last_name=last,
                    team=player_team,
                    position=player_pos,
                    year=player_year,
                    confidence=score,
                )

        return best_match

    finally:
        cur.close()
        conn.close()


def find_recruit_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int | None = None,
) -> PlayerMatch | None:
    """Find best matching player in recruiting.recruits.

    Args:
        name: Player name to match.
        team: Optional committed_to filter.
        position: Optional position filter.
        year: Optional recruiting year filter.

    Returns:
        PlayerMatch if found above threshold, else None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        query = """
            SELECT id, name, committed_to, position, recruiting_year
            FROM recruiting.recruits
            WHERE 1=1
        """
        params = []

        if team:
            query += " AND LOWER(committed_to) = LOWER(%s)"
            params.append(team)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        if year:
            query += " AND recruiting_year = %s"
            params.append(year)

        cur.execute(query, params)
        candidates = cur.fetchall()

        best_match = None
        best_score = 0

        for row in candidates:
            recruit_id, recruit_name, committed_to, recruit_pos, recruit_year = row

            score = fuzzy_match_name(name, recruit_name)

            if score > best_score and score >= MATCH_THRESHOLD:
                best_score = score
                # Split name for consistency
                parts = recruit_name.split(maxsplit=1)
                first = parts[0] if parts else ""
                last = parts[1] if len(parts) > 1 else ""

                best_match = PlayerMatch(
                    source="recruit",
                    source_id=str(recruit_id),
                    first_name=first,
                    last_name=last,
                    team=committed_to or "",
                    position=recruit_pos,
                    year=recruit_year,
                    confidence=score,
                )

        return best_match

    finally:
        cur.close()
        conn.close()


def find_best_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
) -> PlayerMatch | None:
    """Find best match across both roster and recruit data.

    Tries roster first (current players), then recruits.
    """
    # Try current roster first
    match = find_roster_match(name, team=team, position=position, year=2024)
    if match and match.confidence >= 90:
        return match

    # Try recruits
    recruit_match = find_recruit_match(name, team=team, position=position)

    # Return higher confidence match
    if recruit_match:
        if not match or recruit_match.confidence > match.confidence:
            return recruit_match

    return match
