"""Tests for alert processing."""

from src.processing.alerting import (
    check_grade_change_alert,
    AlertCheckResult,
)


def test_check_grade_change_alert_triggers():
    """Test that grade change alert triggers when threshold exceeded."""
    result = check_grade_change_alert(
        old_grade=75,
        new_grade=82,
        threshold={"min_change": 5},
    )

    assert result.should_fire is True
    assert result.message is not None
    assert "increased" in result.message.lower()


def test_check_grade_change_alert_no_trigger():
    """Test that grade change alert doesn't trigger below threshold."""
    result = check_grade_change_alert(
        old_grade=75,
        new_grade=77,
        threshold={"min_change": 5},
    )

    assert result.should_fire is False


def test_check_grade_change_alert_decrease():
    """Test that grade decrease also triggers."""
    result = check_grade_change_alert(
        old_grade=80,
        new_grade=72,
        threshold={"min_change": 5},
    )

    assert result.should_fire is True
    assert "decreased" in result.message.lower()
