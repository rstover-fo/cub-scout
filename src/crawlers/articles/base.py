"""Base class for article crawlers."""

import asyncio
import logging
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime

import httpx

from ...storage.db import get_connection, insert_report
from ..base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

MIN_BODY_LENGTH = 100


@dataclass
class ArticleLink:
    """Discovered article URL with metadata."""

    url: str
    title: str | None = None


@dataclass
class ArticleContent:
    """Extracted article content."""

    url: str
    title: str
    author: str | None = None
    published_at: str | None = None
    body: str = ""


class ArticleCrawlerBase(BaseCrawler):
    """Base class for article crawlers with shared discovery/extraction loop."""

    source_name: str = "unknown"
    request_delay: float = 2.0

    def __init__(self, teams: list[str] | None = None):
        self.teams = teams or ["texas"]
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-load async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def _fetch_page(self, url: str) -> str | None:
        """Fetch page with rate limiting and error handling."""
        try:
            await asyncio.sleep(self.request_delay)
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                logger.warning(f"Rate limited by {self.source_name}: {url}")
            elif status == 403:
                logger.warning(f"Blocked by {self.source_name}: {url}")
            else:
                logger.error(f"HTTP {status} fetching {url}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    async def _is_already_crawled(self, conn, url: str) -> bool:
        """Check if a URL has already been crawled."""
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM scouting.reports WHERE source_url = %s",
                (url,),
            )
            return await cur.fetchone() is not None

    @abstractmethod
    async def discover_article_urls(self, team_slug: str) -> list[ArticleLink]:
        """Discover article URLs from a team index page."""
        ...

    @abstractmethod
    def extract_article_content(self, html: str, url: str) -> ArticleContent | None:
        """Extract article content from HTML. Returns None for stubs/paywalled."""
        ...

    async def crawl(self) -> CrawlResult:
        """Discover articles, skip known URLs, fetch, extract, and store."""
        started = self.log_start()
        errors: list[str] = []
        records_crawled = 0
        records_new = 0

        async with get_connection() as conn:
            for team_slug in self.teams:
                try:
                    links = await self.discover_article_urls(team_slug)
                except Exception as e:
                    errors.append(f"Discovery failed for {team_slug}: {e}")
                    logger.error(f"Discovery failed for {team_slug}: {e}")
                    continue

                for link in links:
                    records_crawled += 1
                    try:
                        if await self._is_already_crawled(conn, link.url):
                            continue

                        html = await self._fetch_page(link.url)
                        if not html:
                            errors.append(f"Fetch failed: {link.url}")
                            continue

                        article = self.extract_article_content(html, link.url)
                        if not article or len(article.body) < MIN_BODY_LENGTH:
                            logger.debug(f"Skipping stub/short article: {link.url}")
                            continue

                        team_name = team_slug.replace("-", " ").title()
                        report_id = await insert_report(
                            conn,
                            source_url=article.url,
                            source_name=self.source_name,
                            content_type="article",
                            raw_text=article.body,
                            team_ids=[team_name],
                            published_at=article.published_at,
                        )
                        if report_id:
                            records_new += 1
                            logger.info(f"Stored article: {article.title} ({link.url})")

                    except Exception as e:
                        errors.append(f"Error processing {link.url}: {e}")
                        logger.warning(f"Error processing article: {e}")

            if self._client:
                await self._client.aclose()

        completed = datetime.now()
        result = CrawlResult(
            source_name=self.source_name,
            records_crawled=records_crawled,
            records_new=records_new,
            errors=errors,
            started_at=started,
            completed_at=completed,
        )
        self.log_complete(result)
        return result
