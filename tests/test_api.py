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
