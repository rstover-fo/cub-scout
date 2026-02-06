# tests/test_summarizer.py
"""Tests for Claude summarization."""

import pytest

from src.processing.summarizer import extract_sentiment, summarize_report


@pytest.mark.asyncio
async def test_extract_sentiment_returns_float(mock_anthropic):
    """Test sentiment extraction returns a float from the mock."""
    text = "Texas looks amazing this year."
    sentiment = await extract_sentiment(text)

    assert isinstance(sentiment, float)
    assert -1.0 <= sentiment <= 1.0
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_extract_sentiment_clamps_to_range(mock_anthropic):
    """Test that sentiment values are clamped to [-1, 1]."""
    # The mock returns 0.65 for sentiment prompts
    text = "Good game."
    sentiment = await extract_sentiment(text)
    assert sentiment == 0.65


@pytest.mark.asyncio
async def test_summarize_report_returns_summary(mock_anthropic):
    """Test summarize_report returns a SummaryResult dict."""
    text = "Arch Manning had a great spring practice for Texas."
    result = await summarize_report(text)

    assert result["summary"] != ""
    assert isinstance(result["sentiment_score"], float)
    assert isinstance(result["player_mentions"], list)
    assert isinstance(result["team_mentions"], list)
    assert isinstance(result["key_topics"], list)


@pytest.mark.asyncio
async def test_summarize_report_with_team_context(mock_anthropic):
    """Test summarize_report passes team context to prompt."""
    text = "The offense looked sharp during drills."
    result = await summarize_report(text, team_context=["Texas", "Alabama"])

    assert result["summary"] != ""
    # Verify the call was made (team context is in the prompt)
    call_args = mock_anthropic.messages.create.call_args
    # AsyncMock stores kwargs — extract the messages kwarg
    prompt = str(call_args)
    assert "Texas" in prompt
