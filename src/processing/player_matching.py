"""Player matching against roster and recruit data."""

import logging
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from ..storage.db import find_similar_by_embedding, get_connection, insert_pending_link
from .embeddings import build_identity_text, generate_embedding

logger = logging.getLogger(__name__)

# Minimum score to consider a match
MATCH_THRESHOLD = 80

# Vector match thresholds
VECTOR_MATCH_HIGH_CONFIDENCE = 0.92  # Accept automatically
VECTOR_MATCH_LOW_CONFIDENCE = 0.80  # Send to review queue


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
    match_method: Literal["deterministic", "vector", "fuzzy"] = "fuzzy"


def fuzzy_match_name(name1: str, name2: str) -> float:
    """Calculate fuzzy match score between two names.

    Returns score from 0-100.
    """
    # Normalize names
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()

    # Use token sort ratio which handles word order differences
    return fuzz.token_sort_ratio(n1, n2)


def find_deterministic_match(
    name: str,
    team: str,
    year: int = 2025,
) -> PlayerMatch | None:
    """Tier 1: Exact name + team + year match.

    Returns 100% confidence match or None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Exact match on name (first + last) + team + year
        cur.execute(
            """
            SELECT id, first_name, last_name, team, position, year
            FROM core.roster
            WHERE LOWER(first_name || ' ' || last_name) = LOWER(%s)
            AND LOWER(team) = LOWER(%s)
            AND year = %s
            LIMIT 1
            """,
            (name, team, year),
        )
        row = cur.fetchone()

        if row:
            player_id, first, last, player_team, player_pos, player_year = row
            return PlayerMatch(
                source="roster",
                source_id=str(player_id),
                first_name=first,
                last_name=last,
                team=player_team,
                position=player_pos,
                year=player_year,
                confidence=100.0,
                match_method="deterministic",
            )

        return None
    finally:
        cur.close()
        conn.close()


def find_deterministic_match_by_athlete_id(
    athlete_id: str,
) -> PlayerMatch | None:
    """Tier 1: Match via recruiting.recruits.athlete_id -> core.roster.id.

    Returns 100% confidence match or None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT r.id, r.first_name, r.last_name, r.team, r.position, r.year
            FROM core.roster r
            JOIN recruiting.recruits rec ON rec.athlete_id = r.id
            WHERE rec.athlete_id = %s
            LIMIT 1
            """,
            (athlete_id,),
        )
        row = cur.fetchone()

        if row:
            player_id, first, last, player_team, player_pos, player_year = row
            return PlayerMatch(
                source="roster",
                source_id=str(player_id),
                first_name=first,
                last_name=last,
                team=player_team,
                position=player_pos,
                year=player_year,
                confidence=100.0,
                match_method="deterministic",
            )

        return None
    finally:
        cur.close()
        conn.close()


def find_vector_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int = 2025,
) -> PlayerMatch | None:
    """Tier 2: Vector similarity match using embeddings.

    Generates embedding for query, searches pgvector for similar players.
    Only accepts matches with similarity >= 0.92 AND team match.

    Args:
        name: Player name to match
        team: Optional team filter (required for high confidence)
        position: Optional position (included in embedding)
        year: Roster year

    Returns:
        PlayerMatch if high-confidence match found, else None
    """
    # Build identity text for query
    query_player = {
        "name": name,
        "team": team or "Unknown",
        "year": year,
        "position": position,
    }
    identity_text = build_identity_text(query_player)

    # Generate embedding for query
    try:
        result = generate_embedding(identity_text)
    except Exception:
        # If embedding fails, fall through to fuzzy
        return None

    conn = get_connection()
    try:
        # Search for similar players
        similar = find_similar_by_embedding(
            conn,
            embedding=result.embedding,
            limit=5,
        )

        if not similar:
            return None

        # Find best match with team filter
        for candidate in similar:
            similarity = candidate["similarity"]

            # Parse identity_text to get team: "Name | Position | Team | Year"
            parts = candidate["identity_text"].split(" | ")
            candidate_team = parts[2] if len(parts) >= 3 else None

            # Require team match for acceptance
            if team and candidate_team and team.lower() != candidate_team.lower():
                continue

            # Only accept high-confidence matches
            if similarity >= VECTOR_MATCH_HIGH_CONFIDENCE:
                # Fetch full player data from roster
                roster_id = candidate["roster_id"]
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, first_name, last_name, team, position, year
                    FROM core.roster
                    WHERE id = %s
                    """,
                    (roster_id,),
                )
                row = cur.fetchone()
                cur.close()

                if row:
                    player_id, first, last, player_team, player_pos, player_year = row
                    return PlayerMatch(
                        source="roster",
                        source_id=str(player_id),
                        first_name=first,
                        last_name=last,
                        team=player_team,
                        position=player_pos,
                        year=player_year,
                        confidence=similarity * 100,
                        match_method="vector",
                    )

        return None
    finally:
        conn.close()


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
    athlete_id: str | None = None,
    year: int = 2025,
) -> PlayerMatch | None:
    """Find best match across all tiers.

    Simplified version that doesn't create pending links.
    Use match_player_with_review() for full review queue support.

    Matching order:
    1. Deterministic (athlete_id or exact match)
    2. Vector similarity
    3. Fuzzy matching
    """
    # Tier 1: Deterministic
    if athlete_id:
        match = find_deterministic_match_by_athlete_id(athlete_id)
        if match:
            return match

    if team:
        match = find_deterministic_match(name, team, year)
        if match:
            return match

    # Tier 2: Vector
    match = find_vector_match(name, team=team, position=position, year=year)
    if match:
        return match

    # Tier 3: Fuzzy (existing logic, but with method tracking)
    match = find_roster_match(name, team=team, position=position, year=year)
    if match and match.confidence >= 90:
        match.match_method = "fuzzy"
        return match

    recruit_match = find_recruit_match(name, team=team, position=position)
    if recruit_match:
        if not match or recruit_match.confidence > match.confidence:
            recruit_match.match_method = "fuzzy"
            return recruit_match

    if match:
        match.match_method = "fuzzy"

    return match


def match_player_with_review(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int = 2025,
    source_context: dict | None = None,
    athlete_id: str | None = None,
) -> tuple[PlayerMatch | None, int | None]:
    """Match player with automatic review queue for low-confidence matches.

    Three-tier matching:
    1. Deterministic: athlete_id link or exact name+team+year (100%)
    2. Vector: pgvector similarity >= 0.92 with team match
    3. Fuzzy: rapidfuzz token_sort_ratio >= 80

    Matches with 0.80-0.92 confidence go to pending_links for review.

    Args:
        name: Player name to match
        team: Optional team filter
        position: Optional position
        year: Roster year
        source_context: Additional context for review queue
        athlete_id: Optional recruit athlete_id for deterministic match

    Returns:
        Tuple of (PlayerMatch or None, pending_link_id or None)
    """
    # Tier 1: Deterministic
    if athlete_id:
        match = find_deterministic_match_by_athlete_id(athlete_id)
        if match:
            return (match, None)

    if team:
        match = find_deterministic_match(name, team, year)
        if match:
            return (match, None)

    # Tier 2: Vector similarity
    vector_match = find_vector_match(name, team=team, position=position, year=year)
    if vector_match:
        return (vector_match, None)

    # Tier 3: Fuzzy matching (existing logic)
    fuzzy_match = find_roster_match(name, team=team, position=position, year=year)

    # Check if we need to create a pending link
    if fuzzy_match:
        confidence_normalized = fuzzy_match.confidence / 100.0

        # High confidence fuzzy match - return it
        if confidence_normalized >= VECTOR_MATCH_HIGH_CONFIDENCE:
            fuzzy_match.match_method = "fuzzy"
            return (fuzzy_match, None)

        # Medium confidence - create pending link for review
        if confidence_normalized >= VECTOR_MATCH_LOW_CONFIDENCE:
            conn = get_connection()
            try:
                pending_id = insert_pending_link(
                    conn,
                    source_name=name,
                    source_team=team,
                    source_context=source_context,
                    candidate_roster_id=fuzzy_match.source_id,
                    match_score=confidence_normalized,
                    match_method="fuzzy",
                )
                return (None, pending_id)
            finally:
                conn.close()

    # Try recruits as fallback
    recruit_match = find_recruit_match(name, team=team, position=position, year=year)
    if recruit_match and recruit_match.confidence >= MATCH_THRESHOLD:
        recruit_match.match_method = "fuzzy"
        return (recruit_match, None)

    # No match found
    return (None, None)
