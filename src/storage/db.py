"""Database connection and operations for CFB Scout."""

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import psycopg
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None

MIN_POOL_CONNECTIONS = 2
MAX_POOL_CONNECTIONS = 10


async def init_pool(
    min_conn: int = MIN_POOL_CONNECTIONS,
    max_conn: int = MAX_POOL_CONNECTIONS,
) -> None:
    """Initialize the async connection pool. Safe to call multiple times."""
    global _pool
    if _pool is not None:
        return
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    _pool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_conn,
        max_size=max_conn,
        open=False,
    )
    await _pool.open()
    logger.info("Async connection pool initialized (min=%d, max=%d)", min_conn, max_conn)


async def close_pool() -> None:
    """Close all connections in the pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Async connection pool closed")


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    """Async context manager that yields a connection from the pool.

    Lazily initializes the pool on first call.
    """
    global _pool
    if _pool is None:
        await init_pool()
    async with _pool.connection() as conn:
        yield conn


# ---------------------------------------------------------------------------
# Data functions
# ---------------------------------------------------------------------------


async def insert_report(
    conn: psycopg.AsyncConnection,
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
    await cur.execute(
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
    row = await cur.fetchone()
    report_id = row[0]
    await conn.commit()
    return report_id


async def get_unprocessed_reports(conn: psycopg.AsyncConnection, limit: int = 100) -> list[dict]:
    """Get reports that haven't been processed yet."""
    cur = conn.cursor()
    await cur.execute(
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
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def mark_report_processed(
    conn: psycopg.AsyncConnection,
    report_id: int,
    summary: str | None = None,
    sentiment_score: float | None = None,
    player_ids: list[int] | None = None,
    team_ids: list[str] | None = None,
) -> None:
    """Mark a report as processed with optional extracted data."""
    cur = conn.cursor()
    await cur.execute(
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
    await conn.commit()


async def upsert_scouting_player(
    conn: psycopg.AsyncConnection,
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
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.players
            (name, team, position, class_year, current_status,
             roster_player_id, recruit_id, composite_grade, traits,
             draft_projection, comps, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (name, team, class_year) DO UPDATE SET
            position = COALESCE(EXCLUDED.position, scouting.players.position),
            current_status = EXCLUDED.current_status,
            roster_player_id = COALESCE(
                EXCLUDED.roster_player_id, scouting.players.roster_player_id),
            recruit_id = COALESCE(EXCLUDED.recruit_id, scouting.players.recruit_id),
            composite_grade = COALESCE(EXCLUDED.composite_grade, scouting.players.composite_grade),
            traits = COALESCE(EXCLUDED.traits, scouting.players.traits),
            draft_projection = COALESCE(
                EXCLUDED.draft_projection, scouting.players.draft_projection),
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
    row = await cur.fetchone()
    player_id = row[0]
    await conn.commit()
    return player_id


async def get_scouting_player(conn: psycopg.AsyncConnection, player_id: int) -> dict | None:
    """Get a scouting player by ID."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, name, team, position, class_year, current_status,
               roster_player_id, recruit_id, composite_grade, traits,
               draft_projection, comps, last_updated
        FROM scouting.players
        WHERE id = %s
        """,
        (player_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None

    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


async def link_report_to_player(
    conn: psycopg.AsyncConnection,
    report_id: int,
    player_id: int,
) -> None:
    """Link a report to a scouting player by adding to player_ids array."""
    cur = conn.cursor()
    await cur.execute(
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
    await conn.commit()


async def insert_timeline_snapshot(
    conn: psycopg.AsyncConnection,
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
    cur = conn.cursor()
    await cur.execute(
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
    row = await cur.fetchone()
    snapshot_id = row[0]
    await conn.commit()
    return snapshot_id


async def get_player_timeline(
    conn: psycopg.AsyncConnection,
    player_id: int,
    limit: int = 30,
) -> list[dict]:
    """Get timeline snapshots for a player, newest first."""
    cur = conn.cursor()
    await cur.execute(
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
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def upsert_pff_grade(
    conn: psycopg.AsyncConnection,
    player_id: int,
    pff_player_id: str,
    season: int,
    overall_grade: float,
    position_grades: dict | None = None,
    snaps: int = 0,
    week: int | None = None,
) -> int:
    """Upsert a PFF grade for a player."""
    cur = conn.cursor()
    await cur.execute(
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
    row = await cur.fetchone()
    grade_id = row[0]
    await conn.commit()
    return grade_id


async def get_player_pff_grades(
    conn: psycopg.AsyncConnection,
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

    await cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def create_watch_list(
    conn: psycopg.AsyncConnection,
    user_id: str,
    name: str,
    description: str | None = None,
) -> int:
    """Create a new watch list."""
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.watch_lists (user_id, name, description)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (user_id, name, description),
    )
    row = await cur.fetchone()
    list_id = row[0]
    await conn.commit()
    return list_id


async def get_watch_lists(
    conn: psycopg.AsyncConnection,
    user_id: str,
) -> list[dict]:
    """Get all watch lists for a user."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, name, description, player_ids, created_at, updated_at
        FROM scouting.watch_lists
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def get_watch_list(
    conn: psycopg.AsyncConnection,
    list_id: int,
) -> dict | None:
    """Get a specific watch list."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, user_id, name, description, player_ids, created_at, updated_at
        FROM scouting.watch_lists
        WHERE id = %s
        """,
        (list_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


async def add_to_watch_list(
    conn: psycopg.AsyncConnection,
    list_id: int,
    player_id: int,
) -> None:
    """Add a player to a watch list."""
    cur = conn.cursor()
    await cur.execute(
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
    await conn.commit()


async def remove_from_watch_list(
    conn: psycopg.AsyncConnection,
    list_id: int,
    player_id: int,
) -> None:
    """Remove a player from a watch list."""
    cur = conn.cursor()
    await cur.execute(
        """
        UPDATE scouting.watch_lists
        SET player_ids = array_remove(player_ids, %s),
            updated_at = NOW()
        WHERE id = %s
        """,
        (player_id, list_id),
    )
    await conn.commit()


async def delete_watch_list(
    conn: psycopg.AsyncConnection,
    list_id: int,
) -> None:
    """Delete a watch list."""
    cur = conn.cursor()
    await cur.execute("DELETE FROM scouting.watch_lists WHERE id = %s", (list_id,))
    await conn.commit()


# Alert functions


async def create_alert(
    conn: psycopg.AsyncConnection,
    user_id: str,
    name: str,
    alert_type: str,
    player_id: int | None = None,
    team: str | None = None,
    threshold: dict | None = None,
) -> int:
    """Create a new alert rule."""
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.alerts (user_id, name, alert_type, player_id, team, threshold)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, name, alert_type, player_id, team, json.dumps(threshold) if threshold else None),
    )
    row = await cur.fetchone()
    alert_id = row[0]
    await conn.commit()
    return alert_id


async def get_user_alerts(
    conn: psycopg.AsyncConnection,
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

    await cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def get_alert(conn: psycopg.AsyncConnection, alert_id: int) -> dict | None:
    """Get a specific alert."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, user_id, name, alert_type, player_id, team, threshold,
               is_active, created_at, last_checked_at
        FROM scouting.alerts
        WHERE id = %s
        """,
        (alert_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


async def update_alert_checked(conn: psycopg.AsyncConnection, alert_id: int) -> None:
    """Update last_checked_at timestamp."""
    cur = conn.cursor()
    await cur.execute(
        "UPDATE scouting.alerts SET last_checked_at = NOW() WHERE id = %s",
        (alert_id,),
    )
    await conn.commit()


async def deactivate_alert(conn: psycopg.AsyncConnection, alert_id: int) -> None:
    """Deactivate an alert."""
    cur = conn.cursor()
    await cur.execute(
        "UPDATE scouting.alerts SET is_active = FALSE WHERE id = %s",
        (alert_id,),
    )
    await conn.commit()


async def delete_alert(conn: psycopg.AsyncConnection, alert_id: int) -> None:
    """Delete an alert and its history."""
    cur = conn.cursor()
    await cur.execute("DELETE FROM scouting.alerts WHERE id = %s", (alert_id,))
    await conn.commit()


async def fire_alert(
    conn: psycopg.AsyncConnection,
    alert_id: int,
    trigger_data: dict,
    message: str,
) -> int:
    """Record a fired alert."""
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.alert_history (alert_id, trigger_data, message)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (alert_id, json.dumps(trigger_data), message),
    )
    row = await cur.fetchone()
    history_id = row[0]
    await conn.commit()
    return history_id


async def get_unread_alerts(conn: psycopg.AsyncConnection, user_id: str) -> list[dict]:
    """Get unread alert history for a user."""
    cur = conn.cursor()
    await cur.execute(
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
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def mark_alert_read(conn: psycopg.AsyncConnection, history_id: int) -> None:
    """Mark an alert history entry as read."""
    cur = conn.cursor()
    await cur.execute(
        "UPDATE scouting.alert_history SET is_read = TRUE WHERE id = %s",
        (history_id,),
    )
    await conn.commit()


# Transfer portal functions


async def insert_transfer_event(
    conn: psycopg.AsyncConnection,
    player_id: int,
    event_type: str,
    from_team: str | None = None,
    to_team: str | None = None,
    event_date: date | None = None,
    source_url: str | None = None,
    notes: str | None = None,
) -> int:
    """Insert a transfer portal event."""
    from datetime import date as date_type

    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.transfer_events
            (player_id, event_type, from_team, to_team, event_date, source_url, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_id, event_type, event_date) DO UPDATE SET
            to_team = EXCLUDED.to_team,
            source_url = EXCLUDED.source_url,
            notes = EXCLUDED.notes
        RETURNING id
        """,
        (
            player_id,
            event_type,
            from_team,
            to_team,
            event_date or date_type.today(),
            source_url,
            notes,
        ),
    )
    row = await cur.fetchone()
    event_id = row[0]
    await conn.commit()
    return event_id


async def get_player_transfer_history(
    conn: psycopg.AsyncConnection,
    player_id: int,
) -> list[dict]:
    """Get transfer history for a player."""
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, player_id, event_type, from_team, to_team,
               event_date, source_url, notes, created_at
        FROM scouting.transfer_events
        WHERE player_id = %s
        ORDER BY event_date DESC
        """,
        (player_id,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def get_active_portal_players(
    conn: psycopg.AsyncConnection,
    position: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get players currently in the transfer portal.

    Returns players who have 'entered' but not 'committed' or 'withdrawn'.
    """
    cur = conn.cursor()

    query = """
        SELECT DISTINCT ON (p.id)
            p.id, p.name, p.team, p.position, p.class_year, p.composite_grade,
            te.event_date as portal_entry_date, te.from_team
        FROM scouting.players p
        JOIN scouting.transfer_events te ON p.id = te.player_id
        WHERE te.event_type = 'entered'
        AND NOT EXISTS (
            SELECT 1 FROM scouting.transfer_events te2
            WHERE te2.player_id = p.id
            AND te2.event_type IN ('committed', 'withdrawn')
            AND te2.event_date > te.event_date
        )
    """
    params = []

    if position:
        query += " AND UPPER(p.position) = UPPER(%s)"
        params.append(position)

    query += " ORDER BY p.id, te.event_date DESC LIMIT %s"
    params.append(limit)

    await cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def get_team_transfer_activity(
    conn: psycopg.AsyncConnection,
    team: str,
) -> dict:
    """Get transfer activity for a team (incoming and outgoing)."""
    cur = conn.cursor()

    # Outgoing (players who left)
    await cur.execute(
        """
        SELECT p.id, p.name, p.position, te.event_date, te.to_team
        FROM scouting.transfer_events te
        JOIN scouting.players p ON te.player_id = p.id
        WHERE te.from_team = %s AND te.event_type = 'entered'
        ORDER BY te.event_date DESC
        """,
        (team,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    outgoing = [dict(zip(columns, row)) for row in rows]

    # Incoming (players who committed)
    await cur.execute(
        """
        SELECT p.id, p.name, p.position, te.event_date, te.from_team
        FROM scouting.transfer_events te
        JOIN scouting.players p ON te.player_id = p.id
        WHERE te.to_team = %s AND te.event_type = 'committed'
        ORDER BY te.event_date DESC
        """,
        (team,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    incoming = [dict(zip(columns, row)) for row in rows]

    return {
        "team": team,
        "outgoing": outgoing,
        "incoming": incoming,
        "net": len(incoming) - len(outgoing),
    }


async def insert_portal_snapshot(
    conn: psycopg.AsyncConnection,
    snapshot_date: date,
    total_in_portal: int,
    by_position: dict | None = None,
    by_conference: dict | None = None,
    notable_entries: list[str] | None = None,
) -> int:
    """Insert a daily portal snapshot."""
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.portal_snapshots
            (snapshot_date, total_in_portal, by_position, by_conference, notable_entries)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (snapshot_date) DO UPDATE SET
            total_in_portal = EXCLUDED.total_in_portal,
            by_position = EXCLUDED.by_position,
            by_conference = EXCLUDED.by_conference,
            notable_entries = EXCLUDED.notable_entries
        RETURNING id
        """,
        (
            snapshot_date,
            total_in_portal,
            json.dumps(by_position) if by_position else None,
            json.dumps(by_conference) if by_conference else None,
            notable_entries or [],
        ),
    )
    row = await cur.fetchone()
    snapshot_id = row[0]
    await conn.commit()
    return snapshot_id


# Embedding functions


async def upsert_player_embedding(
    conn: psycopg.AsyncConnection,
    roster_id: str,
    identity_text: str,
    embedding: list[float],
) -> int:
    """Upsert a player embedding.

    Args:
        conn: Database connection
        roster_id: The canonical roster ID
        identity_text: The text that was embedded
        embedding: The 1536-dim vector

    Returns:
        The embedding record ID
    """
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.player_embeddings (roster_id, identity_text, embedding)
        VALUES (%s, %s, %s)
        ON CONFLICT (roster_id) DO UPDATE SET
            identity_text = EXCLUDED.identity_text,
            embedding = EXCLUDED.embedding,
            created_at = NOW()
        RETURNING id
        """,
        (roster_id, identity_text, embedding),
    )
    row = await cur.fetchone()
    embedding_id = row[0]
    await conn.commit()
    return embedding_id


async def get_player_embedding(
    conn: psycopg.AsyncConnection,
    roster_id: str,
) -> dict | None:
    """Get embedding for a roster player.

    Args:
        conn: Database connection
        roster_id: The roster ID to look up

    Returns:
        Dict with id, roster_id, identity_text, created_at or None
    """
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, roster_id, identity_text, created_at
        FROM scouting.player_embeddings
        WHERE roster_id = %s
        """,
        (roster_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None

    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


async def find_similar_by_embedding(
    conn: psycopg.AsyncConnection,
    embedding: list[float],
    limit: int = 10,
    exclude_roster_id: str | None = None,
) -> list[dict]:
    """Find similar players by embedding vector.

    Uses cosine distance for similarity (lower = more similar).

    Args:
        conn: Database connection
        embedding: Query embedding vector
        limit: Max results to return
        exclude_roster_id: Optional roster_id to exclude from results

    Returns:
        List of dicts with roster_id, identity_text, similarity score
    """
    cur = conn.cursor()

    query = """
        SELECT
            roster_id,
            identity_text,
            1 - (embedding <=> %s::vector) as similarity
        FROM scouting.player_embeddings
        WHERE 1=1
    """
    params: list = [embedding]

    if exclude_roster_id:
        query += " AND roster_id != %s"
        params.append(exclude_roster_id)

    query += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params.extend([embedding, limit])

    await cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def insert_pending_link(
    conn: psycopg.AsyncConnection,
    source_name: str,
    source_team: str | None,
    source_context: dict | None,
    candidate_roster_id: str | None,
    match_score: float,
    match_method: str,
) -> int:
    """Insert a pending link for review.

    Args:
        conn: Database connection
        source_name: Name from source data
        source_team: Team from source data
        source_context: Additional context as JSON
        candidate_roster_id: Best matching roster ID
        match_score: Confidence score (0-1)
        match_method: 'vector', 'fuzzy', or 'deterministic'

    Returns:
        The pending link ID
    """
    cur = conn.cursor()
    await cur.execute(
        """
        INSERT INTO scouting.pending_links
            (source_name, source_team, source_context, candidate_roster_id,
             match_score, match_method)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            source_name,
            source_team,
            json.dumps(source_context) if source_context else None,
            candidate_roster_id,
            match_score,
            match_method,
        ),
    )
    row = await cur.fetchone()
    link_id = row[0]
    await conn.commit()
    return link_id


async def get_pending_links(
    conn: psycopg.AsyncConnection,
    status: str = "pending",
    limit: int = 100,
) -> list[dict]:
    """Get pending links for review.

    Args:
        conn: Database connection
        status: Filter by status ('pending', 'approved', 'rejected')
        limit: Max results

    Returns:
        List of pending link dicts
    """
    cur = conn.cursor()
    await cur.execute(
        """
        SELECT id, source_name, source_team, source_context,
               candidate_roster_id, match_score, match_method,
               status, created_at
        FROM scouting.pending_links
        WHERE status = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (status, limit),
    )
    columns = [desc[0] for desc in cur.description]
    rows = await cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def update_pending_link_status(
    conn: psycopg.AsyncConnection,
    link_id: int,
    status: str,
) -> None:
    """Update pending link status.

    Args:
        conn: Database connection
        link_id: The pending link ID
        status: New status ('approved' or 'rejected')
    """
    cur = conn.cursor()
    await cur.execute(
        """
        UPDATE scouting.pending_links
        SET status = %s, reviewed_at = NOW()
        WHERE id = %s
        """,
        (status, link_id),
    )
    await conn.commit()
