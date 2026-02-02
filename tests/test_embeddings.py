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


@patch("src.processing.embeddings._get_client")
def test_generate_embedding_returns_result(mock_get_client):
    """Test generating embedding returns EmbeddingResult."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = generate_embedding("Arch Manning | QB | Texas | 2024")

    assert isinstance(result, EmbeddingResult)
    assert len(result.embedding) == 1536
    assert result.identity_text == "Arch Manning | QB | Texas | 2024"


@patch("src.processing.embeddings._get_client")
def test_generate_embedding_calls_openai(mock_get_client):
    """Test that generate_embedding calls OpenAI with correct params."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    generate_embedding("test text")

    mock_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input="test text",
    )


# Database function tests


def test_upsert_player_embedding_new(mock_db_connection):
    """Test inserting a new player embedding."""
    from src.storage.db import upsert_player_embedding

    # Use a unique roster_id for this test
    test_roster_id = "test_embed_12345"

    try:
        embedding_id = upsert_player_embedding(
            conn=mock_db_connection,
            roster_id=test_roster_id,
            identity_text="Arch Manning | QB | Texas | 2024",
            embedding=[0.1] * 1536,
        )

        assert embedding_id > 0
    finally:
        # Clean up test data
        cur = mock_db_connection.cursor()
        cur.execute(
            "DELETE FROM scouting.player_embeddings WHERE roster_id = %s",
            (test_roster_id,),
        )
        mock_db_connection.commit()


def test_get_player_embedding(mock_db_connection):
    """Test retrieving a player embedding by roster_id."""
    from src.storage.db import upsert_player_embedding, get_player_embedding

    test_roster_id = "test_embed_67890"

    try:
        upsert_player_embedding(
            conn=mock_db_connection,
            roster_id=test_roster_id,
            identity_text="Arch Manning | QB | Texas | 2024",
            embedding=[0.1] * 1536,
        )

        result = get_player_embedding(mock_db_connection, roster_id=test_roster_id)

        assert result is not None
        assert result["roster_id"] == test_roster_id
        assert result["identity_text"] == "Arch Manning | QB | Texas | 2024"
    finally:
        cur = mock_db_connection.cursor()
        cur.execute(
            "DELETE FROM scouting.player_embeddings WHERE roster_id = %s",
            (test_roster_id,),
        )
        mock_db_connection.commit()


def test_find_similar_by_embedding(mock_db_connection):
    """Test finding similar players by embedding vector."""
    from src.storage.db import upsert_player_embedding, find_similar_by_embedding

    test_ids = ["test_similar_111", "test_similar_222", "test_similar_333"]

    try:
        # Insert a few players
        upsert_player_embedding(
            conn=mock_db_connection,
            roster_id=test_ids[0],
            identity_text="Player One | QB | Texas | 2024",
            embedding=[0.1] * 1536,
        )
        upsert_player_embedding(
            conn=mock_db_connection,
            roster_id=test_ids[1],
            identity_text="Player Two | QB | Texas | 2024",
            embedding=[0.11] * 1536,  # Similar
        )
        upsert_player_embedding(
            conn=mock_db_connection,
            roster_id=test_ids[2],
            identity_text="Player Three | RB | Alabama | 2024",
            embedding=[0.9] * 1536,  # Different
        )

        # Search for similar to first player
        results = find_similar_by_embedding(
            conn=mock_db_connection,
            embedding=[0.1] * 1536,
            limit=2,
            exclude_roster_id=test_ids[0],
        )

        assert len(results) == 2
        # Player Two should be most similar
        assert results[0]["roster_id"] == test_ids[1]
    finally:
        cur = mock_db_connection.cursor()
        for roster_id in test_ids:
            cur.execute(
                "DELETE FROM scouting.player_embeddings WHERE roster_id = %s",
                (roster_id,),
            )
        mock_db_connection.commit()
