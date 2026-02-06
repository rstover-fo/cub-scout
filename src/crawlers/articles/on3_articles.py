"""On3 article crawler for scouting content."""

import logging
import re

from bs4 import BeautifulSoup

from .base import ArticleContent, ArticleCrawlerBase, ArticleLink

logger = logging.getLogger(__name__)

# On3 uses different team slugs than 247Sports
TEAM_SLUG_MAP: dict[str, str] = {
    "texas": "texas-longhorns",
    "ohio-state": "ohio-state-buckeyes",
    "georgia": "georgia-bulldogs",
    "alabama": "alabama-crimson-tide",
}

ON3_ARTICLE_PATTERN = re.compile(r"/news/[^/]+-\d+/?$", re.IGNORECASE)


class On3ArticleCrawler(ArticleCrawlerBase):
    """Crawler for On3 scouting articles."""

    source_name = "on3"
    request_delay = 2.0

    def _get_on3_slug(self, team_slug: str) -> str | None:
        """Map a standard team slug to On3's slug format."""
        on3_slug = TEAM_SLUG_MAP.get(team_slug)
        if not on3_slug:
            logger.warning(f"No On3 slug mapping for team: {team_slug}")
        return on3_slug

    def _build_index_url(self, on3_slug: str) -> str:
        """Build the news listing URL for a team on On3."""
        return f"https://www.on3.com/teams/{on3_slug}/news/"

    async def discover_article_urls(self, team_slug: str) -> list[ArticleLink]:
        """Discover article URLs from On3 team news page."""
        on3_slug = self._get_on3_slug(team_slug)
        if not on3_slug:
            return []

        index_url = self._build_index_url(on3_slug)
        html = await self._fetch_page(index_url)
        if not html:
            return []

        return self._parse_index_page(html)

    def _parse_index_page(self, html: str) -> list[ArticleLink]:
        """Parse article links from the On3 news index page."""
        soup = BeautifulSoup(html, "lxml")
        links: list[ArticleLink] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if not ON3_ARTICLE_PATTERN.search(href):
                continue

            if href.startswith("/"):
                href = f"https://www.on3.com{href}"

            if href in seen:
                continue
            seen.add(href)

            title = anchor.get_text(strip=True) or None
            links.append(ArticleLink(url=href, title=title))

        return links

    def extract_article_content(self, html: str, url: str) -> ArticleContent | None:
        """Extract article content from an On3 article page."""
        soup = BeautifulSoup(html, "lxml")

        # Title: try h1, then og:title
        title = None
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                title = og_title.get("content", "").strip()
        if not title:
            return None

        # Author
        author = None
        author_elem = soup.select_one(
            ".article-author, .author-name, [class*='AuthorName'], [rel='author']"
        )
        if author_elem:
            author = author_elem.get_text(strip=True)

        # Published date
        published_at = None
        time_elem = soup.find("time", datetime=True)
        if time_elem:
            published_at = time_elem["datetime"]

        # Body text
        body_parts: list[str] = []
        article_body = soup.select_one(
            ".article-body, .article-content, [class*='ArticleBody'], [class*='article-body']"
        )
        if article_body:
            for p in article_body.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    body_parts.append(text)
        else:
            main = soup.find("main") or soup.find("article") or soup
            for p in main.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    body_parts.append(text)

        body = "\n\n".join(body_parts)
        if not body:
            return None

        return ArticleContent(
            url=url,
            title=title,
            author=author,
            published_at=published_at,
            body=body,
        )
