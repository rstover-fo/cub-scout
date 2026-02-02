"""Tests for player embedding generation."""

import pytest
from unittest.mock import patch, MagicMock

from src.processing.embeddings import (
    build_identity_text,
    generate_embedding,
    EmbeddingResult,
)


def test_build_identity_text_basic():
    """Test building identity text from player dict."""
    player = {
        "name": "Arch Manning",
        "position": "QB",
        "team": "Texas",
        "year": 2024,
    }
    result = build_identity_text(player)
    assert result == "Arch Manning | QB | Texas | 2024"


def test_build_identity_text_with_hometown():
    """Test identity text includes hometown when present."""
    player = {
        "name": "Arch Manning",
        "position": "QB",
        "team": "Texas",
        "year": 2024,
        "hometown": "New Orleans, LA",
    }
    result = build_identity_text(player)
    assert result == "Arch Manning | QB | Texas | 2024 | New Orleans, LA"


def test_build_identity_text_missing_fields():
    """Test identity text handles missing optional fields."""
    player = {
        "name": "John Smith",
        "team": "Alabama",
        "year": 2024,
    }
    result = build_identity_text(player)
    assert result == "John Smith | Alabama | 2024"


@patch("src.processing.embeddings.openai_client")
def test_generate_embedding_returns_result(mock_client):
    """Test generating embedding returns EmbeddingResult."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response

    result = generate_embedding("Arch Manning | QB | Texas | 2024")

    assert isinstance(result, EmbeddingResult)
    assert len(result.embedding) == 1536
    assert result.identity_text == "Arch Manning | QB | Texas | 2024"


@patch("src.processing.embeddings.openai_client")
def test_generate_embedding_calls_openai(mock_client):
    """Test that generate_embedding calls OpenAI with correct params."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response

    generate_embedding("test text")

    mock_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input="test text",
    )
