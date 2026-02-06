"""Tests for watch list functions."""

from src.storage.db import (
    create_watch_list,
    get_connection,
    get_watch_lists,
)


async def test_create_watch_list():
    """Test creating a watch list."""
    async with get_connection() as conn:
        try:
            list_id = await create_watch_list(
                conn,
                user_id="test-user",
                name="Top QBs",
                description="Tracking top quarterback prospects",
            )

            assert list_id is not None
            assert list_id > 0

        finally:
            # Cleanup
            cur = conn.cursor()
            await cur.execute("DELETE FROM scouting.watch_lists WHERE user_id = 'test-user'")
            await conn.commit()


async def test_get_watch_lists():
    """Test retrieving user's watch lists."""
    async with get_connection() as conn:
        try:
            await create_watch_list(conn, "test-user-2", "List 1")
            await create_watch_list(conn, "test-user-2", "List 2")

            lists = await get_watch_lists(conn, "test-user-2")

            assert len(lists) == 2

        finally:
            cur = conn.cursor()
            await cur.execute("DELETE FROM scouting.watch_lists WHERE user_id = 'test-user-2'")
            await conn.commit()
