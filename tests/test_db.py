# tests/test_db.py
"""Tests for database connection."""

import pytest
from src.storage.db import get_connection, insert_report, get_unprocessed_reports


def test_get_connection_returns_connection():
    """Test that we can connect to the database."""
    conn = get_connection()
    assert conn is not None
    cur = conn.cursor()
    cur.execute("SELECT 1")
    result = cur.fetchone()
    assert result[0] == 1
    conn.close()


def test_insert_report_creates_record():
    """Test that we can insert a report."""
    conn = get_connection()

    report_id = insert_report(
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
    cur.execute("DELETE FROM scouting.reports WHERE id = %s", (report_id,))
    conn.commit()
    conn.close()
