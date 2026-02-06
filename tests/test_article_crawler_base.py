"""Tests for ArticleCrawlerBase."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.crawlers.articles.base import (
    MIN_BODY_LENGTH,
    ArticleContent,
    ArticleCrawlerBase,
    ArticleLink,
)
from src.crawlers.base import CrawlResult


class FakeArticleCrawler(ArticleCrawlerBase):
    """Concrete subclass for testing the base class."""

    source_name = "fake"
    request_delay = 0.0

    def __init__(self, teams=None, articles=None):
        super().__init__(teams=teams)
        self._articles = articles or {}

    async def discover_article_urls(self, team_slug: str) -> list[ArticleLink]:
        return [ArticleLink(url=url) for url in self._articles.keys()]

    def extract_article_content(self, html: str, url: str) -> ArticleContent | None:
        return self._articles.get(url)


# --- Fetch tests ---


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_fetch_page_success(mock_sleep):
    """Test _fetch_page returns HTML on success."""
    crawler = FakeArticleCrawler()
    mock_response = MagicMock()
    mock_response.text = "<html>Test</html>"
    mock_response.raise_for_status = MagicMock()

    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(return_value=mock_response)

    result = await crawler._fetch_page("https://example.com/article/1")
    assert result == "<html>Test</html>"
    mock_sleep.assert_awaited_once()


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_fetch_page_403(mock_sleep):
    """Test _fetch_page returns None on 403."""
    crawler = FakeArticleCrawler()
    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "403 Forbidden",
            request=MagicMock(),
            response=MagicMock(status_code=403),
        )
    )

    result = await crawler._fetch_page("https://example.com/blocked")
    assert result is None


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_fetch_page_429(mock_sleep):
    """Test _fetch_page returns None on rate limit."""
    crawler = FakeArticleCrawler()
    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )
    )

    result = await crawler._fetch_page("https://example.com/ratelimited")
    assert result is None


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_fetch_page_network_error(mock_sleep):
    """Test _fetch_page returns None on network error."""
    crawler = FakeArticleCrawler()
    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    result = await crawler._fetch_page("https://example.com/down")
    assert result is None


# --- Dedup test ---


async def test_is_already_crawled():
    """Test _is_already_crawled returns True for known URLs."""
    crawler = FakeArticleCrawler()

    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    result = await crawler._is_already_crawled(mock_conn, "https://example.com/article/1")
    assert result is True


async def test_is_not_already_crawled():
    """Test _is_already_crawled returns False for new URLs."""
    crawler = FakeArticleCrawler()

    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)

    result = await crawler._is_already_crawled(mock_conn, "https://example.com/new-article")
    assert result is False


# --- crawl() integration test ---


@patch("src.crawlers.articles.base.get_connection")
async def test_crawl_stores_new_articles(mock_get_conn):
    """Test crawl() discovers, fetches, extracts, and stores articles."""
    article_url = "https://example.com/article/1"
    article_body = "A" * 200  # > MIN_BODY_LENGTH
    article = ArticleContent(
        url=article_url,
        title="Test Article",
        author="Author",
        published_at="2025-01-15",
        body=article_body,
    )

    crawler = FakeArticleCrawler(teams=["texas"], articles={article_url: article})

    # Mock DB
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)  # not already crawled
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_get_conn.return_value = mock_conn

    # Mock _fetch_page and insert_report
    with (
        patch.object(crawler, "_fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("src.crawlers.articles.base.insert_report", new_callable=AsyncMock) as mock_insert,
    ):
        mock_fetch.return_value = "<html>article html</html>"
        mock_insert.return_value = 42

        result = await crawler.crawl()

    assert isinstance(result, CrawlResult)
    assert result.source_name == "fake"
    assert result.records_crawled == 1
    assert result.records_new == 1
    assert result.errors == []

    mock_insert.assert_awaited_once()
    call_kwargs = mock_insert.call_args.kwargs
    assert call_kwargs["source_url"] == article_url
    assert call_kwargs["source_name"] == "fake"
    assert call_kwargs["raw_text"] == article_body


@patch("src.crawlers.articles.base.get_connection")
async def test_crawl_skips_already_crawled(mock_get_conn):
    """Test crawl() skips articles already in the DB."""
    article_url = "https://example.com/article/old"
    article = ArticleContent(url=article_url, title="Old", body="B" * 200)

    crawler = FakeArticleCrawler(teams=["texas"], articles={article_url: article})

    # DB says this URL exists
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_get_conn.return_value = mock_conn

    with patch("src.crawlers.articles.base.insert_report", new_callable=AsyncMock) as mock_insert:
        result = await crawler.crawl()

    assert result.records_crawled == 1
    assert result.records_new == 0
    mock_insert.assert_not_awaited()


@patch("src.crawlers.articles.base.get_connection")
async def test_crawl_skips_short_articles(mock_get_conn):
    """Test crawl() skips articles with body shorter than threshold."""
    article_url = "https://example.com/article/stub"
    short_body = "x" * (MIN_BODY_LENGTH - 1)
    article = ArticleContent(url=article_url, title="Stub", body=short_body)

    crawler = FakeArticleCrawler(teams=["texas"], articles={article_url: article})

    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_get_conn.return_value = mock_conn

    with (
        patch.object(crawler, "_fetch_page", new_callable=AsyncMock) as mock_fetch,
        patch("src.crawlers.articles.base.insert_report", new_callable=AsyncMock) as mock_insert,
    ):
        mock_fetch.return_value = "<html>stub</html>"
        result = await crawler.crawl()

    assert result.records_new == 0
    mock_insert.assert_not_awaited()
