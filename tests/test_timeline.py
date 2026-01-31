# tests/test_timeline.py
"""Tests for player timeline functions."""

from datetime import date

from src.storage.db import (
    get_connection,
    insert_timeline_snapshot,
    get_player_timeline,
)


def test_insert_timeline_snapshot():
    """Test inserting a timeline snapshot."""
    conn = get_connection()
    cur = conn.cursor()

    # Create temp player
    cur.execute(
        """
        INSERT INTO scouting.players (name, team, class_year)
        VALUES ('Timeline Test', 'Test Team', 2024)
        RETURNING id
        """
    )
    player_id = cur.fetchone()[0]
    conn.commit()

    try:
        snapshot_id = insert_timeline_snapshot(
            conn,
            player_id=player_id,
            snapshot_date=date.today(),
            status="active",
            sentiment_score=0.5,
            grade_at_time=75,
            traits_at_time={"arm_strength": 8},
            key_narratives=["Strong arm", "Good leader"],
            sources_count=5,
        )

        assert snapshot_id is not None
        assert snapshot_id > 0

    finally:
        # Cleanup
        cur.execute("DELETE FROM scouting.player_timeline WHERE player_id = %s", (player_id,))
        cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
        conn.commit()
        conn.close()


def test_get_player_timeline():
    """Test retrieving player timeline."""
    conn = get_connection()
    cur = conn.cursor()

    # Create temp player
    cur.execute(
        """
        INSERT INTO scouting.players (name, team, class_year)
        VALUES ('Timeline Test 2', 'Test Team', 2024)
        RETURNING id
        """
    )
    player_id = cur.fetchone()[0]
    conn.commit()

    try:
        # Insert two snapshots
        insert_timeline_snapshot(conn, player_id, date(2024, 1, 1), "active", 0.3, 70)
        insert_timeline_snapshot(conn, player_id, date(2024, 2, 1), "active", 0.5, 75)

        timeline = get_player_timeline(conn, player_id)

        assert len(timeline) == 2
        # Should be ordered newest first
        assert timeline[0]["grade_at_time"] == 75
        assert timeline[1]["grade_at_time"] == 70

    finally:
        cur.execute("DELETE FROM scouting.player_timeline WHERE player_id = %s", (player_id,))
        cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
        conn.commit()
        conn.close()
