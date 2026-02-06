# tests/test_api_mutations.py
"""Tests for mutation (POST/DELETE) API endpoints."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


@asynccontextmanager
async def mock_conn():
    yield AsyncMock()


MOCK_WATCHLIST = {
    "id": 1,
    "name": "My List",
    "description": "Test watchlist",
    "player_ids": [],
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00",
}

MOCK_ALERT = {
    "id": 1,
    "user_id": "test-user",
    "name": "Grade Alert",
    "alert_type": "grade_change",
    "player_id": 1,
    "team": None,
    "threshold": None,
    "is_active": True,
    "created_at": "2025-01-01T00:00:00",
    "last_checked_at": None,
}


# --- Watchlist mutation tests ---


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.get_watch_list", new_callable=AsyncMock, return_value=MOCK_WATCHLIST)
@patch("src.api.main.create_watch_list", new_callable=AsyncMock, return_value=1)
def test_create_watchlist(mock_create, mock_get, mock_conn_patch):
    """POST /watchlists creates a watchlist and returns it."""
    response = client.post(
        "/watchlists?user_id=test-user",
        json={"name": "My List", "description": "Test watchlist"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "My List"
    assert data["player_ids"] == []
    assert "created_at" in data
    assert "updated_at" in data
    mock_create.assert_called_once()
    mock_get.assert_called_once()


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.add_to_watch_list", new_callable=AsyncMock, return_value=None)
def test_add_player_to_watchlist(mock_add, mock_conn_patch):
    """POST /watchlists/{list_id}/players/{player_id} adds a player."""
    response = client.post("/watchlists/1/players/42")
    assert response.status_code == 200
    assert response.json() == {"status": "added"}
    mock_add.assert_called_once()


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.remove_from_watch_list", new_callable=AsyncMock, return_value=None)
def test_remove_player_from_watchlist(mock_remove, mock_conn_patch):
    """DELETE /watchlists/{list_id}/players/{player_id} removes a player."""
    response = client.delete("/watchlists/1/players/42")
    assert response.status_code == 200
    assert response.json() == {"status": "removed"}
    mock_remove.assert_called_once()


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.delete_watch_list", new_callable=AsyncMock, return_value=None)
def test_delete_watchlist(mock_delete, mock_conn_patch):
    """DELETE /watchlists/{list_id} deletes the watchlist."""
    response = client.delete("/watchlists/1")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    mock_delete.assert_called_once()


# --- Alert mutation tests ---


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.get_alert", new_callable=AsyncMock, return_value=MOCK_ALERT)
@patch("src.api.main.create_alert", new_callable=AsyncMock, return_value=1)
def test_create_alert(mock_create, mock_get, mock_conn_patch):
    """POST /alerts creates an alert and returns it."""
    response = client.post(
        "/alerts?user_id=test-user",
        json={"name": "Grade Alert", "alert_type": "grade_change", "player_id": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["user_id"] == "test-user"
    assert data["name"] == "Grade Alert"
    assert data["alert_type"] == "grade_change"
    assert data["player_id"] == 1
    assert data["is_active"] is True
    mock_create.assert_called_once()
    mock_get.assert_called_once()


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.delete_alert", new_callable=AsyncMock, return_value=None)
def test_delete_alert(mock_delete, mock_conn_patch):
    """DELETE /alerts/{alert_id} deletes the alert."""
    response = client.delete("/alerts/1")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    mock_delete.assert_called_once()


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.deactivate_alert", new_callable=AsyncMock, return_value=None)
def test_deactivate_alert(mock_deactivate, mock_conn_patch):
    """POST /alerts/{alert_id}/deactivate deactivates the alert."""
    response = client.post("/alerts/1/deactivate")
    assert response.status_code == 200
    assert response.json() == {"status": "deactivated"}
    mock_deactivate.assert_called_once()


@patch("src.api.main.get_connection", side_effect=mock_conn)
@patch("src.api.main.mark_alert_read", new_callable=AsyncMock, return_value=None)
def test_mark_alert_read(mock_read, mock_conn_patch):
    """POST /alerts/history/{history_id}/read marks the alert as read."""
    response = client.post("/alerts/history/5/read")
    assert response.status_code == 200
    assert response.json() == {"status": "read"}
    mock_read.assert_called_once()


# --- Transfer Portal mutation tests ---


@patch(
    "src.api.main.generate_portal_snapshot",
    new_callable=AsyncMock,
    return_value={"snapshot_id": 1, "player_count": 42},
)
def test_create_portal_snapshot(mock_snapshot):
    """POST /transfer-portal/snapshot generates a snapshot."""
    response = client.post("/transfer-portal/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert "snapshot_id" in data
    mock_snapshot.assert_called_once()


# --- Validation tests ---


def test_create_watchlist_requires_user_id():
    """POST /watchlists without user_id returns 422."""
    response = client.post(
        "/watchlists",
        json={"name": "My List"},
    )
    assert response.status_code == 422


def test_create_alert_requires_user_id():
    """POST /alerts without user_id returns 422."""
    response = client.post(
        "/alerts",
        json={"name": "Grade Alert", "alert_type": "grade_change"},
    )
    assert response.status_code == 422
