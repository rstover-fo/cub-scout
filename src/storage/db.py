"""Database connection and operations for CFB Scout."""

import os
from contextlib import contextmanager
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
