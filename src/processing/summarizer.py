"""Claude-powered summarization for scouting content."""

import json
import logging
import os
from typing import TypedDict

import anthropic

logger = logging.getLogger(__name__)


class SummaryResult(TypedDict):
    """Result of summarization."""

    summary: str
    sentiment_score: float
    player_mentions: list[str]
    team_mentions: list[str]
    key_topics: list[str]


def get_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def extract_sentiment(text: str) -> float:
    """Extract sentiment score from text using Claude.

    Returns a score from -1 (very negative) to 1 (very positive).
    """
    client = get_client()

    response = client.messages.create(
        model="claude-3-haiku-20240307",  # Fast/cheap for simple tasks
        max_tokens=50,
        messages=[
            {
                "role": "user",
                "content": f"""Analyze the sentiment of this college football text.
Return ONLY a number between -1.0 (very negative) and 1.0 (very positive).

Text: {text[:1000]}

Sentiment score:""",
            }
        ],
    )

    try:
        score = float(response.content[0].text.strip())
        return max(-1.0, min(1.0, score))  # Clamp to valid range
    except (ValueError, IndexError):
        logger.warning(f"Failed to parse sentiment: {response.content}")
        return 0.0


def summarize_report(text: str, team_context: list[str] | None = None) -> SummaryResult:
    """Summarize a scouting report using Claude.

    Args:
        text: The raw report text.
        team_context: Optional list of teams mentioned for context.

    Returns:
        SummaryResult with summary, sentiment, and extracted entities.
    """
    client = get_client()

    context = ""
    if team_context:
        context = f"Teams mentioned: {', '.join(team_context)}\n\n"

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": f"""Analyze this college football content and extract key information.

{context}Text:
{text[:2000]}

Respond with JSON only:
{{
    "summary": "2-3 sentence summary of the key points",
    "sentiment_score": <float from -1.0 to 1.0>,
    "player_mentions": ["list", "of", "player", "names"],
    "team_mentions": ["list", "of", "team", "names"],
    "key_topics": ["recruiting", "transfer_portal", "injury", "performance", etc.]
}}""",
            }
        ],
    )

    try:
        # Extract JSON from response
        response_text = response.content[0].text.strip()
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        result = json.loads(response_text)
        return SummaryResult(
            summary=result.get("summary", ""),
            sentiment_score=float(result.get("sentiment_score", 0)),
            player_mentions=result.get("player_mentions", []),
            team_mentions=result.get("team_mentions", []),
            key_topics=result.get("key_topics", []),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse summary response: {e}")
        return SummaryResult(
            summary="",
            sentiment_score=0.0,
            player_mentions=[],
            team_mentions=[],
            key_topics=[],
        )
