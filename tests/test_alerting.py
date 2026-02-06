"""Tests for alert processing."""

from src.processing.alerting import (
    check_grade_change_alert,
    check_new_report_alert,
    check_status_change_alert,
    check_trend_change_alert,
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


# Status change tests
def test_check_status_change_triggers():
    """Test status change alert fires on change."""
    result = check_status_change_alert(old_status="active", new_status="portal")
    assert result.should_fire is True
    assert "active" in result.message
    assert "portal" in result.message


def test_check_status_change_no_trigger_same():
    """Test status change doesn't fire when status unchanged."""
    result = check_status_change_alert(old_status="active", new_status="active")
    assert result.should_fire is False


def test_check_status_change_no_trigger_none():
    """Test status change doesn't fire when old is None."""
    result = check_status_change_alert(old_status=None, new_status="active")
    assert result.should_fire is False


def test_check_status_change_filtered():
    """Test status change respects status filter."""
    result = check_status_change_alert(
        old_status="active",
        new_status="injured",
        threshold={"statuses": ["portal"]},
    )
    assert result.should_fire is False


# New report tests
def test_check_new_report_triggers():
    """Test new report alert fires on new reports."""
    result = check_new_report_alert(report_count_before=3, report_count_after=5)
    assert result.should_fire is True
    assert "2 new report" in result.message


def test_check_new_report_no_trigger():
    """Test new report alert doesn't fire when count unchanged."""
    result = check_new_report_alert(report_count_before=3, report_count_after=3)
    assert result.should_fire is False


def test_check_new_report_custom_threshold():
    """Test new report alert respects min_reports threshold."""
    result = check_new_report_alert(
        report_count_before=3,
        report_count_after=4,
        threshold={"min_reports": 3},
    )
    assert result.should_fire is False


# Trend change tests
def test_check_trend_change_triggers():
    """Test trend change fires on significant change."""
    result = check_trend_change_alert(old_direction="stable", new_direction="rising")
    assert result.should_fire is True
    assert "stable" in result.message
    assert "rising" in result.message


def test_check_trend_change_falling_to_rising():
    """Test trend change fires on reversal."""
    result = check_trend_change_alert(old_direction="falling", new_direction="rising")
    assert result.should_fire is True


def test_check_trend_change_no_trigger_same():
    """Test trend change doesn't fire when direction unchanged."""
    result = check_trend_change_alert(old_direction="rising", new_direction="rising")
    assert result.should_fire is False


def test_check_trend_change_no_trigger_none():
    """Test trend change doesn't fire when old is None."""
    result = check_trend_change_alert(old_direction=None, new_direction="rising")
    assert result.should_fire is False


# Grade change edge cases
def test_check_grade_change_none_grades():
    """Test grade change handles None grades."""
    result = check_grade_change_alert(old_grade=None, new_grade=80)
    assert result.should_fire is False

    result = check_grade_change_alert(old_grade=80, new_grade=None)
    assert result.should_fire is False


def test_check_grade_change_default_threshold():
    """Test grade change uses default threshold of 5."""
    result = check_grade_change_alert(old_grade=70, new_grade=76)
    assert result.should_fire is True

    result = check_grade_change_alert(old_grade=70, new_grade=74)
    assert result.should_fire is False
