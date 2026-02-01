"""Tests for player comparison engine."""

from src.processing.comparison import (
    compare_players,
    PlayerComparison,
    build_radar_data,
)


def test_build_radar_data():
    """Test building radar chart data."""
    traits = {
        "arm_strength": 8,
        "accuracy": 7,
        "mobility": 6,
        "decision_making": 9,
    }
    result = build_radar_data(traits)

    assert len(result) == 4
    assert result[0]["trait"] == "arm_strength"
    assert result[0]["value"] == 8


def test_build_radar_data_empty():
    """Test radar data with empty traits."""
    result = build_radar_data({})
    assert result == []


def test_build_radar_data_normalizes():
    """Test that values are normalized to 0-10 scale."""
    traits = {"speed": 95}  # If somehow > 10
    result = build_radar_data(traits, max_value=100)
    assert result[0]["value"] == 9.5  # Normalized to 10-scale
