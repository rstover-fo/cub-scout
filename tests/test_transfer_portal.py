"""Tests for transfer portal functions."""

from datetime import date

from src.storage.db import (
    get_active_portal_players,
    get_connection,
    insert_transfer_event,
)


async def test_insert_transfer_event():
    """Test inserting a transfer event."""
    async with get_connection() as conn:
        try:
            # First create a test player
            cur = conn.cursor()
            await cur.execute(
                """
                INSERT INTO scouting.players (name, team, class_year)
                VALUES ('Test Transfer Player', 'Texas', 2025)
                RETURNING id
                """
            )
            row = await cur.fetchone()
            player_id = row[0]
            await conn.commit()

            event_id = await insert_transfer_event(
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
            await cur.execute("DELETE FROM scouting.players WHERE name = 'Test Transfer Player'")
            await conn.commit()


async def test_get_active_portal_players():
    """Test getting players currently in portal."""
    async with get_connection() as conn:
        players = await get_active_portal_players(conn)
        assert isinstance(players, list)
