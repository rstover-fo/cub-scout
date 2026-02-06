"""Tests for PFF grade pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.pff import PFFPlayerGrade
from src.processing.pff_pipeline import fetch_and_store_pff_grade, run_pff_pipeline


def _make_pff_grade(**overrides) -> PFFPlayerGrade:
    """Build a PFFPlayerGrade with sensible defaults."""
    defaults = {
        "player_id": "99999",
        "name": "Arch Manning",
        "position": "QB",
        "team": "Texas",
        "overall_grade": 85.5,
        "passing_grade": 87.2,
        "rushing_grade": 72.1,
        "snaps": 450,
        "season": 2025,
    }
    defaults.update(overrides)
    return PFFPlayerGrade(**defaults)


SAMPLE_PLAYER = {"id": 1, "name": "Arch Manning", "team": "Texas", "position": "QB"}


# --- fetch_and_store_pff_grade tests ---


async def test_fetch_and_store_pff_grade_found():
    """When PFF returns a grade, upsert is called and True is returned."""
    grade = _make_pff_grade()
    mock_client = MagicMock()
    mock_client.get_player_by_name = AsyncMock(return_value=grade)

    mock_conn = MagicMock()

    with patch(
        "src.processing.pff_pipeline.upsert_pff_grade",
        new_callable=AsyncMock,
        return_value=42,
    ) as mock_upsert:
        result = await fetch_and_store_pff_grade(mock_client, mock_conn, SAMPLE_PLAYER)

    assert result is True
    mock_client.get_player_by_name.assert_awaited_once_with("Arch Manning", team="Texas")
    mock_upsert.assert_awaited_once()

    call_kwargs = mock_upsert.call_args[1]
    assert call_kwargs["player_id"] == 1
    assert call_kwargs["pff_player_id"] == "99999"
    assert call_kwargs["overall_grade"] == 85.5
    assert call_kwargs["snaps"] == 450
    assert call_kwargs["season"] == 2025


async def test_fetch_and_store_pff_grade_not_found():
    """When PFF returns None, upsert is not called and False is returned."""
    mock_client = MagicMock()
    mock_client.get_player_by_name = AsyncMock(return_value=None)

    mock_conn = MagicMock()

    with patch(
        "src.processing.pff_pipeline.upsert_pff_grade",
        new_callable=AsyncMock,
    ) as mock_upsert:
        result = await fetch_and_store_pff_grade(mock_client, mock_conn, SAMPLE_PLAYER)

    assert result is False
    mock_upsert.assert_not_awaited()


async def test_fetch_and_store_pff_grade_error():
    """When PFF client raises, error is logged and None is returned."""
    mock_client = MagicMock()
    mock_client.get_player_by_name = AsyncMock(side_effect=RuntimeError("API timeout"))

    mock_conn = MagicMock()

    with patch("src.processing.pff_pipeline.upsert_pff_grade", new_callable=AsyncMock):
        result = await fetch_and_store_pff_grade(mock_client, mock_conn, SAMPLE_PLAYER)

    assert result is None


# --- run_pff_pipeline tests ---


async def test_run_pff_pipeline_no_api_key(monkeypatch):
    """Without PFF_API_KEY, pipeline returns zeroed stats immediately."""
    monkeypatch.delenv("PFF_API_KEY", raising=False)

    stats = await run_pff_pipeline()

    assert stats == {"players_checked": 0, "grades_stored": 0, "errors": 0}


async def test_run_pff_pipeline_processes_batch(monkeypatch):
    """Pipeline fetches grades for players returned by the DB query."""
    monkeypatch.setenv("PFF_API_KEY", "test-key")

    players_from_db = [
        {"id": 1, "name": "Arch Manning", "team": "Texas", "position": "QB"},
        {"id": 2, "name": "Carson Beck", "team": "Georgia", "position": "QB"},
    ]

    # Mock get_connection to return a context manager with a mock conn
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_cursor.description = [("id",), ("name",), ("team",), ("position",)]
    mock_cursor.fetchall = AsyncMock(
        return_value=[(p["id"], p["name"], p["team"], p["position"]) for p in players_from_db]
    )

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    # Build async context manager mock
    mock_conn_cm = AsyncMock()
    mock_conn_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn_cm.__aexit__ = AsyncMock(return_value=False)

    grade_1 = _make_pff_grade(name="Arch Manning", player_id="111")
    grade_2 = _make_pff_grade(name="Carson Beck", player_id="222", team="Georgia")

    mock_pff_client = MagicMock()
    mock_pff_client.get_player_by_name = AsyncMock(side_effect=[grade_1, grade_2])
    mock_pff_client.__aenter__ = AsyncMock(return_value=mock_pff_client)
    mock_pff_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.processing.pff_pipeline.get_connection", return_value=mock_conn_cm),
        patch("src.processing.pff_pipeline.PFFClient", return_value=mock_pff_client),
        patch(
            "src.processing.pff_pipeline.upsert_pff_grade",
            new_callable=AsyncMock,
            return_value=1,
        ) as mock_upsert,
    ):
        stats = await run_pff_pipeline(batch_size=10)

    assert stats["players_checked"] == 2
    assert stats["grades_stored"] == 2
    assert stats["errors"] == 0
    assert mock_upsert.await_count == 2
