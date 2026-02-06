# tests/test_db.py
"""Tests for database connection."""

from src.storage.db import get_connection, insert_report


async def test_get_connection_returns_connection():
    """Test that we can connect to the database."""
    async with get_connection() as conn:
        cur = conn.cursor()
        await cur.execute("SELECT 1")
        result = await cur.fetchone()
        assert result[0] == 1


async def test_insert_report_creates_record():
    """Test that we can insert a report."""
    async with get_connection() as conn:
        report_id = await insert_report(
            conn,
            source_url="https://reddit.com/r/CFB/test123",
            source_name="reddit",
            content_type="forum",
            raw_text="Test content about Texas football",
            team_ids=["Texas"],
        )

        assert report_id is not None
        assert report_id > 0

        # Clean up
        cur = conn.cursor()
        await cur.execute("DELETE FROM scouting.reports WHERE id = %s", (report_id,))
        await conn.commit()
