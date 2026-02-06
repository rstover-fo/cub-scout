"""PFF API client for grade and snap data."""

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PFF_BASE_URL = "https://api.pff.com/v1"


class PFFPlayerGrade(BaseModel):
    """PFF player grade data."""

    player_id: str
    name: str
    position: str
    team: str
    overall_grade: float
    passing_grade: float | None = None
    rushing_grade: float | None = None
    receiving_grade: float | None = None
    blocking_grade: float | None = None
    defense_grade: float | None = None
    coverage_grade: float | None = None
    pass_rush_grade: float | None = None
    run_defense_grade: float | None = None
    snaps: int
    season: int


class PFFClient:
    """Client for PFF API."""

    def __init__(self, api_key: str | None = None):
        """Initialize PFF client.

        Args:
            api_key: PFF API key. Falls back to PFF_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("PFF_API_KEY")
        if not self.api_key:
            raise ValueError("PFF_API_KEY environment variable or api_key required")

        self.client = httpx.AsyncClient(
            base_url=PFF_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get_player_grades(
        self,
        team: str | None = None,
        position: str | None = None,
        season: int = 2025,
        limit: int = 100,
    ) -> list[PFFPlayerGrade]:
        """Get player grades from PFF API.

        Args:
            team: Filter by team name
            position: Filter by position (QB, RB, WR, etc.)
            season: Season year
            limit: Max results

        Returns:
            List of PFFPlayerGrade objects
        """
        params: dict[str, Any] = {
            "season": season,
            "limit": limit,
            "league": "ncaa",
        }
        if team:
            params["team"] = team
        if position:
            params["position"] = position

        try:
            response = await self.client.get("/grades/players", params=params)
            response.raise_for_status()
            data = response.json()

            return [
                PFFPlayerGrade(
                    player_id=str(p["id"]),
                    name=p["name"],
                    position=p["position"],
                    team=p["team"],
                    overall_grade=p["overall_grade"],
                    passing_grade=p.get("passing_grade"),
                    rushing_grade=p.get("rushing_grade"),
                    receiving_grade=p.get("receiving_grade"),
                    blocking_grade=p.get("blocking_grade"),
                    defense_grade=p.get("defense_grade"),
                    coverage_grade=p.get("coverage_grade"),
                    pass_rush_grade=p.get("pass_rush_grade"),
                    run_defense_grade=p.get("run_defense_grade"),
                    snaps=p["snaps"],
                    season=season,
                )
                for p in data.get("players", [])
            ]
        except httpx.HTTPError as e:
            logger.error(f"PFF API error: {e}")
            raise

    async def get_player_by_name(
        self,
        name: str,
        team: str | None = None,
        season: int = 2025,
    ) -> PFFPlayerGrade | None:
        """Look up a player by name.

        Args:
            name: Player name to search
            team: Optional team filter
            season: Season year

        Returns:
            PFFPlayerGrade if found, None otherwise
        """
        params: dict[str, Any] = {
            "search": name,
            "season": season,
            "league": "ncaa",
        }
        if team:
            params["team"] = team

        try:
            response = await self.client.get("/grades/players/search", params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get("players"):
                return None

            p = data["players"][0]
            return PFFPlayerGrade(
                player_id=str(p["id"]),
                name=p["name"],
                position=p["position"],
                team=p["team"],
                overall_grade=p["overall_grade"],
                passing_grade=p.get("passing_grade"),
                rushing_grade=p.get("rushing_grade"),
                receiving_grade=p.get("receiving_grade"),
                blocking_grade=p.get("blocking_grade"),
                defense_grade=p.get("defense_grade"),
                coverage_grade=p.get("coverage_grade"),
                pass_rush_grade=p.get("pass_rush_grade"),
                run_defense_grade=p.get("run_defense_grade"),
                snaps=p["snaps"],
                season=season,
            )
        except httpx.HTTPError as e:
            logger.error(f"PFF API error searching for {name}: {e}")
            return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
