# src/api/main.py
"""FastAPI application for CFB Scout API."""

from fastapi import FastAPI, HTTPException, Query
from dotenv import load_dotenv

load_dotenv()

from ..storage.db import (  # noqa: E402
    get_connection,
    get_scouting_player,
    get_player_timeline,
    create_watch_list,
    get_watch_lists,
    get_watch_list,
    add_to_watch_list,
    remove_from_watch_list,
    delete_watch_list,
    create_alert,
    get_user_alerts,
    get_alert,
    deactivate_alert,
    delete_alert,
    get_unread_alerts,
    mark_alert_read,
    get_active_portal_players,
    get_player_transfer_history,
    get_team_transfer_activity,
)
from ..processing.transfer_portal import (  # noqa: E402
    predict_destination,
    analyze_team_portal_impact,
    generate_portal_snapshot,
)
from ..processing.aggregation import get_player_reports  # noqa: E402
from ..processing.trends import get_rising_stocks, get_falling_stocks, analyze_player_trend  # noqa: E402
from ..processing.comparison import compare_players, find_similar_players  # noqa: E402
from ..processing.draft import build_draft_board, get_position_rankings  # noqa: E402
from .models import (  # noqa: E402
    PlayerSummary,
    PlayerDetail,
    PlayerWithTimeline,
    TimelineSnapshot,
    TeamSummary,
    TrendData,
    ComparisonResult,
    WatchList,
    WatchListCreate,
    DraftPlayerResponse,
    AlertCreate,
    Alert,
    AlertHistoryEntry,
    TransferEvent,
    PortalPlayer,
    DestinationPrediction,
    TeamTransferActivity,
    PortalImpact,
)

app = FastAPI(
    title="CFB Scout API",
    description="College Football Scouting Intelligence API",
    version="0.3.0",
)


@app.get("/")
def root():
    """API root - health check."""
    return {"status": "ok", "version": "0.3.0"}


@app.get("/players", response_model=list[PlayerSummary])
def list_players(
    team: str | None = None,
    position: str | None = None,
    min_grade: int | None = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List players with optional filters."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        query = """
            SELECT id, name, team, position, class_year,
                   composite_grade, current_status
            FROM scouting.players
            WHERE 1=1
        """
        params = []

        if team:
            query += " AND LOWER(team) = LOWER(%s)"
            params.append(team)

        if position:
            query += " AND UPPER(position) = UPPER(%s)"
            params.append(position)

        if min_grade is not None:
            query += " AND composite_grade >= %s"
            params.append(min_grade)

        query += " ORDER BY composite_grade DESC NULLS LAST LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        return [PlayerSummary(**row) for row in rows]

    finally:
        cur.close()
        conn.close()


@app.get("/players/{player_id}", response_model=PlayerWithTimeline)
def get_player(player_id: int):
    """Get player detail with timeline."""
    conn = get_connection()

    try:
        player = get_scouting_player(conn, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        timeline = get_player_timeline(conn, player_id)
        reports = get_player_reports(player_id)

        return PlayerWithTimeline(
            player=PlayerDetail(**player),
            timeline=[TimelineSnapshot(**t) for t in timeline],
            report_count=len(reports),
        )

    finally:
        conn.close()


@app.get("/teams", response_model=list[TeamSummary])
def list_teams(limit: int = Query(25, ge=1, le=100)):
    """List teams with player stats."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT team,
                   COUNT(*) as player_count,
                   AVG(composite_grade) as avg_grade
            FROM scouting.players
            WHERE team IS NOT NULL
            GROUP BY team
            ORDER BY avg_grade DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )

        teams = []
        for row in cur.fetchall():
            team_name, player_count, avg_grade = row

            # Get top 3 players for this team
            cur.execute(
                """
                SELECT id, name, team, position, class_year,
                       composite_grade, current_status
                FROM scouting.players
                WHERE team = %s
                ORDER BY composite_grade DESC NULLS LAST
                LIMIT 3
                """,
                (team_name,),
            )
            columns = [desc[0] for desc in cur.description]
            top_players = [PlayerSummary(**dict(zip(columns, p))) for p in cur.fetchall()]

            teams.append(
                TeamSummary(
                    team=team_name,
                    player_count=player_count,
                    avg_grade=round(float(avg_grade), 1) if avg_grade else None,
                    top_players=top_players,
                )
            )

        return teams

    finally:
        cur.close()
        conn.close()


@app.get("/teams/{team_name}/players", response_model=list[PlayerSummary])
def get_team_players(team_name: str):
    """Get all players for a team."""
    return list_players(team=team_name, limit=100)


# Trends endpoints
@app.get("/trends/rising", response_model=list[TrendData])
def get_rising(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get players with rising trends."""
    return get_rising_stocks(limit=limit, days=days)


@app.get("/trends/falling", response_model=list[TrendData])
def get_falling(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get players with falling trends."""
    return get_falling_stocks(limit=limit, days=days)


@app.get("/players/{player_id}/trend", response_model=TrendData)
def get_player_trend(player_id: int, days: int = Query(90, ge=7, le=365)):
    """Get trend analysis for a specific player."""
    trend = analyze_player_trend(player_id, days=days)
    return TrendData(
        player_id=player_id,
        direction=trend.direction.value,
        slope=trend.slope,
        grade_change=trend.grade_change,
        data_points=trend.data_points,
        period_days=trend.period_days,
    )


# Comparison endpoints
@app.get("/compare/{player1_id}/{player2_id}", response_model=ComparisonResult)
def compare(player1_id: int, player2_id: int):
    """Compare two players head-to-head."""
    result = compare_players(player1_id, player2_id)
    return ComparisonResult(
        player1=result.player1,
        player2=result.player2,
        trait_comparison=result.trait_comparison,
        grade_comparison=result.grade_comparison,
        pff_comparison=result.pff_comparison,
        advantages=result.advantages,
    )


@app.get("/players/{player_id}/similar", response_model=list[dict])
def get_similar(player_id: int, limit: int = Query(5, ge=1, le=20)):
    """Find similar players based on trait profile."""
    return find_similar_players(player_id, limit=limit)


# Watch list endpoints
@app.get("/watchlists", response_model=list[WatchList])
def list_watchlists(user_id: str = Query(...)):
    """Get user's watch lists."""
    conn = get_connection()
    try:
        lists = get_watch_lists(conn, user_id)
        return [WatchList(**wl) for wl in lists]
    finally:
        conn.close()


@app.post("/watchlists", response_model=WatchList)
def create_watchlist(user_id: str = Query(...), data: WatchListCreate = ...):
    """Create a new watch list."""
    conn = get_connection()
    try:
        list_id = create_watch_list(conn, user_id, data.name, data.description)
        wl = get_watch_list(conn, list_id)
        return WatchList(**wl)
    finally:
        conn.close()


@app.post("/watchlists/{list_id}/players/{player_id}")
def add_player_to_watchlist(list_id: int, player_id: int):
    """Add a player to a watch list."""
    conn = get_connection()
    try:
        add_to_watch_list(conn, list_id, player_id)
        return {"status": "added"}
    finally:
        conn.close()


@app.delete("/watchlists/{list_id}/players/{player_id}")
def remove_player_from_watchlist(list_id: int, player_id: int):
    """Remove a player from a watch list."""
    conn = get_connection()
    try:
        remove_from_watch_list(conn, list_id, player_id)
        return {"status": "removed"}
    finally:
        conn.close()


@app.delete("/watchlists/{list_id}")
def delete_watchlist_endpoint(list_id: int):
    """Delete a watch list."""
    conn = get_connection()
    try:
        delete_watch_list(conn, list_id)
        return {"status": "deleted"}
    finally:
        conn.close()


# Draft board endpoints
@app.get("/draft/board", response_model=list[DraftPlayerResponse])
def get_draft_board(
    class_year: int | None = None,
    position: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get draft board rankings."""
    players = build_draft_board(class_year=class_year, position=position, limit=limit)
    return [
        DraftPlayerResponse(
            player_id=p.player_id,
            name=p.name,
            position=p.position,
            team=p.team,
            class_year=p.class_year,
            draft_score=p.draft_score,
            projection=p.projection.value,
            composite_grade=p.composite_grade,
            pff_grade=p.pff_grade,
            trend_direction=p.trend_direction,
        )
        for p in players
    ]


@app.get("/draft/position/{position}", response_model=list[DraftPlayerResponse])
def get_position_draft_rankings(
    position: str,
    limit: int = Query(25, ge=1, le=100),
):
    """Get draft rankings by position."""
    players = get_position_rankings(position, limit=limit)
    return [
        DraftPlayerResponse(
            player_id=p.player_id,
            name=p.name,
            position=p.position,
            team=p.team,
            class_year=p.class_year,
            draft_score=p.draft_score,
            projection=p.projection.value,
            composite_grade=p.composite_grade,
            pff_grade=p.pff_grade,
            trend_direction=p.trend_direction,
        )
        for p in players
    ]


# Alert endpoints
@app.get("/alerts", response_model=list[Alert])
def list_alerts(user_id: str = Query(...), active_only: bool = Query(True)):
    """Get user's alerts."""
    conn = get_connection()
    try:
        alerts = get_user_alerts(conn, user_id, active_only=active_only)
        return [Alert(**a) for a in alerts]
    finally:
        conn.close()


@app.post("/alerts", response_model=Alert)
def create_alert_endpoint(user_id: str = Query(...), data: AlertCreate = ...):
    """Create a new alert."""
    conn = get_connection()
    try:
        alert_id = create_alert(
            conn,
            user_id=user_id,
            name=data.name,
            alert_type=data.alert_type,
            player_id=data.player_id,
            team=data.team,
            threshold=data.threshold,
        )
        alert = get_alert(conn, alert_id)
        return Alert(**alert)
    finally:
        conn.close()


@app.delete("/alerts/{alert_id}")
def delete_alert_endpoint(alert_id: int):
    """Delete an alert."""
    conn = get_connection()
    try:
        delete_alert(conn, alert_id)
        return {"status": "deleted"}
    finally:
        conn.close()


@app.post("/alerts/{alert_id}/deactivate")
def deactivate_alert_endpoint(alert_id: int):
    """Deactivate an alert without deleting."""
    conn = get_connection()
    try:
        deactivate_alert(conn, alert_id)
        return {"status": "deactivated"}
    finally:
        conn.close()


@app.get("/alerts/history", response_model=list[AlertHistoryEntry])
def get_alert_history(user_id: str = Query(...), unread_only: bool = Query(True)):
    """Get fired alerts for a user."""
    conn = get_connection()
    try:
        if unread_only:
            history = get_unread_alerts(conn, user_id)
        else:
            history = get_unread_alerts(conn, user_id)  # For now, just unread
        return [AlertHistoryEntry(**h) for h in history]
    finally:
        conn.close()


@app.post("/alerts/history/{history_id}/read")
def mark_alert_read_endpoint(history_id: int):
    """Mark an alert as read."""
    conn = get_connection()
    try:
        mark_alert_read(conn, history_id)
        return {"status": "read"}
    finally:
        conn.close()


# Transfer Portal endpoints
@app.get("/transfer-portal/active", response_model=list[PortalPlayer])
def get_portal_players(
    position: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get players currently in the transfer portal."""
    conn = get_connection()
    try:
        players = get_active_portal_players(conn, position=position, limit=limit)
        return [PortalPlayer(**p) for p in players]
    finally:
        conn.close()


@app.get("/transfer-portal/player/{player_id}", response_model=list[TransferEvent])
def get_player_transfers(player_id: int):
    """Get transfer history for a player."""
    conn = get_connection()
    try:
        history = get_player_transfer_history(conn, player_id)
        return [TransferEvent(**h) for h in history]
    finally:
        conn.close()


@app.get("/transfer-portal/player/{player_id}/predict", response_model=list[DestinationPrediction])
def predict_player_destination(player_id: int):
    """Predict likely destinations for a player in the portal."""
    conn = get_connection()
    try:
        player = get_scouting_player(conn, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        predictions = predict_destination(
            position=player.get("position") or "Unknown",
            from_team=player.get("team") or "Unknown",
            composite_grade=player.get("composite_grade"),
            class_year=player.get("class_year"),
        )
        return [DestinationPrediction(**p) for p in predictions]
    finally:
        conn.close()


@app.get("/teams/{team_name}/transfers", response_model=TeamTransferActivity)
def get_team_transfers(team_name: str):
    """Get transfer activity for a team."""
    conn = get_connection()
    try:
        activity = get_team_transfer_activity(conn, team_name)
        return TeamTransferActivity(**activity)
    finally:
        conn.close()


@app.get("/teams/{team_name}/portal-impact", response_model=PortalImpact)
def get_team_portal_impact(team_name: str):
    """Get portal impact analysis for a team."""
    impact = analyze_team_portal_impact(team_name)
    return PortalImpact(**impact)


@app.post("/transfer-portal/snapshot")
def create_portal_snapshot():
    """Generate a portal snapshot (admin)."""
    snapshot = generate_portal_snapshot()
    return snapshot
