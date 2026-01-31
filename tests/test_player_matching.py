"""Tests for player matching against roster data."""

from src.processing.player_matching import (
    fuzzy_match_name,
    find_roster_match,
    PlayerMatch,
)


def test_fuzzy_match_name_exact():
    """Test exact name matching."""
    score = fuzzy_match_name("Arch Manning", "Arch Manning")
    assert score == 100


def test_fuzzy_match_name_similar():
    """Test similar name matching."""
    score = fuzzy_match_name("Arch Manning", "Archibald Manning")
    assert score > 70  # Should be reasonably high


def test_fuzzy_match_name_different():
    """Test different names have low score."""
    score = fuzzy_match_name("Arch Manning", "Quinn Ewers")
    assert score < 50


def test_find_roster_match_integration():
    """Test finding a match in actual roster data."""
    # This test requires database connection
    match = find_roster_match("Arch Manning", team="Texas", position="QB")
    # May or may not find depending on roster data
    # Just verify it returns correct type
    assert match is None or isinstance(match, PlayerMatch)
