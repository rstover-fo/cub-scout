"""Tests for alert functions."""

from src.storage.db import (
    get_connection,
    create_alert,
    get_user_alerts,
    fire_alert,
    get_unread_alerts,
)


def test_create_alert():
    """Test creating an alert."""
    conn = get_connection()

    try:
        alert_id = create_alert(
            conn,
            user_id="test-alert-user",
            name="Arch Manning Grade Alert",
            alert_type="grade_change",
            player_id=None,  # Will use player_id if exists
            threshold={"min_change": 5},
        )

        assert alert_id is not None
        assert alert_id > 0

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.alerts WHERE user_id = 'test-alert-user'")
        conn.commit()
        conn.close()


def test_get_user_alerts():
    """Test retrieving user's alerts."""
    conn = get_connection()

    try:
        create_alert(conn, "test-alert-user-2", "Alert 1", "grade_change")
        create_alert(conn, "test-alert-user-2", "Alert 2", "new_report")

        alerts = get_user_alerts(conn, "test-alert-user-2")

        assert len(alerts) == 2

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.alerts WHERE user_id = 'test-alert-user-2'")
        conn.commit()
        conn.close()
