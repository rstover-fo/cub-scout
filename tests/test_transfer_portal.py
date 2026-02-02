"""Tests for transfer portal functions."""

from datetime import date

from src.storage.db import (
    get_connection,
    insert_transfer_event,
    get_active_portal_players,
)


def test_insert_transfer_event():
    """Test inserting a transfer event."""
    conn = get_connection()

    try:
        # First create a test player
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scouting.players (name, team, class_year)
            VALUES ('Test Transfer Player', 'Texas', 2025)
            RETURNING id
            """
        )
        player_id = cur.fetchone()[0]
        conn.commit()

        event_id = insert_transfer_event(
            conn,
            player_id=player_id,
            event_type="entered",
            from_team="Texas",
            event_date=date.today(),
        )

        assert event_id is not None
        assert event_id > 0

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.players WHERE name = 'Test Transfer Player'")
        conn.commit()
        conn.close()


def test_get_active_portal_players():
    """Test getting players currently in portal."""
    conn = get_connection()

    try:
        players = get_active_portal_players(conn)
        assert isinstance(players, list)

    finally:
        conn.close()
