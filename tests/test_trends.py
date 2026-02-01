"""Tests for trend analysis."""

from src.processing.trends import (
    calculate_trend,
    TrendDirection,
)


def test_calculate_trend_rising():
    """Test detecting rising trend."""
    grades = [60, 65, 70, 75, 80]  # Consistently increasing
    result = calculate_trend(grades)
    assert result == TrendDirection.RISING


def test_calculate_trend_falling():
    """Test detecting falling trend."""
    grades = [80, 75, 70, 65, 60]  # Consistently decreasing
    result = calculate_trend(grades)
    assert result == TrendDirection.FALLING


def test_calculate_trend_stable():
    """Test detecting stable trend."""
    grades = [70, 72, 69, 71, 70]  # Minor fluctuations
    result = calculate_trend(grades)
    assert result == TrendDirection.STABLE


def test_calculate_trend_insufficient_data():
    """Test with insufficient data points."""
    grades = [70, 75]  # Only 2 points
    result = calculate_trend(grades)
    assert result == TrendDirection.UNKNOWN
