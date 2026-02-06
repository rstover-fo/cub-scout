"""Pytest configuration for cfb-scout tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


@pytest.fixture
async def mock_db_connection():
    """Provide an async database connection for tests."""
    from src.storage.db import get_connection

    async with get_connection() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Anthropic mock helpers
# ---------------------------------------------------------------------------


def _make_anthropic_response(text: str) -> MagicMock:
    """Build a mock anthropic.types.Message with a single TextBlock."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


# Default mock responses keyed by prompt substring for routing
_ANTHROPIC_RESPONSES: dict[str, str] = {
    # entity_extraction: extract_player_mentions_claude
    "Extract all college football player names": json.dumps(
        [
            {
                "name": "Arch Manning",
                "position": "QB",
                "team": "Texas",
                "context": "starter",
            }
        ]
    ),
    # summarizer: extract_sentiment
    "Analyze the sentiment": "0.65",
    # summarizer: summarize_report
    "Analyze this college football content": json.dumps(
        {
            "summary": "Texas continues spring practice with strong performances.",
            "sentiment_score": 0.7,
            "player_mentions": ["Arch Manning"],
            "team_mentions": ["Texas"],
            "key_topics": ["performance"],
        }
    ),
    # aggregation: extract_traits_from_reports
    "Analyze these scouting reports and extract player traits": json.dumps(
        {
            "arm_strength": 8,
            "accuracy": 7,
            "mobility": 6,
            "decision_making": 9,
        }
    ),
}


def _route_anthropic_response(**kwargs) -> MagicMock:
    """Return a mock response based on the prompt content."""
    messages = kwargs.get("messages", [])
    prompt = messages[0]["content"] if messages else ""
    for key, text in _ANTHROPIC_RESPONSES.items():
        if key in prompt:
            return _make_anthropic_response(text)
    # Fallback
    return _make_anthropic_response("{}")


@pytest.fixture(autouse=True)
def mock_anthropic():
    """Auto-mock all Anthropic API calls so tests never hit the real API.

    Patches get_anthropic_client at every call site in the processing package.
    The mock routes responses based on prompt content via AsyncMock.
    """
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=_route_anthropic_response)

    targets = [
        "src.processing.entity_extraction.get_anthropic_client",
        "src.processing.summarizer.get_anthropic_client",
        "src.processing.aggregation.get_anthropic_client",
    ]
    patches = [patch(target, return_value=mock_client) for target in targets]

    for p in patches:
        p.start()
    yield mock_client
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# OpenAI mock helpers
# ---------------------------------------------------------------------------


def _make_openai_embedding_response(dims: int = 1536) -> MagicMock:
    """Build a mock openai embedding response."""
    embedding_obj = MagicMock()
    embedding_obj.embedding = [0.01] * dims
    response = MagicMock()
    response.data = [embedding_obj]
    return response


@pytest.fixture(autouse=True)
def mock_openai():
    """Auto-mock all OpenAI API calls so tests never hit the real API.

    Patches the lazy _get_client in embeddings.py.
    """
    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(return_value=_make_openai_embedding_response())

    with patch("src.processing.embeddings._get_client", return_value=mock_client):
        yield mock_client
