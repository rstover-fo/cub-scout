# tests/test_aggregation.py
"""Tests for player aggregation."""

from src.processing.aggregation import (
    get_player_reports,
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
