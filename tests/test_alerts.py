"""Tests for alert functions."""

from src.storage.db import (
    create_alert,
    get_connection,
    get_user_alerts,
)


async def test_create_alert():
    """Test creating an alert."""
    async with get_connection() as conn:
        try:
            alert_id = await create_alert(
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
            await cur.execute("DELETE FROM scouting.alerts WHERE user_id = 'test-alert-user'")
            await conn.commit()


async def test_get_user_alerts():
    """Test retrieving user's alerts."""
    async with get_connection() as conn:
        try:
            await create_alert(conn, "test-alert-user-2", "Alert 1", "grade_change")
            await create_alert(conn, "test-alert-user-2", "Alert 2", "new_report")

            alerts = await get_user_alerts(conn, "test-alert-user-2")

            assert len(alerts) == 2

        finally:
            cur = conn.cursor()
            await cur.execute("DELETE FROM scouting.alerts WHERE user_id = 'test-alert-user-2'")
            await conn.commit()
