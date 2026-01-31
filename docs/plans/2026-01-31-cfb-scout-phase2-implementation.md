# CFB Scout Agent Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 247Sports scraper and player entity linking to match crawled content with existing roster/recruit data in Supabase.

**Architecture:** BeautifulSoup-based scraper for 247Sports team pages and player profiles. Player entity extraction from report text using Claude, then fuzzy matching against `core.roster` and `recruiting.recruits` tables. New `scouting.players` records link scouting content to existing player data.

**Tech Stack:** Python 3.12, BeautifulSoup4, httpx, Anthropic SDK, psycopg2, rapidfuzz (fuzzy matching)

---

## Task 1: Add Scraping Dependencies

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/pyproject.toml`

**Step 1: Add beautifulsoup4 and rapidfuzz**

```toml
dependencies = [
    "praw>=7.7.0",
    "anthropic>=0.18.0",
    "psycopg2-binary>=2.9.9",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",
    "rapidfuzz>=3.6.0",
]
```

**Step 2: Install updated dependencies**

```bash
cd /Users/robstover/Development/personal/cfb-scout
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: All packages install successfully.

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add beautifulsoup4, lxml, rapidfuzz dependencies"
```

---

## Task 2: Create 247Sports Scraper Base

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/crawlers/recruiting/__init__.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/src/crawlers/recruiting/two47.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_two47_crawler.py`

**Step 1: Create recruiting crawler package**

```bash
touch /Users/robstover/Development/personal/cfb-scout/src/crawlers/recruiting/__init__.py
```

**Step 2: Write failing test for URL builder**

```python
# tests/test_two47_crawler.py
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
```

**Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_two47_crawler.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 4: Write minimal implementation**

```python
# src/crawlers/recruiting/two47.py
"""247Sports crawler for recruiting content."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from ..base import BaseCrawler, CrawlResult
from ...storage.db import get_connection, insert_report

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

                commits.append(PlayerCommit(
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
                ))
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

    def crawl(self) -> CrawlResult:
        """Crawl all configured teams/years."""
        started = self.log_start()
        errors = []
        records_crawled = 0
        records_new = 0

        conn = get_connection()

        try:
            for team in self.teams:
                for year in self.years:
                    commits = self.crawl_team_commits(team, year)
                    records_crawled += len(commits)

                    for commit in commits:
                        try:
                            # Build raw text from commit data
                            raw_text = f"{commit.name} ({commit.position}) - {commit.stars or '?'}-star recruit"
                            if commit.city and commit.state:
                                raw_text += f" from {commit.city}, {commit.state}"
                            raw_text += f". Committed to {team.replace('-', ' ').title()} for {year}."
                            if commit.rating:
                                raw_text += f" Rating: {commit.rating}."

                            source_url = build_player_url(commit.player_slug) if commit.player_slug else f"{build_team_commits_url(team, year)}#{commit.name}"

                            report_id = insert_report(
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

        finally:
            conn.close()
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
```

**Step 5: Run tests**

```bash
python -m pytest tests/test_two47_crawler.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add src/crawlers/recruiting/ tests/test_two47_crawler.py
git commit -m "feat: add 247Sports crawler with commits page parser"
```

---

## Task 3: Create Player Entity Extraction Module

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/entity_extraction.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_entity_extraction.py`

**Step 1: Write failing test**

```python
# tests/test_entity_extraction.py
"""Tests for player entity extraction."""

import pytest

from src.processing.entity_extraction import extract_player_mentions, normalize_name


def test_normalize_name():
    """Test name normalization."""
    assert normalize_name("Arch Manning") == "arch manning"
    assert normalize_name("  John Smith Jr. ") == "john smith jr"
    assert normalize_name("D'Andre Swift") == "dandre swift"


def test_extract_player_mentions_finds_names():
    """Test that player names are extracted from text."""
    text = """
    Texas QB Arch Manning continues to impress in spring practice.
    Wide receiver Isaiah Bond made several big catches.
    The defense, led by linebacker Anthony Hill, looks strong.
    """
    players = extract_player_mentions(text)

    assert len(players) >= 2  # Should find multiple names
    assert any("manning" in p.lower() for p in players)
    assert any("bond" in p.lower() for p in players)


def test_extract_player_mentions_handles_positions():
    """Test extraction handles position prefixes."""
    text = "QB Quinn Ewers and RB Jaydon Blue both had great games."
    players = extract_player_mentions(text)

    assert any("ewers" in p.lower() for p in players)
    assert any("blue" in p.lower() for p in players)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_entity_extraction.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/processing/entity_extraction.py
"""Player entity extraction from scouting content."""

import logging
import os
import re
from typing import TypedDict

import anthropic

logger = logging.getLogger(__name__)

# Common CFB position abbreviations
POSITIONS = [
    "QB", "RB", "WR", "TE", "OL", "OT", "OG", "C",
    "DL", "DT", "DE", "EDGE", "LB", "ILB", "OLB", "MLB",
    "DB", "CB", "S", "FS", "SS", "K", "P", "LS", "ATH",
]

# Regex to find "Position Name" patterns
POSITION_NAME_PATTERN = re.compile(
    rf'\b({"|".join(POSITIONS)})\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
    re.IGNORECASE
)

# Regex to find capitalized names (2-4 words)
NAME_PATTERN = re.compile(
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
)


def normalize_name(name: str) -> str:
    """Normalize a name for matching.

    - Lowercase
    - Remove extra whitespace
    - Remove apostrophes
    """
    name = name.lower().strip()
    name = re.sub(r"['\"]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def extract_player_mentions(text: str) -> list[str]:
    """Extract potential player names from text using regex patterns.

    This is a fast heuristic extraction. For higher accuracy,
    use extract_player_mentions_claude().
    """
    players = set()

    # Find "Position Name" patterns
    for match in POSITION_NAME_PATTERN.finditer(text):
        name = match.group(2).strip()
        if len(name.split()) >= 2:  # At least first + last
            players.add(name)

    # Find standalone capitalized names that look like player names
    # Filter out common non-names
    SKIP_WORDS = {
        "The", "This", "That", "When", "Where", "What", "Which", "While",
        "After", "Before", "During", "With", "From", "Into", "About",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
        "Spring", "Summer", "Fall", "Winter", "Practice", "Game",
        "Texas", "Ohio State", "Alabama", "Georgia", "Michigan",  # Team names
    }

    for match in NAME_PATTERN.finditer(text):
        name = match.group(1).strip()
        words = name.split()

        # Skip if first word is a common non-name
        if words[0] in SKIP_WORDS:
            continue

        # Must be 2-4 words, not all caps
        if 2 <= len(words) <= 4 and not name.isupper():
            players.add(name)

    return list(players)


class PlayerMention(TypedDict):
    """Structured player mention from Claude extraction."""
    name: str
    position: str | None
    team: str | None
    context: str  # "starter", "recruit", "transfer", etc.


def extract_player_mentions_claude(text: str) -> list[PlayerMention]:
    """Extract player mentions using Claude for higher accuracy.

    Use this for processing important content where accuracy matters.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": f"""Extract all college football player names mentioned in this text.

Text:
{text[:3000]}

Return a JSON array of objects with these fields:
- name: The player's full name
- position: Their position if mentioned (QB, RB, WR, etc.) or null
- team: Their team if mentioned or null
- context: One of "starter", "recruit", "transfer", "draft_prospect", "general"

Return only the JSON array, no other text. If no players mentioned, return [].

Example:
[{{"name": "Arch Manning", "position": "QB", "team": "Texas", "context": "starter"}}]"""
            }
        ],
    )

    try:
        import json
        response_text = response.content[0].text.strip()

        # Handle markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        result = json.loads(response_text)
        return [PlayerMention(**p) for p in result]
    except Exception as e:
        logger.warning(f"Failed to parse Claude response: {e}")
        return []
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_entity_extraction.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/entity_extraction.py tests/test_entity_extraction.py
git commit -m "feat: add player entity extraction with regex and Claude"
```

---

## Task 4: Create Player Matching Module

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/player_matching.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_player_matching.py`

**Step 1: Write failing test**

```python
# tests/test_player_matching.py
"""Tests for player matching against roster data."""

import pytest

from src.processing.player_matching import (
    fuzzy_match_name,
    find_roster_match,
    PlayerMatch,
)


def test_fuzzy_match_name_exact():
    """Test exact name matching."""
    score = fuzzy_match_name("Arch Manning", "Arch Manning")
    assert score == 100


def test_fuzzy_match_name_similar():
    """Test similar name matching."""
    score = fuzzy_match_name("Arch Manning", "Archibald Manning")
    assert score > 70  # Should be reasonably high


def test_fuzzy_match_name_different():
    """Test different names have low score."""
    score = fuzzy_match_name("Arch Manning", "Quinn Ewers")
    assert score < 50


def test_find_roster_match_integration():
    """Test finding a match in actual roster data."""
    # This test requires database connection
    match = find_roster_match("Arch Manning", team="Texas", position="QB")
    # May or may not find depending on roster data
    # Just verify it returns correct type
    assert match is None or isinstance(match, PlayerMatch)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_player_matching.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# src/processing/player_matching.py
"""Player matching against roster and recruit data."""

import logging
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from ..storage.db import get_connection

logger = logging.getLogger(__name__)

# Minimum score to consider a match
MATCH_THRESHOLD = 80


@dataclass
class PlayerMatch:
    """A matched player from roster or recruit data."""
    source: Literal["roster", "recruit"]
    source_id: str
    first_name: str
    last_name: str
    team: str
    position: str | None
    year: int | None
    confidence: float  # 0-100


def fuzzy_match_name(name1: str, name2: str) -> float:
    """Calculate fuzzy match score between two names.

    Returns score from 0-100.
    """
    # Normalize names
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()

    # Use token sort ratio which handles word order differences
    return fuzz.token_sort_ratio(n1, n2)


def find_roster_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int = 2024,
) -> PlayerMatch | None:
    """Find best matching player in core.roster.

    Args:
        name: Player name to match.
        team: Optional team filter.
        position: Optional position filter.
        year: Roster year to search.

    Returns:
        PlayerMatch if found above threshold, else None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Build query with optional filters
        query = """
            SELECT id, first_name, last_name, team, position, year
            FROM core.roster
            WHERE year = %s
        """
        params = [year]

        if team:
            query += " AND LOWER(team) = LOWER(%s)"
            params.append(team)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        cur.execute(query, params)
        candidates = cur.fetchall()

        best_match = None
        best_score = 0

        for row in candidates:
            player_id, first, last, player_team, player_pos, player_year = row
            full_name = f"{first} {last}"

            score = fuzzy_match_name(name, full_name)

            if score > best_score and score >= MATCH_THRESHOLD:
                best_score = score
                best_match = PlayerMatch(
                    source="roster",
                    source_id=str(player_id),
                    first_name=first,
                    last_name=last,
                    team=player_team,
                    position=player_pos,
                    year=player_year,
                    confidence=score,
                )

        return best_match

    finally:
        cur.close()
        conn.close()


def find_recruit_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
    year: int | None = None,
) -> PlayerMatch | None:
    """Find best matching player in recruiting.recruits.

    Args:
        name: Player name to match.
        team: Optional committed_to filter.
        position: Optional position filter.
        year: Optional recruiting year filter.

    Returns:
        PlayerMatch if found above threshold, else None.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        query = """
            SELECT id, name, committed_to, position, recruiting_year
            FROM recruiting.recruits
            WHERE 1=1
        """
        params = []

        if team:
            query += " AND LOWER(committed_to) = LOWER(%s)"
            params.append(team)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        if year:
            query += " AND recruiting_year = %s"
            params.append(year)

        cur.execute(query, params)
        candidates = cur.fetchall()

        best_match = None
        best_score = 0

        for row in candidates:
            recruit_id, recruit_name, committed_to, recruit_pos, recruit_year = row

            score = fuzzy_match_name(name, recruit_name)

            if score > best_score and score >= MATCH_THRESHOLD:
                best_score = score
                # Split name for consistency
                parts = recruit_name.split(maxsplit=1)
                first = parts[0] if parts else ""
                last = parts[1] if len(parts) > 1 else ""

                best_match = PlayerMatch(
                    source="recruit",
                    source_id=str(recruit_id),
                    first_name=first,
                    last_name=last,
                    team=committed_to or "",
                    position=recruit_pos,
                    year=recruit_year,
                    confidence=score,
                )

        return best_match

    finally:
        cur.close()
        conn.close()


def find_best_match(
    name: str,
    team: str | None = None,
    position: str | None = None,
) -> PlayerMatch | None:
    """Find best match across both roster and recruit data.

    Tries roster first (current players), then recruits.
    """
    # Try current roster first
    match = find_roster_match(name, team=team, position=position, year=2024)
    if match and match.confidence >= 90:
        return match

    # Try recruits
    recruit_match = find_recruit_match(name, team=team, position=position)

    # Return higher confidence match
    if recruit_match:
        if not match or recruit_match.confidence > match.confidence:
            return recruit_match

    return match
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_player_matching.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/player_matching.py tests/test_player_matching.py
git commit -m "feat: add player matching with fuzzy name search"
```

---

## Task 5: Create Scouting Player Upsert

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_player_upsert.py`

**Step 1: Write failing test**

```python
# tests/test_player_upsert.py
"""Tests for scouting player upsert."""

import pytest

from src.storage.db import get_connection, upsert_scouting_player, get_scouting_player


def test_upsert_scouting_player_creates_new():
    """Test creating a new scouting player."""
    conn = get_connection()

    player_id = upsert_scouting_player(
        conn,
        name="Test Player",
        team="Test Team",
        position="QB",
        class_year=2024,
        current_status="active",
        roster_player_id="test-roster-123",
    )

    assert player_id is not None
    assert player_id > 0

    # Clean up
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id,))
    conn.commit()
    conn.close()


def test_upsert_scouting_player_updates_existing():
    """Test updating an existing scouting player."""
    conn = get_connection()

    # Create initial
    player_id1 = upsert_scouting_player(
        conn,
        name="Update Test",
        team="Team A",
        position="RB",
        class_year=2024,
        current_status="active",
    )

    # Upsert with same key should update
    player_id2 = upsert_scouting_player(
        conn,
        name="Update Test",
        team="Team A",
        position="RB",
        class_year=2024,
        current_status="transfer",  # Changed status
        composite_grade=85,
    )

    assert player_id1 == player_id2  # Same record

    # Verify update
    player = get_scouting_player(conn, player_id1)
    assert player["current_status"] == "transfer"
    assert player["composite_grade"] == 85

    # Clean up
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.players WHERE id = %s", (player_id1,))
    conn.commit()
    conn.close()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_player_upsert.py -v
```

Expected: FAIL with "cannot import name 'upsert_scouting_player'"

**Step 3: Add implementation to db.py**

Add these functions to `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`:

```python
def upsert_scouting_player(
    conn: connection,
    name: str,
    team: str,
    position: str | None = None,
    class_year: int | None = None,
    current_status: str = "active",
    roster_player_id: str | None = None,
    recruit_id: str | None = None,
    composite_grade: int | None = None,
    traits: dict | None = None,
    draft_projection: str | None = None,
    comps: list[str] | None = None,
) -> int:
    """Upsert a scouting player profile.

    Uses (name, team, class_year) as the unique key.
    """
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.players
            (name, team, position, class_year, current_status,
             roster_player_id, recruit_id, composite_grade, traits,
             draft_projection, comps, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (name, team, class_year) DO UPDATE SET
            position = COALESCE(EXCLUDED.position, scouting.players.position),
            current_status = EXCLUDED.current_status,
            roster_player_id = COALESCE(EXCLUDED.roster_player_id, scouting.players.roster_player_id),
            recruit_id = COALESCE(EXCLUDED.recruit_id, scouting.players.recruit_id),
            composite_grade = COALESCE(EXCLUDED.composite_grade, scouting.players.composite_grade),
            traits = COALESCE(EXCLUDED.traits, scouting.players.traits),
            draft_projection = COALESCE(EXCLUDED.draft_projection, scouting.players.draft_projection),
            comps = COALESCE(EXCLUDED.comps, scouting.players.comps),
            last_updated = NOW()
        RETURNING id
        """,
        (
            name,
            team,
            position,
            class_year,
            current_status,
            roster_player_id,
            recruit_id,
            composite_grade,
            json.dumps(traits) if traits else None,
            draft_projection,
            comps or [],
        ),
    )
    player_id = cur.fetchone()[0]
    conn.commit()
    return player_id


def get_scouting_player(conn: connection, player_id: int) -> dict | None:
    """Get a scouting player by ID."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, team, position, class_year, current_status,
               roster_player_id, recruit_id, composite_grade, traits,
               draft_projection, comps, last_updated
        FROM scouting.players
        WHERE id = %s
        """,
        (player_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def link_report_to_player(
    conn: connection,
    report_id: int,
    player_id: int,
) -> None:
    """Link a report to a scouting player by adding to player_ids array."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.reports
        SET player_ids = array_append(
            COALESCE(player_ids, '{}'),
            %s
        )
        WHERE id = %s
        AND NOT (%s = ANY(COALESCE(player_ids, '{}')))
        """,
        (player_id, report_id, player_id),
    )
    conn.commit()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_player_upsert.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/storage/db.py tests/test_player_upsert.py
git commit -m "feat: add scouting player upsert and linking functions"
```

---

## Task 6: Create Entity Linking Pipeline

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/entity_linking.py`
- Modify: `/Users/robstover/Development/personal/cfb-scout/scripts/run_pipeline.py`

**Step 1: Create entity linking module**

```python
# src/processing/entity_linking.py
"""Entity linking pipeline - connects reports to player profiles."""

import logging

from ..storage.db import (
    get_connection,
    get_unprocessed_reports,
    upsert_scouting_player,
    link_report_to_player,
)
from .entity_extraction import extract_player_mentions, extract_player_mentions_claude
from .player_matching import find_best_match

logger = logging.getLogger(__name__)


def link_report_entities(
    report: dict,
    use_claude: bool = False,
) -> list[int]:
    """Extract and link player entities from a report.

    Args:
        report: Report dict with id, raw_text, team_ids.
        use_claude: Use Claude for entity extraction (more accurate, costs tokens).

    Returns:
        List of scouting.players IDs that were linked.
    """
    conn = get_connection()
    linked_player_ids = []

    try:
        # Extract player mentions
        if use_claude:
            mentions = extract_player_mentions_claude(report["raw_text"])
            names = [(m["name"], m.get("position"), m.get("team")) for m in mentions]
        else:
            names = [(name, None, None) for name in extract_player_mentions(report["raw_text"])]

        # Get team context from report
        team_context = report.get("team_ids", [])
        default_team = team_context[0] if team_context else None

        for name, position, team in names:
            # Try to find existing roster/recruit match
            match = find_best_match(
                name,
                team=team or default_team,
                position=position,
            )

            if match:
                # Create/update scouting player linked to roster/recruit
                player_id = upsert_scouting_player(
                    conn,
                    name=f"{match.first_name} {match.last_name}",
                    team=match.team,
                    position=match.position,
                    class_year=match.year,
                    current_status="active" if match.source == "roster" else "recruit",
                    roster_player_id=match.source_id if match.source == "roster" else None,
                    recruit_id=match.source_id if match.source == "recruit" else None,
                )
            else:
                # Create scouting player without link (new mention)
                player_id = upsert_scouting_player(
                    conn,
                    name=name,
                    team=team or default_team or "Unknown",
                    position=position,
                    class_year=2024,  # Default assumption
                    current_status="active",
                )

            # Link report to player
            link_report_to_player(conn, report["id"], player_id)
            linked_player_ids.append(player_id)
            logger.debug(f"Linked player {player_id} ({name}) to report {report['id']}")

        return linked_player_ids

    finally:
        conn.close()


def run_entity_linking(
    batch_size: int = 50,
    use_claude: bool = False,
) -> dict:
    """Run entity linking on processed reports without player links.

    Args:
        batch_size: Number of reports to process.
        use_claude: Use Claude for extraction.

    Returns:
        Stats dict.
    """
    conn = get_connection()

    try:
        # Get reports that are processed but have no player links
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, source_url, source_name, content_type, raw_text, team_ids
            FROM scouting.reports
            WHERE processed_at IS NOT NULL
            AND (player_ids IS NULL OR array_length(player_ids, 1) IS NULL)
            ORDER BY crawled_at ASC
            LIMIT %s
            """,
            (batch_size,),
        )
        columns = [desc[0] for desc in cur.description]
        reports = [dict(zip(columns, row)) for row in cur.fetchall()]

    finally:
        conn.close()

    logger.info(f"Found {len(reports)} reports needing entity linking")

    linked = 0
    errors = 0
    total_players = 0

    for report in reports:
        try:
            player_ids = link_report_entities(report, use_claude=use_claude)
            total_players += len(player_ids)
            linked += 1
        except Exception as e:
            logger.error(f"Error linking report {report['id']}: {e}")
            errors += 1

    return {
        "reports_processed": len(reports),
        "reports_linked": linked,
        "players_linked": total_players,
        "errors": errors,
    }
```

**Step 2: Update run_pipeline.py to include entity linking**

Add to the imports and argparse in `/Users/robstover/Development/personal/cfb-scout/scripts/run_pipeline.py`:

```python
# Add to imports
from src.processing.entity_linking import run_entity_linking
from src.crawlers.recruiting.two47 import Two47Crawler

# Add to argparse
parser.add_argument(
    "--crawl-247",
    action="store_true",
    help="Crawl 247Sports for recruiting data",
)
parser.add_argument(
    "--link",
    action="store_true",
    help="Run entity linking on processed reports",
)
parser.add_argument(
    "--teams",
    nargs="+",
    default=["texas"],
    help="Teams to crawl (default: texas)",
)
parser.add_argument(
    "--years",
    nargs="+",
    type=int,
    default=[2025],
    help="Years to crawl (default: 2025)",
)

# Add to main() after process block
if args.crawl_247 or args.all:
    logger.info("Crawling 247Sports...")
    crawler = Two47Crawler(teams=args.teams, years=args.years)
    result = crawler.crawl()
    logger.info(f"247 crawl complete: {result.records_new} new records")

if args.link or args.all:
    logger.info("Running entity linking...")
    result = run_entity_linking()
    logger.info(f"Entity linking complete: {result['players_linked']} players linked")
```

**Step 3: Test the full pipeline**

```bash
# Run full pipeline with 247 crawl
python scripts/run_pipeline.py --crawl-247 --teams texas --years 2025

# Process new reports
python scripts/run_pipeline.py --process

# Link entities
python scripts/run_pipeline.py --link
```

Expected: Pipeline runs successfully, reports crawled, processed, and linked.

**Step 4: Commit**

```bash
git add src/processing/entity_linking.py scripts/run_pipeline.py
git commit -m "feat: add entity linking pipeline connecting reports to players"
```

---

## Task 7: Verify End-to-End and Update Documentation

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/README.md`

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass.

**Step 2: Verify data flow**

```sql
-- Check scouting players were created
SELECT COUNT(*), team FROM scouting.players GROUP BY team;

-- Check reports have player links
SELECT COUNT(*) as reports_with_players
FROM scouting.reports
WHERE player_ids IS NOT NULL AND array_length(player_ids, 1) > 0;

-- View a linked player
SELECT p.name, p.team, p.position, p.roster_player_id, p.recruit_id
FROM scouting.players p
LIMIT 5;
```

**Step 3: Update README**

Add to the Usage section:

```markdown
## Usage

```bash
# Seed test data for development
python scripts/run_pipeline.py --seed

# Crawl 247Sports recruiting data
python scripts/run_pipeline.py --crawl-247 --teams texas ohio-state --years 2025

# Process reports through Claude summarization
python scripts/run_pipeline.py --process

# Link entities (connect reports to player profiles)
python scripts/run_pipeline.py --link

# Run full pipeline
python scripts/run_pipeline.py --all --teams texas --years 2025
```

## Phase 2 Status

- [x] 247Sports commits crawler
- [x] Player entity extraction (regex + Claude)
- [x] Fuzzy name matching against roster/recruits
- [x] Scouting player profile creation
- [x] Report-to-player linking
```

**Step 4: Final commit**

```bash
git add README.md
git commit -m "docs: update README with phase 2 features"
```

---

## Success Criteria Checklist

- [ ] 247Sports crawler fetches commits data
- [ ] Player names extracted from report text
- [ ] Names matched against `core.roster` with fuzzy matching
- [ ] `scouting.players` records created with `roster_player_id` links
- [ ] Reports linked to players via `player_ids` array
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Full pipeline runs end-to-end
