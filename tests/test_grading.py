"""Tests for src/processing/grading.py."""

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from src.processing.grading import (
    get_players_needing_update,
    run_grading_pipeline,
    update_player_grade,
)

MOCK_AGGREGATION = {
    "player_id": 1,
    "report_count": 5,
    "sentiment_score": 0.72,
    "traits": {"arm_strength": 8, "accuracy": 7, "mobility": 6},
    "composite_grade": 78,
}

MOCK_PLAYERS_ROWS = [
    (1, "Arch Manning", "Texas", 2026),
    (2, "Carson Beck", "Miami", 2025),
]

COLUMN_DESCRIPTORS = [("id",), ("name",), ("team",), ("class_year",)]


def _make_mock_conn(cursor_description=None, fetchall_return=None):
    """Build a MagicMock connection with an AsyncMock cursor.

    conn.cursor() is sync (returns cursor directly), but cursor.execute()
    and cursor.fetchall() are async in psycopg v3.
    """
    mock_cursor = AsyncMock()
    if cursor_description is not None:
        mock_cursor.description = cursor_description
    if fetchall_return is not None:
        mock_cursor.fetchall.return_value = fetchall_return

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    # commit is async in psycopg v3
    mock_conn.commit = AsyncMock()
    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# get_players_needing_update
# ---------------------------------------------------------------------------


async def test_get_players_needing_update_returns_players():
    """Returns list of player dicts with correct keys from DB rows."""
    mock_conn, _ = _make_mock_conn(
        cursor_description=COLUMN_DESCRIPTORS,
        fetchall_return=MOCK_PLAYERS_ROWS,
    )

    @asynccontextmanager
    async def conn_ctx():
        yield mock_conn

    with patch("src.processing.grading.get_connection", side_effect=conn_ctx):
        result = await get_players_needing_update()

    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "Arch Manning", "team": "Texas", "class_year": 2026}
    assert result[1] == {"id": 2, "name": "Carson Beck", "team": "Miami", "class_year": 2025}


async def test_get_players_needing_update_empty():
    """Returns empty list when no players need updating."""
    mock_conn, _ = _make_mock_conn(
        cursor_description=COLUMN_DESCRIPTORS,
        fetchall_return=[],
    )

    @asynccontextmanager
    async def conn_ctx():
        yield mock_conn

    with patch("src.processing.grading.get_connection", side_effect=conn_ctx):
        result = await get_players_needing_update()

    assert result == []


async def test_get_players_needing_update_respects_limit():
    """Passes the limit parameter into the SQL query."""
    mock_conn, mock_cursor = _make_mock_conn(
        cursor_description=COLUMN_DESCRIPTORS,
        fetchall_return=[],
    )

    @asynccontextmanager
    async def conn_ctx():
        yield mock_conn

    with patch("src.processing.grading.get_connection", side_effect=conn_ctx):
        await get_players_needing_update(limit=10)

    mock_cursor.execute.assert_called_once()
    sql_args = mock_cursor.execute.call_args[0]
    assert sql_args[1] == (10,)


# ---------------------------------------------------------------------------
# update_player_grade
# ---------------------------------------------------------------------------


async def test_update_player_grade_updates_db():
    """Executes UPDATE SQL and commits the transaction."""
    mock_conn, mock_cursor = _make_mock_conn()

    @asynccontextmanager
    async def conn_ctx():
        yield mock_conn

    with (
        patch("src.processing.grading.get_connection", side_effect=conn_ctx),
        patch(
            "src.processing.grading.aggregate_player_profile",
            new_callable=AsyncMock,
            return_value=MOCK_AGGREGATION,
        ),
        patch("src.processing.grading.insert_timeline_snapshot", new_callable=AsyncMock),
    ):
        await update_player_grade(player_id=1)

    # Verify UPDATE was executed with correct params
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args[0]
    assert "UPDATE scouting.players" in sql
    assert params == (78, {"arm_strength": 8, "accuracy": 7, "mobility": 6}, 1)

    # Verify commit was called
    mock_conn.commit.assert_called_once()


async def test_update_player_grade_creates_timeline():
    """Calls insert_timeline_snapshot with correct arguments."""
    mock_conn, _ = _make_mock_conn()

    @asynccontextmanager
    async def conn_ctx():
        yield mock_conn

    mock_timeline = AsyncMock()

    with (
        patch("src.processing.grading.get_connection", side_effect=conn_ctx),
        patch(
            "src.processing.grading.aggregate_player_profile",
            new_callable=AsyncMock,
            return_value=MOCK_AGGREGATION,
        ),
        patch("src.processing.grading.insert_timeline_snapshot", mock_timeline),
    ):
        await update_player_grade(player_id=1)

    mock_timeline.assert_called_once_with(
        mock_conn,
        player_id=1,
        snapshot_date=date.today(),
        sentiment_score=0.72,
        grade_at_time=78,
        traits_at_time={"arm_strength": 8, "accuracy": 7, "mobility": 6},
        sources_count=5,
    )


async def test_update_player_grade_returns_aggregation():
    """Returns the aggregation result dict from aggregate_player_profile."""
    mock_conn, _ = _make_mock_conn()

    @asynccontextmanager
    async def conn_ctx():
        yield mock_conn

    with (
        patch("src.processing.grading.get_connection", side_effect=conn_ctx),
        patch(
            "src.processing.grading.aggregate_player_profile",
            new_callable=AsyncMock,
            return_value=MOCK_AGGREGATION,
        ),
        patch("src.processing.grading.insert_timeline_snapshot", new_callable=AsyncMock),
    ):
        result = await update_player_grade(player_id=1)

    assert result == MOCK_AGGREGATION
    assert result["composite_grade"] == 78
    assert result["report_count"] == 5


# ---------------------------------------------------------------------------
# run_grading_pipeline
# ---------------------------------------------------------------------------


async def test_run_grading_pipeline_processes_all():
    """Processes all players returned by get_players_needing_update."""
    mock_players = [
        {"id": 1, "name": "Player A", "team": "Team A", "class_year": 2026},
        {"id": 2, "name": "Player B", "team": "Team B", "class_year": 2025},
        {"id": 3, "name": "Player C", "team": "Team C", "class_year": 2026},
    ]

    mock_update = AsyncMock(return_value=MOCK_AGGREGATION)

    with (
        patch(
            "src.processing.grading.get_players_needing_update",
            new_callable=AsyncMock,
            return_value=mock_players,
        ),
        patch("src.processing.grading.update_player_grade", mock_update),
    ):
        result = await run_grading_pipeline(batch_size=25)

    assert result == {"players_found": 3, "players_updated": 3, "errors": 0}
    assert mock_update.call_count == 3
    mock_update.assert_any_call(1)
    mock_update.assert_any_call(2)
    mock_update.assert_any_call(3)


async def test_run_grading_pipeline_handles_errors():
    """Continues processing other players when one raises an exception."""
    mock_players = [
        {"id": 1, "name": "Player A", "team": "Team A", "class_year": 2026},
        {"id": 2, "name": "Player B", "team": "Team B", "class_year": 2025},
        {"id": 3, "name": "Player C", "team": "Team C", "class_year": 2026},
    ]

    async def update_side_effect(player_id):
        if player_id == 2:
            raise RuntimeError("DB connection lost")
        return MOCK_AGGREGATION

    with (
        patch(
            "src.processing.grading.get_players_needing_update",
            new_callable=AsyncMock,
            return_value=mock_players,
        ),
        patch(
            "src.processing.grading.update_player_grade",
            new_callable=AsyncMock,
            side_effect=update_side_effect,
        ),
    ):
        result = await run_grading_pipeline()

    assert result["players_found"] == 3
    assert result["players_updated"] == 2
    assert result["errors"] == 1


async def test_run_grading_pipeline_no_players():
    """Returns zeroed stats when no players need updating."""
    with patch(
        "src.processing.grading.get_players_needing_update",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await run_grading_pipeline()

    assert result == {"players_found": 0, "players_updated": 0, "errors": 0}
