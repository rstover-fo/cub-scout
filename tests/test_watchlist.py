"""Tests for watch list functions."""

from src.storage.db import (
    create_watch_list,
    get_connection,
    get_watch_lists,
)


def test_create_watch_list():
    """Test creating a watch list."""
    conn = get_connection()

    try:
        list_id = create_watch_list(
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
        cur.execute("DELETE FROM scouting.watch_lists WHERE user_id = 'test-user'")
        conn.commit()
        conn.close()


def test_get_watch_lists():
    """Test retrieving user's watch lists."""
    conn = get_connection()

    try:
        create_watch_list(conn, "test-user-2", "List 1")
        create_watch_list(conn, "test-user-2", "List 2")

        lists = get_watch_lists(conn, "test-user-2")

        assert len(lists) == 2

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.watch_lists WHERE user_id = 'test-user-2'")
        conn.commit()
        conn.close()
