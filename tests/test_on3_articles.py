"""Tests for On3ArticleCrawler."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.crawlers.articles.on3_articles import (
    TEAM_SLUG_MAP,
    On3ArticleCrawler,
)

# --- Sample HTML fixtures ---

SAMPLE_ON3_INDEX_HTML = """
<html><body>
<div class="news-feed">
    <a href="/news/texas-longhorns-spring-practice-report-12345/">Texas Spring Practice Report</a>
    <a href="/news/five-star-commits-to-longhorns-67890/">Five-Star Commits to Longhorns</a>
    <a href="/teams/texas-longhorns/roster/">Roster Link</a>
    <a href="/news/texas-longhorns-spring-practice-report-12345/">Texas Spring Practice Report</a>
</div>
</body></html>
"""

EMPTY_ON3_INDEX_HTML = """
<html><body>
<div class="news-feed">
    <p>No news articles available.</p>
</div>
</body></html>
"""

SAMPLE_ON3_ARTICLE_HTML = """
<html><head>
<meta property="og:title" content="Texas Longhorns Spring Practice: Key Takeaways" />
</head><body>
<article>
    <h1>Texas Longhorns Spring Practice: Key Takeaways</h1>
    <span class="article-author">David Johnson</span>
    <time datetime="2025-03-20T14:00:00Z">March 20, 2025</time>
    <div class="article-body">
        <p>The Texas Longhorns wrapped up their spring practice schedule on Saturday with
        an impressive showing from several key players on both sides of the ball.</p>
        <p>Quarterback Arch Manning continued his strong spring, completing 15 of 20 passes
        in the team's final scrimmage. His command of the offense has improved dramatically.</p>
        <p>On the defensive side, sophomore linebacker Marcus Williams showed the kind of
        sideline-to-sideline speed that has coaches excited about the upcoming season.</p>
    </div>
</article>
</body></html>
"""

ON3_PAYWALLED_HTML = """
<html><head>
<meta property="og:title" content="On3+ Exclusive Analysis" />
</head><body>
<article>
    <h1>On3+ Exclusive Analysis</h1>
    <div class="article-body">
        <p>Become an On3+ member to read.</p>
    </div>
</article>
</body></html>
"""

ON3_FALLBACK_HTML = """
<html><head>
<meta property="og:title" content="Fallback On3 Article" />
</head><body>
<main>
    <p>This article uses the main tag fallback path instead of article-body class.</p>
    <p>The content discusses recruiting developments and scouting evaluations for
    multiple prospects in the 2026 recruiting class.</p>
</main>
</body></html>
"""


# --- Team slug mapping tests ---


def test_team_slug_map_has_expected_teams():
    """Test TEAM_SLUG_MAP contains the 4 daily pipeline teams."""
    assert "texas" in TEAM_SLUG_MAP
    assert "ohio-state" in TEAM_SLUG_MAP
    assert "georgia" in TEAM_SLUG_MAP
    assert "alabama" in TEAM_SLUG_MAP


def test_get_on3_slug_known_team():
    """Test _get_on3_slug returns mapped slug."""
    crawler = On3ArticleCrawler()
    assert crawler._get_on3_slug("texas") == "texas-longhorns"
    assert crawler._get_on3_slug("ohio-state") == "ohio-state-buckeyes"


def test_get_on3_slug_unknown_team():
    """Test _get_on3_slug returns None for unmapped teams."""
    crawler = On3ArticleCrawler()
    assert crawler._get_on3_slug("unknown-team") is None


# --- Index page parse tests ---


def test_parse_index_page_extracts_links():
    """Test _parse_index_page finds On3 article links and deduplicates."""
    crawler = On3ArticleCrawler()
    links = crawler._parse_index_page(SAMPLE_ON3_INDEX_HTML)

    assert len(links) == 2
    assert links[0].url == "https://www.on3.com/news/texas-longhorns-spring-practice-report-12345/"
    assert links[0].title == "Texas Spring Practice Report"
    assert links[1].url == "https://www.on3.com/news/five-star-commits-to-longhorns-67890/"


def test_parse_index_page_empty():
    """Test _parse_index_page returns empty list for no articles."""
    crawler = On3ArticleCrawler()
    links = crawler._parse_index_page(EMPTY_ON3_INDEX_HTML)
    assert links == []


# --- Article extract tests ---


def test_extract_article_content_full():
    """Test extract_article_content parses all fields from On3 article."""
    crawler = On3ArticleCrawler()
    article = crawler.extract_article_content(
        SAMPLE_ON3_ARTICLE_HTML,
        "https://www.on3.com/news/test-12345/",
    )

    assert article is not None
    assert article.title == "Texas Longhorns Spring Practice: Key Takeaways"
    assert article.author == "David Johnson"
    assert article.published_at == "2025-03-20T14:00:00Z"
    assert "15 of 20 passes" in article.body
    assert "Marcus Williams" in article.body


def test_extract_article_content_paywalled():
    """Test extract_article_content returns short body for paywalled stubs."""
    crawler = On3ArticleCrawler()
    article = crawler.extract_article_content(
        ON3_PAYWALLED_HTML,
        "https://www.on3.com/news/premium-12345/",
    )

    assert article is not None
    assert len(article.body) < 100


def test_extract_article_content_fallback():
    """Test extract_article_content uses <main> fallback for body."""
    crawler = On3ArticleCrawler()
    article = crawler.extract_article_content(
        ON3_FALLBACK_HTML,
        "https://www.on3.com/news/fallback-12345/",
    )

    assert article is not None
    assert article.title == "Fallback On3 Article"
    assert "recruiting developments" in article.body


def test_extract_article_content_no_title():
    """Test extract_article_content returns None when no title found."""
    crawler = On3ArticleCrawler()
    article = crawler.extract_article_content(
        "<html><body><p>No title here</p></body></html>",
        "https://www.on3.com/news/no-title-12345/",
    )
    assert article is None


# --- Discovery integration test ---


@patch("src.crawlers.articles.base.asyncio.sleep", new_callable=AsyncMock)
async def test_discover_article_urls(mock_sleep):
    """Test discover_article_urls fetches On3 index and returns links."""
    crawler = On3ArticleCrawler(teams=["texas"])

    mock_response = MagicMock()
    mock_response.text = SAMPLE_ON3_INDEX_HTML
    mock_response.raise_for_status = MagicMock()

    crawler._client = MagicMock()
    crawler._client.get = AsyncMock(return_value=mock_response)

    links = await crawler.discover_article_urls("texas")

    assert len(links) == 2
    crawler._client.get.assert_awaited_once_with("https://www.on3.com/teams/texas-longhorns/news/")


async def test_discover_article_urls_unmapped_team():
    """Test discover_article_urls returns empty for unmapped team slugs."""
    crawler = On3ArticleCrawler(teams=["unknown"])
    links = await crawler.discover_article_urls("unknown")
    assert links == []


def test_build_index_url():
    """Test _build_index_url constructs correct On3 URL."""
    crawler = On3ArticleCrawler()
    url = crawler._build_index_url("texas-longhorns")
    assert url == "https://www.on3.com/teams/texas-longhorns/news/"
