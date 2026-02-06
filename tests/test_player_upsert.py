"""Tests for scouting player upsert."""

from src.storage.db import get_connection, get_scouting_player, upsert_scouting_player


async def test_upsert_scouting_player_creates_new():
    """Test creating a new scouting player."""
    async with get_connection() as conn:
        player_id = await upsert_scouting_player(
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
        await cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
        await conn.commit()


async def test_upsert_scouting_player_updates_existing():
    """Test updating an existing scouting player."""
    async with get_connection() as conn:
        # Create initial
        player_id1 = await upsert_scouting_player(
            conn,
            name="Update Test",
            team="Team A",
            position="RB",
            class_year=2024,
            current_status="active",
        )

        # Upsert with same key should update
        player_id2 = await upsert_scouting_player(
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
        player = await get_scouting_player(conn, player_id1)
        assert player["current_status"] == "transfer"
        assert player["composite_grade"] == 85

        # Clean up
        cur = conn.cursor()
        await cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id1,))
        await conn.commit()
