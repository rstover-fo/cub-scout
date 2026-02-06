"""Tests for player entity extraction."""

import pytest

from src.processing.entity_extraction import (
    extract_player_mentions,
    extract_player_mentions_claude,
    normalize_name,
)


def test_normalize_name():
    """Test name normalization."""
    assert normalize_name("Arch Manning") == "arch manning"
    assert normalize_name("  John Smith Jr. ") == "john smith jr"
    assert normalize_name("D'Andre Swift") == "dandre swift"


def test_extract_player_mentions_finds_names():
    """Test that player names are extracted from text."""
    text = """
    Texas QB Arch Manning continues to impress in spring practice.
    Wide receiver Isaiah Bond made several big catches.
    The defense, led by linebacker Anthony Hill, looks strong.
    """
    players = extract_player_mentions(text)

    assert len(players) >= 2  # Should find multiple names
    assert any("manning" in p.lower() for p in players)
    assert any("bond" in p.lower() for p in players)


def test_extract_player_mentions_handles_positions():
    """Test extraction handles position prefixes."""
    text = "QB Quinn Ewers and RB Jaydon Blue both had great games."
    players = extract_player_mentions(text)

    assert any("ewers" in p.lower() for p in players)
    assert any("blue" in p.lower() for p in players)


@pytest.mark.asyncio
async def test_extract_player_mentions_claude(mock_anthropic):
    """Test Claude-based player extraction returns structured results."""
    text = "Texas QB Arch Manning had a great spring practice."
    results = await extract_player_mentions_claude(text)

    assert len(results) >= 1
    assert results[0]["name"] == "Arch Manning"
    assert results[0]["position"] == "QB"
    assert results[0]["team"] == "Texas"
    assert results[0]["context"] == "starter"
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_extract_player_mentions_claude_empty_text(mock_anthropic):
    """Test Claude extraction handles empty results."""
    # Override the mock to return empty array for this call
    from tests.conftest import _make_anthropic_response

    mock_anthropic.messages.create.side_effect = None
    mock_anthropic.messages.create.return_value = _make_anthropic_response("[]")

    results = await extract_player_mentions_claude("")
    assert results == []
