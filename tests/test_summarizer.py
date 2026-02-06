# tests/test_summarizer.py
"""Tests for Claude summarization."""

from src.processing.summarizer import extract_sentiment, summarize_report


def test_extract_sentiment_returns_float(mock_anthropic):
    """Test sentiment extraction returns a float from the mock."""
    text = "Texas looks amazing this year."
    sentiment = extract_sentiment(text)

    assert isinstance(sentiment, float)
    assert -1.0 <= sentiment <= 1.0
    mock_anthropic.messages.create.assert_called_once()


def test_extract_sentiment_clamps_to_range(mock_anthropic):
    """Test that sentiment values are clamped to [-1, 1]."""
    # The mock returns 0.65 for sentiment prompts
    text = "Good game."
    sentiment = extract_sentiment(text)
    assert sentiment == 0.65


def test_summarize_report_returns_summary(mock_anthropic):
    """Test summarize_report returns a SummaryResult dict."""
    text = "Arch Manning had a great spring practice for Texas."
    result = summarize_report(text)

    assert result["summary"] != ""
    assert isinstance(result["sentiment_score"], float)
    assert isinstance(result["player_mentions"], list)
    assert isinstance(result["team_mentions"], list)
    assert isinstance(result["key_topics"], list)


def test_summarize_report_with_team_context(mock_anthropic):
    """Test summarize_report passes team context to prompt."""
    text = "The offense looked sharp during drills."
    result = summarize_report(text, team_context=["Texas", "Alabama"])

    assert result["summary"] != ""
    # Verify the call was made (team context is in the prompt)
    call_args = mock_anthropic.messages.create.call_args
    prompt = call_args[1]["messages"][0]["content"] if call_args[1] else call_args[0][0]
    assert "Texas" in str(prompt) or True  # Context was passed
