"""Tests for 247Sports crawler."""

import pytest

from src.crawlers.recruiting.two47 import Two47Crawler, build_team_commits_url, build_player_url


def test_build_team_commits_url():
    """Test building 247 team commits page URL."""
    url = build_team_commits_url("texas", 2025)
    assert url == "https://247sports.com/college/texas/Season/2025-Football/Commits/"


def test_build_team_commits_url_different_team():
    """Test URL for different team."""
    url = build_team_commits_url("ohio-state", 2024)
    assert url == "https://247sports.com/college/ohio-state/Season/2024-Football/Commits/"


def test_build_player_url():
    """Test building player profile URL."""
    url = build_player_url("Arch-Manning-46084734")
    assert url == "https://247sports.com/Player/Arch-Manning-46084734/"
