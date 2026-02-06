"""Tests for PFF API client."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.clients.pff import PFFClient, PFFPlayerGrade

# --- Existing tests ---


def test_pff_client_init_requires_api_key():
    """Test that client requires API key."""
    with pytest.raises(ValueError, match="PFF_API_KEY"):
        PFFClient(api_key=None)


def test_pff_client_init_with_key():
    """Test client initializes with API key."""
    client = PFFClient(api_key="test-key")
    assert client.api_key == "test-key"


def test_pff_player_grade_model():
    """Test PFFPlayerGrade pydantic model."""
    grade = PFFPlayerGrade(
        player_id="12345",
        name="Arch Manning",
        position="QB",
        team="Texas",
        overall_grade=85.5,
        passing_grade=87.2,
        rushing_grade=72.1,
        snaps=450,
        season=2025,
    )
    assert grade.overall_grade == 85.5
    assert grade.position == "QB"


# --- Sample API response ---

SAMPLE_PFF_RESPONSE = {
    "players": [
        {
            "id": 12345,
            "name": "Arch Manning",
            "position": "QB",
            "team": "Texas",
            "overall_grade": 85.5,
            "passing_grade": 87.2,
            "rushing_grade": 72.1,
            "snaps": 450,
        }
    ]
}

SAMPLE_PFF_MULTI_RESPONSE = {
    "players": [
        {
            "id": 12345,
            "name": "Arch Manning",
            "position": "QB",
            "team": "Texas",
            "overall_grade": 85.5,
            "passing_grade": 87.2,
            "rushing_grade": 72.1,
            "snaps": 450,
        },
        {
            "id": 67890,
            "name": "Quinn Ewers",
            "position": "QB",
            "team": "Texas",
            "overall_grade": 78.3,
            "passing_grade": 80.1,
            "snaps": 320,
        },
    ]
}


# --- Helpers ---


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx response."""
    response = MagicMock()
    response.json.return_value = json_data
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    return response


# --- get_player_grades tests ---


async def test_get_player_grades_success():
    """Test get_player_grades returns PFFPlayerGrade list from API response."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(return_value=_make_mock_response(SAMPLE_PFF_RESPONSE))

    grades = await client.get_player_grades(team="Texas", season=2025)

    assert len(grades) == 1
    assert isinstance(grades[0], PFFPlayerGrade)
    assert grades[0].player_id == "12345"
    assert grades[0].name == "Arch Manning"
    assert grades[0].position == "QB"
    assert grades[0].team == "Texas"
    assert grades[0].overall_grade == 85.5
    assert grades[0].passing_grade == 87.2
    assert grades[0].rushing_grade == 72.1
    assert grades[0].snaps == 450
    assert grades[0].season == 2025

    await client.close()


async def test_get_player_grades_with_filters():
    """Test that team and position filters are passed as query params."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(return_value=_make_mock_response(SAMPLE_PFF_MULTI_RESPONSE))

    await client.get_player_grades(team="Texas", position="QB", season=2025, limit=50)

    client.client.get.assert_awaited_once()
    call_args = client.client.get.call_args
    assert call_args[0][0] == "/grades/players"
    params = call_args[1]["params"]
    assert params["team"] == "Texas"
    assert params["position"] == "QB"
    assert params["season"] == 2025
    assert params["limit"] == 50
    assert params["league"] == "ncaa"

    await client.close()


async def test_get_player_grades_no_filters():
    """Test get_player_grades without team/position only sends defaults."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(return_value=_make_mock_response({"players": []}))

    grades = await client.get_player_grades()

    assert grades == []
    call_args = client.client.get.call_args
    params = call_args[1]["params"]
    assert "team" not in params
    assert "position" not in params
    assert params["season"] == 2025

    await client.close()


async def test_get_player_grades_http_error():
    """Test get_player_grades raises on HTTP error."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_player_grades(team="Texas")

    await client.close()


# --- get_player_by_name tests ---


async def test_get_player_by_name_found():
    """Test get_player_by_name returns PFFPlayerGrade when player found."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(return_value=_make_mock_response(SAMPLE_PFF_RESPONSE))

    grade = await client.get_player_by_name("Arch Manning", team="Texas", season=2025)

    assert grade is not None
    assert isinstance(grade, PFFPlayerGrade)
    assert grade.name == "Arch Manning"
    assert grade.player_id == "12345"
    assert grade.overall_grade == 85.5

    # Verify correct endpoint called
    call_args = client.client.get.call_args
    assert call_args[0][0] == "/grades/players/search"
    params = call_args[1]["params"]
    assert params["search"] == "Arch Manning"
    assert params["team"] == "Texas"
    assert params["season"] == 2025

    await client.close()


async def test_get_player_by_name_not_found():
    """Test get_player_by_name returns None when no players in response."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(return_value=_make_mock_response({"players": []}))

    grade = await client.get_player_by_name("Nobody Real")

    assert grade is None
    await client.close()


async def test_get_player_by_name_http_error():
    """Test get_player_by_name returns None on HTTP error (catches exception)."""
    client = PFFClient(api_key="test-key")
    client.client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "403 Forbidden",
            request=MagicMock(),
            response=MagicMock(status_code=403),
        )
    )

    grade = await client.get_player_by_name("Arch Manning", team="Texas")

    assert grade is None
    await client.close()


# --- Context manager and close tests ---


async def test_pff_client_context_manager():
    """Test PFF client works as async context manager."""
    async with PFFClient(api_key="test-key") as client:
        assert isinstance(client, PFFClient)
        assert client.api_key == "test-key"
        # Replace the real client with a mock so close doesn't hit network
        client.client = MagicMock()
        client.client.aclose = AsyncMock()

    client.client.aclose.assert_awaited_once()


async def test_pff_client_close():
    """Test close calls aclose on the httpx client."""
    client = PFFClient(api_key="test-key")
    client.client = MagicMock()
    client.client.aclose = AsyncMock()

    await client.close()

    client.client.aclose.assert_awaited_once()
