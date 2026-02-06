# src/api/main.py
"""FastAPI application for CFB Scout API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query

load_dotenv()

from ..processing.aggregation import get_player_reports  # noqa: E402
from ..processing.comparison import compare_players, find_similar_players  # noqa: E402
from ..processing.draft import build_draft_board, get_position_rankings  # noqa: E402
from ..processing.transfer_portal import (  # noqa: E402
    analyze_team_portal_impact,
    generate_portal_snapshot,
    predict_destination,
)
from ..processing.trends import (  # noqa: E402
    analyze_player_trend,
    get_falling_stocks,
    get_rising_stocks,
)
from ..storage.db import (  # noqa: E402
    add_to_watch_list,
    close_pool,
    create_alert,
    create_watch_list,
    deactivate_alert,
    delete_alert,
    delete_watch_list,
    get_active_portal_players,
    get_alert,
    get_all_alert_history,
    get_connection,
    get_player_timeline,
    get_player_transfer_history,
    get_scouting_player,
    get_team_transfer_activity,
    get_unread_alerts,
    get_user_alerts,
    get_watch_list,
    get_watch_lists,
    init_pool,
    mark_alert_read,
    remove_from_watch_list,
)
from .models import (  # noqa: E402
    Alert,
    AlertCreate,
    AlertHistoryEntry,
    ComparisonResult,
    DestinationPrediction,
    DraftPlayerResponse,
    PlayerDetail,
    PlayerSummary,
    PlayerWithTimeline,
    PortalImpact,
    PortalPlayer,
    TeamSummary,
    TeamTransferActivity,
    TimelineSnapshot,
    TransferEvent,
    TrendData,
    WatchList,
    WatchListCreate,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize connection pool on startup, close on shutdown."""
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="CFB Scout API",
    description="College Football Scouting Intelligence API",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """API root - health check."""
    return {"status": "ok", "version": "0.3.0"}


@app.get("/players", response_model=list[PlayerSummary])
async def list_players(
    team: str | None = None,
    position: str | None = None,
    min_grade: int | None = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List players with optional filters."""
    async with get_connection() as conn:
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

        cur = conn.cursor()
        await cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in await cur.fetchall()]
        await cur.close()

        return [PlayerSummary(**row) for row in rows]


@app.get("/players/{player_id}", response_model=PlayerWithTimeline)
async def get_player(player_id: int):
    """Get player detail with timeline."""
    async with get_connection() as conn:
        player = await get_scouting_player(conn, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        timeline = await get_player_timeline(conn, player_id)
        reports = await get_player_reports(player_id)

        return PlayerWithTimeline(
            player=PlayerDetail(**player),
            timeline=[TimelineSnapshot(**t) for t in timeline],
            report_count=len(reports),
        )


@app.get("/teams", response_model=list[TeamSummary])
async def list_teams(limit: int = Query(25, ge=1, le=100)):
    """List teams with player stats."""
    async with get_connection() as conn:
        cur = conn.cursor()

        await cur.execute(
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
        for row in await cur.fetchall():
            team_name, player_count, avg_grade = row

            # Get top 3 players for this team
            await cur.execute(
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
            top_players = [PlayerSummary(**dict(zip(columns, p))) for p in await cur.fetchall()]

            teams.append(
                TeamSummary(
                    team=team_name,
                    player_count=player_count,
                    avg_grade=round(float(avg_grade), 1) if avg_grade else None,
                    top_players=top_players,
                )
            )

        await cur.close()
        return teams


@app.get("/teams/{team_name}/players", response_model=list[PlayerSummary])
async def get_team_players(team_name: str):
    """Get all players for a team."""
    return await list_players(team=team_name, limit=100)


# Trends endpoints
@app.get("/trends/rising", response_model=list[TrendData])
async def get_rising(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get players with rising trends."""
    return await get_rising_stocks(limit=limit, days=days)


@app.get("/trends/falling", response_model=list[TrendData])
async def get_falling(
    days: int = Query(90, ge=7, le=365),
    limit: int = Query(20, ge=1, le=100),
):
    """Get players with falling trends."""
    return await get_falling_stocks(limit=limit, days=days)


@app.get("/players/{player_id}/trend", response_model=TrendData)
async def get_player_trend(player_id: int, days: int = Query(90, ge=7, le=365)):
    """Get trend analysis for a specific player."""
    trend = await analyze_player_trend(player_id, days=days)
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
async def compare(player1_id: int, player2_id: int):
    """Compare two players head-to-head."""
    result = await compare_players(player1_id, player2_id)
    return ComparisonResult(
        player1=result.player1,
        player2=result.player2,
        trait_comparison=result.trait_comparison,
        grade_comparison=result.grade_comparison,
        pff_comparison=result.pff_comparison,
        advantages=result.advantages,
    )


@app.get("/players/{player_id}/similar", response_model=list[dict])
async def get_similar(player_id: int, limit: int = Query(5, ge=1, le=20)):
    """Find similar players based on trait profile."""
    return await find_similar_players(player_id, limit=limit)


# Watch list endpoints
@app.get("/watchlists", response_model=list[WatchList])
async def list_watchlists(user_id: str = Query(...)):
    """Get user's watch lists."""
    async with get_connection() as conn:
        lists = await get_watch_lists(conn, user_id)
        return [WatchList(**wl) for wl in lists]


@app.post("/watchlists", response_model=WatchList)
async def create_watchlist(user_id: str = Query(...), data: WatchListCreate = ...):
    """Create a new watch list."""
    async with get_connection() as conn:
        list_id = await create_watch_list(conn, user_id, data.name, data.description)
        wl = await get_watch_list(conn, list_id)
        return WatchList(**wl)


@app.post("/watchlists/{list_id}/players/{player_id}")
async def add_player_to_watchlist(list_id: int, player_id: int):
    """Add a player to a watch list."""
    async with get_connection() as conn:
        await add_to_watch_list(conn, list_id, player_id)
        return {"status": "added"}


@app.delete("/watchlists/{list_id}/players/{player_id}")
async def remove_player_from_watchlist(list_id: int, player_id: int):
    """Remove a player from a watch list."""
    async with get_connection() as conn:
        await remove_from_watch_list(conn, list_id, player_id)
        return {"status": "removed"}


@app.delete("/watchlists/{list_id}")
async def delete_watchlist_endpoint(list_id: int):
    """Delete a watch list."""
    async with get_connection() as conn:
        await delete_watch_list(conn, list_id)
        return {"status": "deleted"}


# Draft board endpoints
@app.get("/draft/board", response_model=list[DraftPlayerResponse])
async def get_draft_board(
    class_year: int | None = None,
    position: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get draft board rankings."""
    players = await build_draft_board(class_year=class_year, position=position, limit=limit)
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
async def get_position_draft_rankings(
    position: str,
    limit: int = Query(25, ge=1, le=100),
):
    """Get draft rankings by position."""
    players = await get_position_rankings(position, limit=limit)
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
async def list_alerts(user_id: str = Query(...), active_only: bool = Query(True)):
    """Get user's alerts."""
    async with get_connection() as conn:
        alerts = await get_user_alerts(conn, user_id, active_only=active_only)
        return [Alert(**a) for a in alerts]


@app.post("/alerts", response_model=Alert)
async def create_alert_endpoint(user_id: str = Query(...), data: AlertCreate = ...):
    """Create a new alert."""
    async with get_connection() as conn:
        alert_id = await create_alert(
            conn,
            user_id=user_id,
            name=data.name,
            alert_type=data.alert_type,
            player_id=data.player_id,
            team=data.team,
            threshold=data.threshold,
        )
        alert = await get_alert(conn, alert_id)
        return Alert(**alert)


@app.delete("/alerts/{alert_id}")
async def delete_alert_endpoint(alert_id: int):
    """Delete an alert."""
    async with get_connection() as conn:
        await delete_alert(conn, alert_id)
        return {"status": "deleted"}


@app.post("/alerts/{alert_id}/deactivate")
async def deactivate_alert_endpoint(alert_id: int):
    """Deactivate an alert without deleting."""
    async with get_connection() as conn:
        await deactivate_alert(conn, alert_id)
        return {"status": "deactivated"}


@app.get("/alerts/history", response_model=list[AlertHistoryEntry])
async def get_alert_history(user_id: str = Query(...), unread_only: bool = Query(True)):
    """Get fired alerts for a user."""
    async with get_connection() as conn:
        if unread_only:
            history = await get_unread_alerts(conn, user_id)
        else:
            history = await get_all_alert_history(conn, user_id)
        return [AlertHistoryEntry(**h) for h in history]


@app.post("/alerts/history/{history_id}/read")
async def mark_alert_read_endpoint(history_id: int):
    """Mark an alert as read."""
    async with get_connection() as conn:
        await mark_alert_read(conn, history_id)
        return {"status": "read"}


# Transfer Portal endpoints
@app.get("/transfer-portal/active", response_model=list[PortalPlayer])
async def get_portal_players(
    position: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get players currently in the transfer portal."""
    async with get_connection() as conn:
        players = await get_active_portal_players(conn, position=position, limit=limit)
        return [PortalPlayer(**p) for p in players]


@app.get("/transfer-portal/player/{player_id}", response_model=list[TransferEvent])
async def get_player_transfers(player_id: int):
    """Get transfer history for a player."""
    async with get_connection() as conn:
        history = await get_player_transfer_history(conn, player_id)
        return [TransferEvent(**h) for h in history]


@app.get(
    "/transfer-portal/player/{player_id}/predict",
    response_model=list[DestinationPrediction],
)
async def predict_player_destination(player_id: int):
    """Predict likely destinations for a player in the portal."""
    async with get_connection() as conn:
        player = await get_scouting_player(conn, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        predictions = await predict_destination(
            position=player.get("position") or "Unknown",
            from_team=player.get("team") or "Unknown",
            composite_grade=player.get("composite_grade"),
            class_year=player.get("class_year"),
        )
        return [DestinationPrediction(**p) for p in predictions]


@app.get("/teams/{team_name}/transfers", response_model=TeamTransferActivity)
async def get_team_transfers(team_name: str):
    """Get transfer activity for a team."""
    async with get_connection() as conn:
        activity = await get_team_transfer_activity(conn, team_name)
        return TeamTransferActivity(**activity)


@app.get("/teams/{team_name}/portal-impact", response_model=PortalImpact)
async def get_team_portal_impact(team_name: str):
    """Get portal impact analysis for a team."""
    impact = await analyze_team_portal_impact(team_name)
    return PortalImpact(**impact)


@app.post("/transfer-portal/snapshot")
async def create_portal_snapshot():
    """Generate a portal snapshot (admin)."""
    snapshot = await generate_portal_snapshot()
    return snapshot
