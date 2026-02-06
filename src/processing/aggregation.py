# src/processing/aggregation.py
"""Player profile aggregation from scouting reports."""

import logging
import os

import anthropic

from ..config import CLAUDE_MODEL
from ..storage.db import get_connection

logger = logging.getLogger(__name__)


async def get_player_reports(player_id: int) -> list[dict]:
    """Get all reports linked to a player."""
    async with get_connection() as conn:
        cur = conn.cursor()

        await cur.execute(
            """
            SELECT id, source_url, source_name, raw_text, summary,
                   sentiment_score, crawled_at
            FROM scouting.reports
            WHERE %s = ANY(player_ids)
            ORDER BY crawled_at DESC
            """,
            (player_id,),
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in await cur.fetchall()]


def calculate_sentiment_average(reports: list[dict]) -> float | None:
    """Calculate average sentiment from reports."""
    scores = [float(r["sentiment_score"]) for r in reports if r.get("sentiment_score") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def extract_traits_from_reports(reports: list[dict]) -> dict:
    """Use Claude to extract player traits from report summaries.

    Returns dict with trait categories and ratings.
    """
    if not reports:
        return {}

    summaries = "\n\n".join(
        f"- {r.get('summary', r.get('raw_text', ''))[:500]}"
        for r in reports[:10]  # Limit to recent 10
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": f"""Analyze these scouting reports and extract player traits.

Reports:
{summaries}

Return a JSON object with trait categories as keys and ratings (1-10) as values.
Categories: arm_strength, accuracy, mobility, decision_making, leadership,
athleticism, technique, football_iq, consistency, upside

Only include traits that have evidence in the reports. Return only JSON, no other text.

Example: {{"arm_strength": 8, "mobility": 7, "leadership": 9}}""",
            }
        ],
    )

    try:
        import json

        response_text = response.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        return json.loads(response_text)
    except Exception as e:
        logger.warning(f"Failed to parse traits: {e}")
        return {}


def calculate_composite_grade(traits: dict, sentiment: float | None) -> int | None:
    """Calculate composite grade (0-100) from traits and sentiment."""
    if not traits:
        return None

    # Average trait scores (1-10 scale) -> 0-100
    trait_avg = sum(traits.values()) / len(traits)
    base_grade = int(trait_avg * 10)

    # Adjust for sentiment (-1 to 1 scale) -> +/- 5 points
    if sentiment is not None:
        sentiment_bonus = int(sentiment * 5)
        base_grade += sentiment_bonus

    return max(0, min(100, base_grade))


async def aggregate_player_profile(player_id: int) -> dict:
    """Aggregate all data for a player profile.

    Returns dict with sentiment, traits, grade, and report count.
    """
    reports = await get_player_reports(player_id)

    sentiment = calculate_sentiment_average(reports)
    traits = extract_traits_from_reports(reports)
    grade = calculate_composite_grade(traits, sentiment)

    return {
        "player_id": player_id,
        "report_count": len(reports),
        "sentiment_score": sentiment,
        "traits": traits,
        "composite_grade": grade,
    }
