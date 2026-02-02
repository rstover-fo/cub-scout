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


def create_watch_list(
    conn: connection,
    user_id: str,
    name: str,
    description: str | None = None,
) -> int:
    """Create a new watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.watch_lists (user_id, name, description)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (user_id, name, description),
    )
    list_id = cur.fetchone()[0]
    conn.commit()
    return list_id


def get_watch_lists(
    conn: connection,
    user_id: str,
) -> list[dict]:
    """Get all watch lists for a user."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, description, player_ids, created_at, updated_at
        FROM scouting.watch_lists
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_watch_list(
    conn: connection,
    list_id: int,
) -> dict | None:
    """Get a specific watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user_id, name, description, player_ids, created_at, updated_at
        FROM scouting.watch_lists
        WHERE id = %s
        """,
        (list_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def add_to_watch_list(
    conn: connection,
    list_id: int,
    player_id: int,
) -> None:
    """Add a player to a watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.watch_lists
        SET player_ids = array_append(
            COALESCE(player_ids, '{}'),
            %s
        ),
        updated_at = NOW()
        WHERE id = %s
        AND NOT (%s = ANY(COALESCE(player_ids, '{}')))
        """,
        (player_id, list_id, player_id),
    )
    conn.commit()


def remove_from_watch_list(
    conn: connection,
    list_id: int,
    player_id: int,
) -> None:
    """Remove a player from a watch list."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scouting.watch_lists
        SET player_ids = array_remove(player_ids, %s),
            updated_at = NOW()
        WHERE id = %s
        """,
        (player_id, list_id),
    )
    conn.commit()


def delete_watch_list(
    conn: connection,
    list_id: int,
) -> None:
    """Delete a watch list."""
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.watch_lists WHERE id = %s", (list_id,))
    conn.commit()


# Alert functions


def create_alert(
    conn: connection,
    user_id: str,
    name: str,
    alert_type: str,
    player_id: int | None = None,
    team: str | None = None,
    threshold: dict | None = None,
) -> int:
    """Create a new alert rule."""
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.alerts (user_id, name, alert_type, player_id, team, threshold)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, name, alert_type, player_id, team, json.dumps(threshold) if threshold else None),
    )
    alert_id = cur.fetchone()[0]
    conn.commit()
    return alert_id


def get_user_alerts(
    conn: connection,
    user_id: str,
    active_only: bool = True,
) -> list[dict]:
    """Get all alerts for a user."""
    cur = conn.cursor()

    query = """
        SELECT id, user_id, name, alert_type, player_id, team, threshold,
               is_active, created_at, last_checked_at
        FROM scouting.alerts
        WHERE user_id = %s
    """
    params = [user_id]

    if active_only:
        query += " AND is_active = TRUE"

    query += " ORDER BY created_at DESC"

    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_alert(conn: connection, alert_id: int) -> dict | None:
    """Get a specific alert."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user_id, name, alert_type, player_id, team, threshold,
               is_active, created_at, last_checked_at
        FROM scouting.alerts
        WHERE id = %s
        """,
        (alert_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def update_alert_checked(conn: connection, alert_id: int) -> None:
    """Update last_checked_at timestamp."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE scouting.alerts SET last_checked_at = NOW() WHERE id = %s",
        (alert_id,),
    )
    conn.commit()


def deactivate_alert(conn: connection, alert_id: int) -> None:
    """Deactivate an alert."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE scouting.alerts SET is_active = FALSE WHERE id = %s",
        (alert_id,),
    )
    conn.commit()


def delete_alert(conn: connection, alert_id: int) -> None:
    """Delete an alert and its history."""
    cur = conn.cursor()
    cur.execute("DELETE FROM scouting.alerts WHERE id = %s", (alert_id,))
    conn.commit()


def fire_alert(
    conn: connection,
    alert_id: int,
    trigger_data: dict,
    message: str,
) -> int:
    """Record a fired alert."""
    import json

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO scouting.alert_history (alert_id, trigger_data, message)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (alert_id, json.dumps(trigger_data), message),
    )
    history_id = cur.fetchone()[0]
    conn.commit()
    return history_id


def get_unread_alerts(conn: connection, user_id: str) -> list[dict]:
    """Get unread alert history for a user."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT h.id, h.alert_id, h.fired_at, h.trigger_data, h.message, h.is_read,
               a.name as alert_name, a.alert_type
        FROM scouting.alert_history h
        JOIN scouting.alerts a ON h.alert_id = a.id
        WHERE a.user_id = %s AND h.is_read = FALSE
        ORDER BY h.fired_at DESC
        """,
        (user_id,),
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def mark_alert_read(conn: connection, history_id: int) -> None:
    """Mark an alert history entry as read."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE scouting.alert_history SET is_read = TRUE WHERE id = %s",
        (history_id,),
    )
    conn.commit()
