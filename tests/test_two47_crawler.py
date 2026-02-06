"""Tests for 247Sports crawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.crawlers.recruiting.two47 import (
    Two47Crawler,
    build_player_url,
    build_team_board_url,
    build_team_commits_url,
)

# --- URL builder tests (existing) ---


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


def test_build_team_board_url():
    """Test building team message board URL."""
    url = build_team_board_url("texas")
    assert url == "https://247sports.com/college/texas/board/21/"


def test_build_team_board_url_custom_id():
    """Test building board URL with custom board ID."""
    url = build_team_board_url("ohio-state", board_id=42)
    assert url == "https://247sports.com/college/ohio-state/board/42/"


# --- Sample HTML fixtures ---


SAMPLE_COMMITS_HTML = """
<html><body>
<div class="ri-page__list-item">
    <a class="ri-page__name-link" href="/Player/John-Smith-46084734/">John Smith</a>
    <span class="position">QB</span>
    <span class="ri-page__star-and-score">
        <span class="icon-starsolid"></span>
        <span class="icon-starsolid"></span>
        <span class="icon-starsolid"></span>
        <span class="icon-starsolid"></span>
    </span>
    <span class="rating">0.9845</span>
    <span class="meta">Austin, TX</span>
</div>
<div class="ri-page__list-item">
    <a class="ri-page__name-link" href="/Player/Jane-Doe-46084735/">Jane Doe</a>
    <span class="position">WR</span>
    <span class="ri-page__star-and-score">
        <span class="icon-starsolid"></span>
        <span class="icon-starsolid"></span>
        <span class="icon-starsolid"></span>
    </span>
    <span class="rating">0.8920</span>
    <span class="meta">Dallas, TX</span>
</div>
</body></html>
"""

EMPTY_COMMITS_HTML = """
<html><body>
<div class="ri-page__content">
    <p>No commits found for this team.</p>
</div>
</body></html>
"""

PARTIAL_DATA_HTML = """
<html><body>
<div class="ri-page__list-item">
    <a class="ri-page__name-link" href="/Player/Bob-Jones-46084736/">Bob Jones</a>
    <span class="position">RB</span>
    <span class="meta">Miami, FL</span>
</div>
</body></html>
"""


# --- Parse tests ---


def test_parse_commits_page_extracts_players():
    """Test _parse_commits_page extracts player data from HTML."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])
    commits = crawler._parse_commits_page(SAMPLE_COMMITS_HTML)

    assert len(commits) == 2

    # First player: John Smith
    assert commits[0].name == "John Smith"
    assert commits[0].position == "QB"
    assert commits[0].stars == 4
    assert commits[0].rating == 0.9845
    assert commits[0].city == "Austin"
    assert commits[0].state == "TX"
    assert commits[0].player_slug == "John-Smith-46084734"
    assert commits[0].status == "committed"

    # Second player: Jane Doe
    assert commits[1].name == "Jane Doe"
    assert commits[1].position == "WR"
    assert commits[1].stars == 3
    assert commits[1].rating == 0.8920
    assert commits[1].city == "Dallas"
    assert commits[1].state == "TX"
    assert commits[1].player_slug == "Jane-Doe-46084735"


def test_parse_commits_page_empty_html():
    """Test _parse_commits_page returns empty list for HTML with no player rows."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])
    commits = crawler._parse_commits_page(EMPTY_COMMITS_HTML)

    assert commits == []


def test_parse_commits_page_partial_data():
    """Test _parse_commits_page handles player rows missing rating and stars."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])
    commits = crawler._parse_commits_page(PARTIAL_DATA_HTML)

    assert len(commits) == 1
    assert commits[0].name == "Bob Jones"
    assert commits[0].position == "RB"
    assert commits[0].stars is None
    assert commits[0].rating is None
    assert commits[0].city == "Miami"
    assert commits[0].state == "FL"
    assert commits[0].player_slug == "Bob-Jones-46084736"


# --- Fetch tests ---


@patch("src.crawlers.recruiting.two47.asyncio.sleep", new_callable=AsyncMock)
async def test_fetch_page_success(mock_sleep):
    """Test _fetch_page returns HTML text on successful response."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])

    mock_response = MagicMock()
    mock_response.text = "<html><body>Test page</body></html>"
    mock_response.raise_for_status = MagicMock()

    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(return_value=mock_response)

    result = await crawler._fetch_page("https://247sports.com/test/")

    assert result == "<html><body>Test page</body></html>"
    mock_sleep.assert_awaited_once()
    crawler._client.get.assert_awaited_once_with("https://247sports.com/test/")


@patch("src.crawlers.recruiting.two47.asyncio.sleep", new_callable=AsyncMock)
async def test_fetch_page_http_error(mock_sleep):
    """Test _fetch_page returns None on HTTP error."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])

    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "403 Forbidden",
            request=MagicMock(),
            response=MagicMock(status_code=403),
        )
    )

    result = await crawler._fetch_page("https://247sports.com/blocked/")

    assert result is None
    mock_sleep.assert_awaited_once()


# --- Integration test ---


async def test_crawl_team_commits_integration():
    """Test crawl_team_commits returns PlayerCommit list from mocked HTML."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])

    with patch.object(crawler, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = SAMPLE_COMMITS_HTML
        commits = await crawler.crawl_team_commits("texas", 2025)

    assert len(commits) == 2
    assert commits[0].name == "John Smith"
    assert commits[0].position == "QB"
    assert commits[1].name == "Jane Doe"
    assert commits[1].position == "WR"

    mock_fetch.assert_awaited_once_with(
        "https://247sports.com/college/texas/Season/2025-Football/Commits/"
    )


async def test_crawl_team_commits_fetch_failure():
    """Test crawl_team_commits returns empty list when fetch fails."""
    crawler = Two47Crawler(teams=["texas"], years=[2025])

    with patch.object(crawler, "_fetch_page", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        commits = await crawler.crawl_team_commits("texas", 2025)

    assert commits == []
