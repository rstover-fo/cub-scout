# tests/test_api.py
"""Tests for FastAPI endpoints."""

from fastapi.testclient import TestClient

from src.api.main import app


client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_players():
    """Test listing players."""
    response = client.get("/players")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_players_with_filters():
    """Test listing players with filters."""
    response = client.get("/players?team=Texas&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 10


def test_get_player_not_found():
    """Test 404 for missing player."""
    response = client.get("/players/999999")
    assert response.status_code == 404


def test_list_teams():
    """Test listing teams."""
    response = client.get("/teams")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_rising_trends():
    """Test rising stocks endpoint."""
    response = client.get("/trends/rising")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_falling_trends():
    """Test falling stocks endpoint."""
    response = client.get("/trends/falling")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_draft_board():
    """Test draft board endpoint."""
    response = client.get("/draft/board")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_draft_board_by_position():
    """Test draft board by position."""
    response = client.get("/draft/position/QB")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_watchlist_requires_user_id():
    """Test that watchlist endpoints require user_id."""
    response = client.get("/watchlists")
    assert response.status_code == 422  # Validation error


# Phase 5 - Alert Tests


def test_get_alerts_requires_user_id():
    """Test that alerts endpoints require user_id."""
    response = client.get("/alerts")
    assert response.status_code == 422


def test_get_alert_history():
    """Test alert history endpoint."""
    response = client.get("/alerts/history?user_id=test-user")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# Phase 5 - Transfer Portal Tests


def test_get_active_portal_players():
    """Test active portal players endpoint."""
    response = client.get("/transfer-portal/active")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_portal_players_by_position():
    """Test portal players filtered by position."""
    response = client.get("/transfer-portal/active?position=QB")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_team_transfers():
    """Test team transfer activity endpoint."""
    response = client.get("/teams/Texas/transfers")
    assert response.status_code == 200
    data = response.json()
    assert "outgoing" in data
    assert "incoming" in data
    assert "net" in data
