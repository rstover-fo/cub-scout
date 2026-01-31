# tests/test_summarizer.py
"""Tests for Claude summarization."""

from src.processing.summarizer import extract_sentiment


def test_extract_sentiment_positive():
    """Test sentiment extraction for positive content."""
    text = "Texas looks amazing this year. The offense is explosive and the defense is elite."
    sentiment = extract_sentiment(text)
    assert sentiment > 0.3  # Clearly positive


def test_extract_sentiment_negative():
    """Test sentiment extraction for negative content."""
    text = "Ohio State is struggling. The injuries are piling up and morale is low."
    sentiment = extract_sentiment(text)
    assert sentiment < -0.3  # Clearly negative


def test_extract_sentiment_neutral():
    """Test sentiment extraction for neutral content."""
    text = "The game is scheduled for Saturday at 3pm. Kickoff time was announced yesterday."
    sentiment = extract_sentiment(text)
    assert -0.5 <= sentiment <= 0.5  # Neutral-ish range (LLMs can vary)
