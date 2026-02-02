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


class TrendData(BaseModel):
    """Player trend analysis."""

    player_id: int
    name: str | None = None
    team: str | None = None
    position: str | None = None
    direction: str
    slope: float
    grade_change: float
    data_points: int
    period_days: int


class ComparisonResult(BaseModel):
    """Player comparison result."""

    player1: dict
    player2: dict
    trait_comparison: list[dict]
    grade_comparison: dict
    pff_comparison: dict | None
    advantages: dict


class WatchList(BaseModel):
    """Watch list."""

    id: int
    name: str
    description: str | None
    player_ids: list[int]
    created_at: datetime
    updated_at: datetime


class WatchListCreate(BaseModel):
    """Watch list creation request."""

    name: str
    description: str | None = None


class DraftPlayerResponse(BaseModel):
    """Draft board player."""

    player_id: int
    name: str
    position: str
    team: str
    class_year: int | None
    draft_score: float
    projection: str
    composite_grade: int | None
    pff_grade: float | None
    trend_direction: str


class AlertCreate(BaseModel):
    """Alert creation request."""

    name: str
    alert_type: str  # grade_change, new_report, status_change, trend_change, portal_entry
    player_id: int | None = None
    team: str | None = None
    threshold: dict | None = None


class Alert(BaseModel):
    """Alert rule."""

    id: int
    user_id: str
    name: str
    alert_type: str
    player_id: int | None
    team: str | None
    threshold: dict | None
    is_active: bool
    created_at: datetime
    last_checked_at: datetime | None


class AlertHistoryEntry(BaseModel):
    """Fired alert record."""

    id: int
    alert_id: int
    alert_name: str
    alert_type: str
    fired_at: datetime
    trigger_data: dict
    message: str
    is_read: bool
