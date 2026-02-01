# src/api/main.py
"""FastAPI application for CFB Scout API."""

from fastapi import FastAPI, HTTPException, Query
from dotenv import load_dotenv

load_dotenv()

from ..storage.db import get_connection, get_scouting_player, get_player_timeline
from ..processing.aggregation import get_player_reports
from .models import (
    PlayerSummary,
    PlayerDetail,
    PlayerWithTimeline,
    TimelineSnapshot,
    TeamSummary,
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
            top_players = [
                PlayerSummary(**dict(zip(columns, p)))
                for p in cur.fetchall()
            ]

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
