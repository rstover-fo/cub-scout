"""Tests for scouting player upsert."""

import pytest

from src.storage.db import get_connection, upsert_scouting_player, get_scouting_player


def test_upsert_scouting_player_creates_new():
    """Test creating a new scouting player."""
    conn = get_connection()

    player_id = upsert_scouting_player(
        conn,
        name="Test Player",
        team="Test Team",
        position="QB",
        class_year=2024,
        current_status="active",
        roster_player_id=12345,
    )

    assert player_id is not None
    assert player_id > 0

    # Clean up
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
    conn.commit()
    conn.close()


def test_upsert_scouting_player_updates_existing():
    """Test updating an existing scouting player."""
    conn = get_connection()

    # Create initial
    player_id1 = upsert_scouting_player(
        conn,
        name="Update Test",
        team="Team A",
        position="RB",
        class_year=2024,
        current_status="active",
    )

    # Upsert with same key should update
    player_id2 = upsert_scouting_player(
        conn,
        name="Update Test",
        team="Team A",
        position="RB",
        class_year=2024,
        current_status="transfer",  # Changed status
        composite_grade=85,
    )

    assert player_id1 == player_id2  # Same record

    # Verify update
    player = get_scouting_player(conn, player_id1)
    assert player["current_status"] == "transfer"
    assert player["composite_grade"] == 85

    # Clean up
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id1,))
    conn.commit()
    conn.close()
