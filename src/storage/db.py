"""Database connection and operations for CFB Scout."""

import os
from contextlib import contextmanager
from datetime import date
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection


def get_connection() -> connection:
    """Get a database connection."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)


@contextmanager
def get_db() -> Iterator[connection]:
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def insert_report(
    conn: connection,
    source_url: str,
    source_name: str,
    content_type: str,
    raw_text: str,
    player_ids: list[int] | None = None,
    team_ids: list[str] | None = None,
    published_at: str | None = None,
) -> int:
    """Insert a scouting report and return its ID.

    Uses ON CONFLICT to handle duplicates (same URL).
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.reports
            (source_url, source_name, content_type, raw_text, player_ids, team_ids, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_url) DO UPDATE SET
            raw_text = EXCLUDED.raw_text,
            crawled_at = NOW()
        RETURNING id
        """,
        (
            source_url,
            source_name,
            content_type,
            raw_text,
            player_ids or [],
            team_ids or [],
            published_at,
        ),
    )
    report_id = cur.fetchone()[0]
    conn.commit()
    return report_id


def get_unprocessed_reports(conn: connection, limit: int = 100) -> list[dict]:
    """Get reports that haven't been processed yet."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_url, source_name, content_type, raw_text, player_ids, team_ids
        FROM scouting.reports
        WHERE processed_at IS NULL
        ORDER BY crawled_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def mark_report_processed(
    conn: connection,
    report_id: int,
    summary: str | None = None,
    sentiment_score: float | None = None,
    player_ids: list[int] | None = None,
    team_ids: list[str] | None = None,
) -> None:
    """Mark a report as processed with optional extracted data."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.reports
        SET processed_at = NOW(),
            summary = COALESCE(%s, summary),
            sentiment_score = COALESCE(%s, sentiment_score),
            player_ids = COALESCE(%s, player_ids),
            team_ids = COALESCE(%s, team_ids)
        WHERE id = %s
        """,
        (summary, sentiment_score, player_ids, team_ids, report_id),
    )
    conn.commit()


def upsert_scouting_player(
    conn: connection,
    name: str,
    team: str,
    position: str | None = None,
    class_year: int | None = None,
    current_status: str = "active",
    roster_player_id: int | None = None,
    recruit_id: int | None = None,
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


def insert_timeline_snapshot(
    conn: connection,
    player_id: int,
    snapshot_date: date,
    status: str | None = None,
    sentiment_score: float | None = None,
    grade_at_time: int | None = None,
    traits_at_time: dict | None = None,
    key_narratives: list[str] | None = None,
    sources_count: int | None = None,
) -> int:
    """Insert a player timeline snapshot."""
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.player_timeline
            (player_id, snapshot_date, status, sentiment_score,
             grade_at_time, traits_at_time, key_narratives, sources_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            player_id,
            snapshot_date,
            status,
            sentiment_score,
            grade_at_time,
            json.dumps(traits_at_time) if traits_at_time else None,
            key_narratives or [],
            sources_count or 0,
        ),
    )
    snapshot_id = cur.fetchone()[0]
    conn.commit()
    return snapshot_id


def get_player_timeline(
    conn: connection,
    player_id: int,
    limit: int = 30,
) -> list[dict]:
    """Get timeline snapshots for a player, newest first."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, player_id, snapshot_date, status, sentiment_score,
               grade_at_time, traits_at_time, key_narratives, sources_count
        FROM scouting.player_timeline
        WHERE player_id = %s
        ORDER BY snapshot_date DESC
        LIMIT %s
        """,
        (player_id, limit),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def upsert_pff_grade(
    conn: connection,
    player_id: int,
    pff_player_id: str,
    season: int,
    overall_grade: float,
    position_grades: dict | None = None,
    snaps: int = 0,
    week: int | None = None,
) -> int:
    """Upsert a PFF grade for a player."""
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.pff_grades
            (player_id, pff_player_id, season, week, overall_grade, position_grades, snaps)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_id, season, week) DO UPDATE SET
            overall_grade = EXCLUDED.overall_grade,
            position_grades = EXCLUDED.position_grades,
            snaps = EXCLUDED.snaps,
            fetched_at = NOW()
        RETURNING id
        """,
        (
            player_id,
            pff_player_id,
            season,
            week,
            overall_grade,
            json.dumps(position_grades) if position_grades else None,
            snaps,
        ),
    )
    grade_id = cur.fetchone()[0]
    conn.commit()
    return grade_id


def get_player_pff_grades(
    conn: connection,
    player_id: int,
    season: int | None = None,
) -> list[dict]:
    """Get PFF grades for a player."""
    cur = conn.cursor()

    query = """
        SELECT id, player_id, pff_player_id, season, week,
               overall_grade, position_grades, snaps, fetched_at
        FROM scouting.pff_grades
        WHERE player_id = %s
    """
    params = [player_id]

    if season:
        query += " AND season = %s"
        params.append(season)

    query += " ORDER BY season DESC, week DESC NULLS FIRST"

    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]
