"""247Sports crawler for recruiting content."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from ...storage.db import get_connection, insert_report
from ..base import BaseCrawler, CrawlResult

logger = logging.getLogger(__name__)

# Rate limiting: 247 is aggressive about blocking
REQUEST_DELAY = 2.0  # seconds between requests
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def build_team_commits_url(team_slug: str, year: int) -> str:
    """Build URL for team commits page."""
    return f"https://247sports.com/college/{team_slug}/Season/{year}-Football/Commits/"


def build_player_url(player_slug: str) -> str:
    """Build URL for player profile page."""
    return f"https://247sports.com/Player/{player_slug}/"


def build_team_board_url(team_slug: str, board_id: int = 21) -> str:
    """Build URL for team message board."""
    return f"https://247sports.com/college/{team_slug}/board/{board_id}/"


@dataclass
class PlayerCommit:
    """Parsed player commit data."""

    name: str
    position: str
    height: str | None
    weight: str | None
    stars: int | None
    rating: float | None
    high_school: str | None
    city: str | None
    state: str | None
    player_slug: str | None
    status: str  # "committed", "enrolled", "transfer"


class Two47Crawler(BaseCrawler):
    """Crawler for 247Sports recruiting content."""

    source_name = "247sports"

    def __init__(
        self,
        teams: list[str] | None = None,
        years: list[int] | None = None,
    ):
        """Initialize 247Sports crawler.

        Args:
            teams: List of team slugs (e.g., ["texas", "ohio-state"]).
            years: List of recruiting years to crawl.
        """
        self.teams = teams or ["texas"]
        self.years = years or [2025]
        self._client = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    def _fetch_page(self, url: str) -> str | None:
        """Fetch page with rate limiting."""
        try:
            time.sleep(REQUEST_DELAY)
            response = self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _parse_commits_page(self, html: str) -> list[PlayerCommit]:
        """Parse commits page HTML into PlayerCommit objects."""
        soup = BeautifulSoup(html, "lxml")
        commits = []

        # Find player rows in the commits table
        player_rows = soup.select(".ri-page__list-item, .recruit")

        for row in player_rows:
            try:
                # Extract player name and link
                name_elem = row.select_one(".ri-page__name-link, a.player")
                if not name_elem:
                    continue

                name = name_elem.get_text(strip=True)
                href = name_elem.get("href", "")
                player_slug = href.split("/Player/")[-1].rstrip("/") if "/Player/" in href else None

                # Extract position
                pos_elem = row.select_one(".position, .pos")
                position = pos_elem.get_text(strip=True) if pos_elem else ""

                # Extract rating/stars
                rating_elem = row.select_one(".rating, .stars-and-score .score")
                rating = None
                if rating_elem:
                    try:
                        rating = float(rating_elem.get_text(strip=True))
                    except ValueError:
                        pass

                # Extract stars (count star icons or parse text)
                stars_elem = row.select_one(".ri-page__star-and-score, .stars")
                stars = None
                if stars_elem:
                    star_icons = stars_elem.select(".icon-starsolid, .yellow")
                    stars = len(star_icons) if star_icons else None

                # Extract location
                location_elem = row.select_one(".meta, .location")
                location_text = location_elem.get_text(strip=True) if location_elem else ""

                # Parse "City, ST" format
                city, state = None, None
                if ", " in location_text:
                    parts = location_text.rsplit(", ", 1)
                    city = parts[0] if len(parts) > 0 else None
                    state = parts[1] if len(parts) > 1 else None

                commits.append(
                    PlayerCommit(
                        name=name,
                        position=position,
                        height=None,  # Requires player page
                        weight=None,
                        stars=stars,
                        rating=rating,
                        high_school=None,
                        city=city,
                        state=state,
                        player_slug=player_slug,
                        status="committed",
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing player row: {e}")
                continue

        return commits

    def crawl_team_commits(self, team_slug: str, year: int) -> list[PlayerCommit]:
        """Crawl commits for a specific team/year."""
        url = build_team_commits_url(team_slug, year)
        logger.info(f"Crawling {url}")

        html = self._fetch_page(url)
        if not html:
            return []

        return self._parse_commits_page(html)

    async def crawl(self) -> CrawlResult:
        """Crawl all configured teams/years."""
        started = self.log_start()
        errors = []
        records_crawled = 0
        records_new = 0

        async with get_connection() as conn:
            for team in self.teams:
                for year in self.years:
                    commits = self.crawl_team_commits(team, year)
                    records_crawled += len(commits)

                    for commit in commits:
                        try:
                            # Build raw text from commit data
                            raw_text = (
                                f"{commit.name} ({commit.position}) - "
                                f"{commit.stars or '?'}-star recruit"
                            )
                            if commit.city and commit.state:
                                raw_text += f" from {commit.city}, {commit.state}"
                            raw_text += (
                                f". Committed to {team.replace('-', ' ').title()} for {year}."
                            )
                            if commit.rating:
                                raw_text += f" Rating: {commit.rating}."

                            source_url = (
                                build_player_url(commit.player_slug)
                                if commit.player_slug
                                else f"{build_team_commits_url(team, year)}#{commit.name}"
                            )

                            report_id = await insert_report(
                                conn,
                                source_url=source_url,
                                source_name=self.source_name,
                                content_type="article",
                                raw_text=raw_text,
                                team_ids=[team.replace("-", " ").title()],
                            )
                            if report_id:
                                records_new += 1

                        except Exception as e:
                            errors.append(f"Error storing {commit.name}: {e}")
                            logger.warning(f"Error storing commit: {e}")

            if self._client:
                self._client.close()

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
