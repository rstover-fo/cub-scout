# tests/test_timeline.py
"""Tests for player timeline functions."""

from datetime import date

from src.storage.db import (
    get_connection,
    get_player_timeline,
    insert_timeline_snapshot,
)


async def test_insert_timeline_snapshot():
    """Test inserting a timeline snapshot."""
    async with get_connection() as conn:
        cur = conn.cursor()

        # Create temp player
        await cur.execute(
            """
            INSERT INTO scouting.players (name, team, class_year)
            VALUES ('Timeline Test', 'Test Team', 2024)
            RETURNING id
            """
        )
        row = await cur.fetchone()
        player_id = row[0]
        await conn.commit()

        try:
            snapshot_id = await insert_timeline_snapshot(
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
            await cur.execute(
                "DELETE FROM scouting.player_timeline WHERE player_id = %s",
                (player_id,),
            )
            await cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
            await conn.commit()


async def test_get_player_timeline():
    """Test retrieving player timeline."""
    async with get_connection() as conn:
        cur = conn.cursor()

        # Create temp player
        await cur.execute(
            """
            INSERT INTO scouting.players (name, team, class_year)
            VALUES ('Timeline Test 2', 'Test Team', 2024)
            RETURNING id
            """
        )
        row = await cur.fetchone()
        player_id = row[0]
        await conn.commit()

        try:
            # Insert two snapshots
            await insert_timeline_snapshot(conn, player_id, date(2024, 1, 1), "active", 0.3, 70)
            await insert_timeline_snapshot(conn, player_id, date(2024, 2, 1), "active", 0.5, 75)

            timeline = await get_player_timeline(conn, player_id)

            assert len(timeline) == 2
            # Should be ordered newest first
            assert timeline[0]["grade_at_time"] == 75
            assert timeline[1]["grade_at_time"] == 70

        finally:
            await cur.execute(
                "DELETE FROM scouting.player_timeline WHERE player_id = %s",
                (player_id,),
            )
            await cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
            await conn.commit()
