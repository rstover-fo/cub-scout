"""247Sports article crawler for scouting content."""

import logging
import re

from bs4 import BeautifulSoup

from .base import ArticleContent, ArticleCrawlerBase, ArticleLink

logger = logging.getLogger(__name__)

ARTICLE_URL_PATTERN = re.compile(r"/Article/[^/]+-\d+/?$", re.IGNORECASE)


class Two47ArticleCrawler(ArticleCrawlerBase):
    """Crawler for 247Sports scouting articles."""

    source_name = "247sports"
    request_delay = 2.5

    def _build_index_url(self, team_slug: str) -> str:
        """Build the article listing URL for a team."""
        return f"https://247sports.com/college/{team_slug}/Article/"

    async def discover_article_urls(self, team_slug: str) -> list[ArticleLink]:
        """Discover article URLs from 247Sports team article index."""
        index_url = self._build_index_url(team_slug)
        html = await self._fetch_page(index_url)
        if not html:
            return []

        return self._parse_index_page(html)

    def _parse_index_page(self, html: str) -> list[ArticleLink]:
        """Parse article links from the 247 index page."""
        soup = BeautifulSoup(html, "lxml")
        links: list[ArticleLink] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if not ARTICLE_URL_PATTERN.search(href):
                continue

            # Normalize to absolute URL
            if href.startswith("/"):
                href = f"https://247sports.com{href}"

            if href in seen:
                continue
            seen.add(href)

            title = anchor.get_text(strip=True) or None
            links.append(ArticleLink(url=href, title=title))

        return links

    def extract_article_content(self, html: str, url: str) -> ArticleContent | None:
        """Extract article content from a 247Sports article page."""
        soup = BeautifulSoup(html, "lxml")

        # Title: try h1, then og:title meta tag
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
        author_elem = soup.select_one(".author-name, .article-author-name, [rel='author']")
        if author_elem:
            author = author_elem.get_text(strip=True)

        # Published date
        published_at = None
        time_elem = soup.find("time", datetime=True)
        if time_elem:
            published_at = time_elem["datetime"]

        # Body text: try article body container, fall back to all <p> in main
        body_parts: list[str] = []
        article_body = soup.select_one(
            ".article-body, .article__body, .article-content, [class*='ArticleBody']"
        )
        if article_body:
            for p in article_body.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    body_parts.append(text)
        else:
            # Fallback: paragraphs in main content area
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
