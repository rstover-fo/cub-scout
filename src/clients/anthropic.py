"""Shared async Anthropic client for all processing modules."""

import os

from anthropic import AsyncAnthropic

_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    """Get or create the shared async Anthropic client.

    Lazy-initialized on first call. Safe to call multiple times.
    """
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client
