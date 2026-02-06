# tests/test_aggregation.py
"""Tests for player aggregation."""

import pytest

from src.processing.aggregation import (
    calculate_composite_grade,
    calculate_sentiment_average,
    extract_traits_from_reports,
)


def test_calculate_sentiment_average_empty():
    """Test sentiment average with empty list."""
    result = calculate_sentiment_average([])
    assert result is None


def test_calculate_sentiment_average_values():
    """Test sentiment average calculation."""
    reports = [
        {"sentiment_score": 0.5},
        {"sentiment_score": 0.3},
        {"sentiment_score": -0.2},
    ]
    result = calculate_sentiment_average(reports)
    assert result == 0.2  # (0.5 + 0.3 + -0.2) / 3 = 0.2


def test_calculate_sentiment_average_skips_none():
    """Test that None values are skipped."""
    reports = [
        {"sentiment_score": 0.6},
        {"sentiment_score": None},
        {"sentiment_score": 0.4},
    ]
    result = calculate_sentiment_average(reports)
    assert result == 0.5  # (0.6 + 0.4) / 2


@pytest.mark.asyncio
async def test_extract_traits_from_reports_returns_dict(mock_anthropic):
    """Test trait extraction returns dict with ratings."""
    reports = [
        {"summary": "Strong arm, great accuracy. Natural leader on the field."},
        {"summary": "Mobile QB with excellent decision making under pressure."},
    ]
    traits = await extract_traits_from_reports(reports)

    assert isinstance(traits, dict)
    assert "arm_strength" in traits
    assert traits["arm_strength"] == 8
    assert traits["decision_making"] == 9
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_extract_traits_from_reports_empty():
    """Test trait extraction with no reports returns empty dict."""
    traits = await extract_traits_from_reports([])
    assert traits == {}


def test_calculate_composite_grade_from_traits():
    """Test composite grade calculation."""
    traits = {"arm_strength": 8, "accuracy": 7, "mobility": 6}
    grade = calculate_composite_grade(traits, sentiment=0.5)

    # avg = (8+7+6)/3 = 7.0, base = 70, sentiment bonus = 2
    assert grade == 72


def test_calculate_composite_grade_no_traits():
    """Test composite grade with empty traits."""
    assert calculate_composite_grade({}, None) is None
