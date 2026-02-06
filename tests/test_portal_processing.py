"""Tests for transfer portal processing."""

from src.processing.transfer_portal import (
    extract_portal_mentions,
    predict_destination,
)


def test_extract_portal_mentions_finds_keywords():
    """Test that portal-related text is detected."""
    text = "Breaking: Arch Manning has entered the transfer portal from Texas"
    result = extract_portal_mentions(text)

    assert result["is_portal_related"] is True
    assert "entered" in result["event_type"]


def test_extract_portal_mentions_no_match():
    """Test text without portal mentions."""
    text = "Arch Manning had a great game against Alabama"
    result = extract_portal_mentions(text)

    assert result["is_portal_related"] is False


async def test_predict_destination_returns_list():
    """Test destination prediction returns ranked list."""
    # Mock input - player with certain traits/history
    predictions = await predict_destination(
        position="QB",
        from_team="Texas",
        composite_grade=85,
        class_year=2025,
    )

    assert isinstance(predictions, list)
