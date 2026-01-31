"""Player entity extraction from scouting content."""

import logging
import os
import re
from typing import TypedDict

import anthropic

logger = logging.getLogger(__name__)

# Common CFB position abbreviations
POSITIONS = [
    "QB", "RB", "WR", "TE", "OL", "OT", "OG", "C",
    "DL", "DT", "DE", "EDGE", "LB", "ILB", "OLB", "MLB",
    "DB", "CB", "S", "FS", "SS", "K", "P", "LS", "ATH",
]

# Regex to find "Position Name" patterns
POSITION_NAME_PATTERN = re.compile(
    rf'\b({"|".join(POSITIONS)})\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
    re.IGNORECASE
)

# Regex to find capitalized names (2-4 words)
NAME_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
)


def normalize_name(name: str) -> str:
    """Normalize a name for matching.

    - Lowercase
    - Remove extra whitespace
    - Remove apostrophes and periods
    """
    name = name.lower().strip()
    name = re.sub(r"['\".]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def extract_player_mentions(text: str) -> list[str]:
    """Extract potential player names from text using regex patterns.

    This is a fast heuristic extraction. For higher accuracy,
    use extract_player_mentions_claude().
    """
    players = set()

    # Find "Position Name" patterns
    for match in POSITION_NAME_PATTERN.finditer(text):
        name = match.group(2).strip()
        if len(name.split()) >= 2:  # At least first + last
            players.add(name)

    # Find standalone capitalized names that look like player names
    # Filter out common non-names
    SKIP_WORDS = {
        "The", "This", "That", "When", "Where", "What", "Which", "While",
        "After", "Before", "During", "With", "From", "Into", "About",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
        "Spring", "Summer", "Fall", "Winter", "Practice", "Game",
        "Texas", "Ohio State", "Alabama", "Georgia", "Michigan",  # Team names
    }

    for match in NAME_PATTERN.finditer(text):
        name = match.group(1).strip()
        words = name.split()

        # Skip if first word is a common non-name
        if words[0] in SKIP_WORDS:
            continue

        # Must be 2-4 words, not all caps
        if 2 <= len(words) <= 4 and not name.isupper():
            players.add(name)

    return list(players)


class PlayerMention(TypedDict):
    """Structured player mention from Claude extraction."""

    name: str
    position: str | None
    team: str | None
    context: str  # "starter", "recruit", "transfer", etc.


def extract_player_mentions_claude(text: str) -> list[PlayerMention]:
    """Extract player mentions using Claude for higher accuracy.

    Use this for processing important content where accuracy matters.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": f"""Extract all college football player names mentioned in this text.

Text:
{text[:3000]}

Return a JSON array of objects with these fields:
- name: The player's full name
- position: Their position if mentioned (QB, RB, WR, etc.) or null
- team: Their team if mentioned or null
- context: One of "starter", "recruit", "transfer", "draft_prospect", "general"

Return only the JSON array, no other text. If no players mentioned, return [].

Example:
[{{"name": "Arch Manning", "position": "QB", "team": "Texas", "context": "starter"}}]"""
            }
        ],
    )

    try:
        import json
        response_text = response.content[0].text.strip()

        # Handle markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        result = json.loads(response_text)
        return [PlayerMention(**p) for p in result]
    except Exception as e:
        logger.warning(f"Failed to parse Claude response: {e}")
        return []
