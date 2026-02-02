"""Player identity embedding generation using OpenAI."""

import os
from dataclasses import dataclass

from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Lazy-initialized client (None until first use, allows mocking in tests)
openai_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Get or create OpenAI client."""
    global openai_client
    if openai_client is None:
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return openai_client


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""

    identity_text: str
    embedding: list[float]


def build_identity_text(player: dict) -> str:
    """Build identity text string from player data.

    Format: "Name | Position | Team | Year | Hometown"
    Missing fields are omitted.

    Args:
        player: Dict with keys: name, team, year, and optionally
                position, hometown

    Returns:
        Identity string for embedding
    """
    parts = [player["name"]]

    if player.get("position"):
        parts.append(player["position"])

    parts.append(player["team"])
    parts.append(str(player["year"]))

    if player.get("hometown"):
        parts.append(player["hometown"])

    return " | ".join(parts)


def generate_embedding(identity_text: str) -> EmbeddingResult:
    """Generate embedding vector for identity text.

    Args:
        identity_text: Player identity string

    Returns:
        EmbeddingResult with text and 1536-dim vector
    """
    client = _get_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=identity_text,
    )

    return EmbeddingResult(
        identity_text=identity_text,
        embedding=response.data[0].embedding,
    )
