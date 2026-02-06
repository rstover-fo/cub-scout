"""Tests for Two47ArticleCrawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.crawlers.articles.two47_articles import Two47ArticleCrawler

# --- Sample HTML fixtures ---

SAMPLE_INDEX_HTML = """
<html><body>
<div class="articles-list">
    <a href="/Article/texas-qb-impresses-in-spring-12345/">Texas QB Impresses in Spring</a>
    <a href="/Article/longhorns-land-five-star-67890/">Longhorns Land Five-Star</a>
    <a href="/college/texas/Season/2025-Football/Commits/">Commits Page</a>
    <a href="/Article/texas-qb-impresses-in-spring-12345/">Texas QB Impresses in Spring</a>
</div>
</body></html>
"""

EMPTY_INDEX_HTML = """
<html><body>
<div class="articles-list">
    <p>No articles found.</p>
</div>
</body></html>
"""

SAMPLE_ARTICLE_HTML = """
<html><head>
<meta property="og:title" content="Texas QB Arch Manning Impresses in Spring Practice" />
</head><body>
<article>
    <h1>Texas QB Arch Manning Impresses in Spring Practice</h1>
    <span class="author-name">Mike Roach</span>
    <time datetime="2025-03-15T10:30:00Z">March 15, 2025</time>
    <div class="article-body">
        <p>Arch Manning has been the talk of Austin this spring, showing remarkable improvement
        in his pocket presence and ability to read defenses at the second and third level.</p>
        <p>The sophomore signal-caller completed 18 of 22 passes in Saturday's scrimmage,
        including a beautiful 45-yard touchdown to Xavier Worthy down the seam.</p>
        <p>Offensive coordinator Kyle Flood praised Manning's development, noting his ability
        to progress through his reads and make anticipatory throws has taken a significant
        leap since last season.</p>
    </div>
</article>
</body></html>
"""

PAYWALLED_ARTICLE_HTML = """
<html><head>
<meta property="og:title" content="Premium: Insider Report" />
</head><body>
<article>
    <h1>Premium: Insider Report</h1>
    <div class="article-body">
        <p>Subscribe to read this article.</p>
    </div>
</article>
</body></html>
"""

NO_TITLE_ARTICLE_HTML = """
<html><body>
<div class="article-body">
    <p>This article has no title or og:title meta tag.</p>
</div>
</body></html>
"""

FALLBACK_ARTICLE_HTML = """
<html><head>
<meta property="og:title" content="Fallback Title" />
</head><body>
<main>
    <p>This article uses main tag fallback instead of article-body class.</p>
    <p>It still contains scouting content about the player's impressive arm strength
    and accuracy in the intermediate passing game.</p>
</main>
</body></html>
"""


# --- Index page parse tests ---


def test_parse_index_page_extracts_article_links():
    """Test _parse_index_page finds article links and deduplicates."""
    crawler = Two47ArticleCrawler(teams=["texas"])
    links = crawler._parse_index_page(SAMPLE_INDEX_HTML)

    assert len(links) == 2
    assert links[0].url == "https://247sports.com/Article/texas-qb-impresses-in-spring-12345/"
    assert links[0].title == "Texas QB Impresses in Spring"
    assert links[1].url == "https://247sports.com/Article/longhorns-land-five-star-67890/"


def test_parse_index_page_empty():
    """Test _parse_index_page returns empty list for no articles."""
    crawler = Two47ArticleCrawler(teams=["texas"])
    links = crawler._parse_index_page(EMPTY_INDEX_HTML)
    assert links == []


# --- Article extract tests ---


def test_extract_article_content_full():
    """Test extract_article_content parses all fields from article HTML."""
    crawler = Two47ArticleCrawler()
    article = crawler.extract_article_content(
        SAMPLE_ARTICLE_HTML,
        "https://247sports.com/Article/texas-qb-12345/",
    )

    assert article is not None
    assert article.title == "Texas QB Arch Manning Impresses in Spring Practice"
    assert article.author == "Mike Roach"
    assert article.published_at == "2025-03-15T10:30:00Z"
    assert "pocket presence" in article.body
    assert "18 of 22 passes" in article.body
    assert "Kyle Flood" in article.body


def test_extract_article_content_paywalled():
    """Test extract_article_content returns content for paywalled stubs.

    The base class crawl() method handles the MIN_BODY_LENGTH check.
    """
    crawler = Two47ArticleCrawler()
    article = crawler.extract_article_content(
        PAYWALLED_ARTICLE_HTML,
        "https://247sports.com/Article/premium-12345/",
    )

    # Extract returns content; the base crawl() checks length threshold
    assert article is not None
    assert article.title == "Premium: Insider Report"
    assert len(article.body) < 100  # Short stub


def test_extract_article_content_no_title():
    """Test extract_article_content returns None when no title found."""
    crawler = Two47ArticleCrawler()
    article = crawler.extract_article_content(
        NO_TITLE_ARTICLE_HTML,
        "https://247sports.com/Article/no-title-12345/",
    )
    assert article is None


def test_extract_article_content_fallback_selector():
    """Test extract_article_content falls back to <main> for body text."""
    crawler = Two47ArticleCrawler()
    article = crawler.extract_article_content(
        FALLBACK_ARTICLE_HTML,
        "https://247sports.com/Article/fallback-12345/",
    )

    assert article is not None
    assert article.title == "Fallback Title"
    assert "arm strength" in article.body


# --- Discovery integration test ---


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_discover_article_urls(mock_sleep):
    """Test discover_article_urls fetches index and returns links."""
    crawler = Two47ArticleCrawler(teams=["texas"])

    mock_response = MagicMock()
    mock_response.text = SAMPLE_INDEX_HTML
    mock_response.raise_for_status = MagicMock()

    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(return_value=mock_response)

    links = await crawler.discover_article_urls("texas")

    assert len(links) == 2
    crawler._client.get.assert_awaited_once_with("https://247sports.com/college/texas/Article/")


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_discover_article_urls_fetch_failure(mock_sleep):
    """Test discover_article_urls returns empty list on fetch failure."""
    crawler = Two47ArticleCrawler(teams=["texas"])

    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(side_effect=httpx.ConnectError("Network error"))

    links = await crawler.discover_article_urls("texas")
    assert links == []


def test_build_index_url():
    """Test _build_index_url constructs correct URL."""
    crawler = Two47ArticleCrawler()
    url = crawler._build_index_url("ohio-state")
    assert url == "https://247sports.com/college/ohio-state/Article/"
