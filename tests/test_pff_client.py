"""Tests for PFF API client."""

import pytest
from unittest.mock import patch, MagicMock

from src.clients.pff import PFFClient, PFFPlayerGrade


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
