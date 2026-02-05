"""Tests for draft board functionality."""

from src.processing.draft import (
    DraftProjection,
    calculate_draft_score,
)


def test_calculate_draft_score_first_round():
    """Test draft score calculation for elite player."""
    score = calculate_draft_score(
        composite_grade=92,
        pff_grade=90.5,
        trend_slope=1.2,
    )
    assert score > 80


def test_calculate_draft_score_no_pff():
    """Test draft score without PFF grade."""
    score = calculate_draft_score(
        composite_grade=75,
        pff_grade=None,
        trend_slope=0.5,
    )
    assert 50 < score < 80


def test_draft_projection_enum():
    """Test DraftProjection values."""
    assert DraftProjection.FIRST_ROUND.value == "1st Round"
    assert DraftProjection.UDFA.value == "UDFA"
