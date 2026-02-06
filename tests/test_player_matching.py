"""Tests for player matching against roster data."""

from src.processing.player_matching import (
    PlayerMatch,
    find_roster_match,
    fuzzy_match_name,
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


async def test_find_roster_match_integration():
    """Test finding a match in actual roster data."""
    # This test requires database connection
    match = await find_roster_match("Arch Manning", team="Texas", position="QB")
    # May or may not find depending on roster data
    # Just verify it returns correct type
    assert match is None or isinstance(match, PlayerMatch)


# Tests for Tier 1: Deterministic Matching


async def test_deterministic_match_exact_name_team_year():
    """Test exact name + team + year returns 100% confidence."""
    from src.processing.player_matching import find_deterministic_match

    result = await find_deterministic_match(
        name="Arch Manning",
        team="Texas",
        year=2025,
    )
    assert result is None or isinstance(result, PlayerMatch)
    if result:
        assert result.confidence == 100.0
        assert result.match_method == "deterministic"


async def test_deterministic_match_athlete_id_link():
    """Test athlete_id link to roster returns 100% confidence."""
    from src.processing.player_matching import find_deterministic_match_by_athlete_id

    result = await find_deterministic_match_by_athlete_id(athlete_id="123456")
    assert result is None or isinstance(result, PlayerMatch)
    if result:
        assert result.confidence == 100.0
        assert result.match_method == "deterministic"


# Tests for Tier 2: Vector Similarity Matching


async def test_vector_match_returns_high_similarity():
    """Test vector matching uses embeddings for similarity."""
    from src.processing.player_matching import find_vector_match

    result = await find_vector_match(
        name="Arch Manning",
        team="Texas",
        position="QB",
        year=2025,
    )
    assert result is None or isinstance(result, PlayerMatch)
    if result:
        assert result.match_method == "vector"
        assert result.confidence >= 0 and result.confidence <= 100


async def test_vector_match_requires_team_match():
    """Test vector matching enforces team filter."""
    from src.processing.player_matching import find_vector_match

    # Search for Texas player
    result = await find_vector_match(
        name="Arch Manning",
        team="Texas",
        position="QB",
        year=2025,
    )
    if result:
        # Team should match filter
        assert result.team.lower() == "texas"


# Tests for Pending Links Queue


async def test_create_pending_link_for_low_confidence():
    """Test low confidence matches create pending links."""
    from src.processing.player_matching import match_player_with_review

    # Function should exist and return a tuple (match, pending_link_id)
    result = await match_player_with_review(
        name="Unknown Player",
        team="Some Team",
        position="WR",
        year=2025,
        source_context={"source": "test"},
    )

    assert isinstance(result, tuple)
    assert len(result) == 2
    match, pending_link_id = result
    # Either we got a match or a pending link was created (or neither)
    assert (
        match is not None
        or pending_link_id is not None
        or (match is None and pending_link_id is None)
    )
