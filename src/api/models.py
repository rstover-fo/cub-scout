# src/api/models.py
"""Pydantic models for API responses."""

from datetime import date, datetime

from pydantic import BaseModel


class PlayerSummary(BaseModel):
    """Brief player info for lists."""

    id: int
    name: str
    team: str | None
    position: str | None
    class_year: int | None
    composite_grade: int | None
    current_status: str | None


class PlayerDetail(BaseModel):
    """Full player profile."""

    id: int
    name: str
    team: str | None
    position: str | None
    class_year: int | None
    current_status: str | None
    composite_grade: int | None
    traits: dict | None
    draft_projection: str | None
    comps: list[str] | None
    roster_player_id: int | None
    recruit_id: int | None
    last_updated: datetime | None


class TimelineSnapshot(BaseModel):
    """Player timeline entry."""

    id: int
    snapshot_date: date
    status: str | None
    sentiment_score: float | None
    grade_at_time: int | None
    traits_at_time: dict | None
    key_narratives: list[str] | None
    sources_count: int | None


class PlayerWithTimeline(BaseModel):
    """Player detail with timeline history."""

    player: PlayerDetail
    timeline: list[TimelineSnapshot]
    report_count: int


class TeamSummary(BaseModel):
    """Team scouting summary."""

    team: str
    player_count: int
    avg_grade: float | None
    top_players: list[PlayerSummary]
