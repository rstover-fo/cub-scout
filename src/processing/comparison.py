"""Player comparison engine for head-to-head analysis."""

import logging
from dataclasses import dataclass

from ..storage.db import (
    find_similar_by_embedding,
    get_connection,
    get_player_pff_grades,
    get_scouting_player,
)

logger = logging.getLogger(__name__)

TRAIT_CATEGORIES = [
    "arm_strength",
    "accuracy",
    "mobility",
    "decision_making",
    "leadership",
    "athleticism",
    "technique",
    "football_iq",
    "consistency",
    "upside",
]


@dataclass
class PlayerComparison:
    """Result of comparing two players."""

    player1: dict
    player2: dict
    trait_comparison: list[dict]
    grade_comparison: dict
    pff_comparison: dict | None
    advantages: dict


def build_radar_data(
    traits: dict,
    max_value: float = 10.0,
) -> list[dict]:
    """Build radar chart data from player traits.

    Args:
        traits: Dict of trait name -> value
        max_value: Maximum value for normalization

    Returns:
        List of {trait, value} dicts for radar chart
    """
    if not traits:
        return []

    result = []
    for trait, value in traits.items():
        normalized = (value / max_value) * 10 if max_value != 10 else value
        result.append(
            {
                "trait": trait,
                "value": round(normalized, 1),
            }
        )

    return result


async def compare_players(player1_id: int, player2_id: int) -> PlayerComparison:
    """Compare two players head-to-head.

    Args:
        player1_id: First player ID
        player2_id: Second player ID

    Returns:
        PlayerComparison with detailed comparison data
    """
    async with get_connection() as conn:
        p1 = await get_scouting_player(conn, player1_id)
        p2 = await get_scouting_player(conn, player2_id)

        if not p1 or not p2:
            raise ValueError(f"Player not found: {player1_id if not p1 else player2_id}")

        # Trait comparison
        p1_traits = p1.get("traits") or {}
        p2_traits = p2.get("traits") or {}

        trait_comparison = []
        p1_advantages = []
        p2_advantages = []

        for trait in TRAIT_CATEGORIES:
            v1 = p1_traits.get(trait)
            v2 = p2_traits.get(trait)

            if v1 is not None or v2 is not None:
                diff = (v1 or 0) - (v2 or 0)
                trait_comparison.append(
                    {
                        "trait": trait,
                        "player1_value": v1,
                        "player2_value": v2,
                        "difference": diff,
                    }
                )

                if diff > 0.5:
                    p1_advantages.append(trait)
                elif diff < -0.5:
                    p2_advantages.append(trait)

        # Grade comparison
        grade_comparison = {
            "player1_grade": p1.get("composite_grade"),
            "player2_grade": p2.get("composite_grade"),
            "difference": ((p1.get("composite_grade") or 0) - (p2.get("composite_grade") or 0)),
        }

        # PFF comparison
        pff1 = await get_player_pff_grades(conn, player1_id)
        pff2 = await get_player_pff_grades(conn, player2_id)

        pff_comparison = None
        if pff1 and pff2:
            pff_comparison = {
                "player1_overall": pff1[0].get("overall_grade"),
                "player2_overall": pff2[0].get("overall_grade"),
                "player1_snaps": pff1[0].get("snaps"),
                "player2_snaps": pff2[0].get("snaps"),
            }

        return PlayerComparison(
            player1={
                "id": p1["id"],
                "name": p1["name"],
                "team": p1.get("team"),
                "position": p1.get("position"),
                "radar_data": build_radar_data(p1_traits),
            },
            player2={
                "id": p2["id"],
                "name": p2["name"],
                "team": p2.get("team"),
                "position": p2.get("position"),
                "radar_data": build_radar_data(p2_traits),
            },
            trait_comparison=trait_comparison,
            grade_comparison=grade_comparison,
            pff_comparison=pff_comparison,
            advantages={
                "player1": p1_advantages,
                "player2": p2_advantages,
            },
        )


async def find_similar_players(
    player_id: int,
    limit: int = 5,
) -> list[dict]:
    """Find players with similar profiles using pgvector embeddings.

    Falls back to trait-based cosine similarity if no embedding exists.
    """
    async with get_connection() as conn:
        player = await get_scouting_player(conn, player_id)
        if not player:
            return []

        cur = conn.cursor()

        # Try pgvector similarity via precomputed embeddings
        roster_player_id = player.get("roster_player_id")
        if roster_player_id:
            await cur.execute(
                "SELECT embedding FROM scouting.player_embeddings WHERE roster_id = %s",
                (str(roster_player_id),),
            )
            emb_row = await cur.fetchone()

            if emb_row and emb_row[0]:
                similar = await find_similar_by_embedding(
                    conn,
                    embedding=emb_row[0],
                    limit=limit,
                    exclude_roster_id=str(roster_player_id),
                )
                # Join back to scouting.players for full info
                results = []
                for s in similar:
                    await cur.execute(
                        """
                        SELECT id, name, team, position
                        FROM scouting.players
                        WHERE roster_player_id = %s
                        """,
                        (int(s["roster_id"]) if s["roster_id"].isdigit() else None,),
                    )
                    p_row = await cur.fetchone()
                    if p_row:
                        results.append(
                            {
                                "player_id": p_row[0],
                                "name": p_row[1],
                                "team": p_row[2],
                                "position": p_row[3],
                                "similarity": round(float(s["similarity"]), 3),
                            }
                        )
                return results

        # Fallback: trait-based cosine similarity
        if not player.get("traits"):
            return []

        logger.warning("No embedding for player %d, using trait-based similarity", player_id)

        import numpy as np

        player_traits = player["traits"]
        player_vector = np.array([player_traits.get(t, 0) for t in TRAIT_CATEGORIES])

        if np.linalg.norm(player_vector) == 0:
            return []

        await cur.execute(
            """
            SELECT id, name, team, position, traits
            FROM scouting.players
            WHERE id != %s
            AND traits IS NOT NULL
            AND traits != '{}'
            """,
            (player_id,),
        )

        similarities = []
        for row in await cur.fetchall():
            other_id, name, team, position, other_traits = row
            if not other_traits:
                continue

            other_vector = np.array([other_traits.get(t, 0) for t in TRAIT_CATEGORIES])

            if np.linalg.norm(other_vector) == 0:
                continue

            similarity = np.dot(player_vector, other_vector) / (
                np.linalg.norm(player_vector) * np.linalg.norm(other_vector)
            )

            similarities.append(
                {
                    "player_id": other_id,
                    "name": name,
                    "team": team,
                    "position": position,
                    "similarity": round(float(similarity), 3),
                }
            )

        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:limit]
