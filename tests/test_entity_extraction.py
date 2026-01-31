"""Tests for player entity extraction."""

import pytest

from src.processing.entity_extraction import extract_player_mentions, normalize_name


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
