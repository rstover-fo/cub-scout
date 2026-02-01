# CFB Scout Agent Phase 5 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an Alert System for tracking watched players and a Transfer Portal Tracker for monitoring portal activity, destinations, and impact analysis.

**Architecture:** Alert System uses user-scoped alert rules with configurable triggers (grade change, new report, status update) and checks conditions during pipeline runs. Transfer Portal Tracker crawls portal sources, extracts transfer events, links to existing players, and provides destination predictions based on historical patterns. Both features integrate with existing timeline and trend analysis.

**Tech Stack:** Python 3.12, FastAPI, psycopg2, Claude for content analysis, existing processing pipeline

---

## Task 1: Add Alert System Schema

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/schema.sql`

**Step 1: Add alerts and alert_history tables to schema**

Add to end of schema.sql:

```sql
-- Alert rules for watched players
CREATE TABLE IF NOT EXISTS scouting.alerts (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('grade_change', 'new_report', 'status_change', 'trend_change', 'portal_entry')),
    player_id INT REFERENCES scouting.players(id) ON DELETE CASCADE,
    team TEXT,  -- NULL for player-specific, set for team-wide alerts
    threshold JSONB DEFAULT '{}',  -- type-specific config (e.g., {"min_change": 5})
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ,
    UNIQUE (user_id, name)
);

CREATE INDEX idx_alerts_user ON scouting.alerts (user_id);
CREATE INDEX idx_alerts_player ON scouting.alerts (player_id);
CREATE INDEX idx_alerts_active ON scouting.alerts (is_active) WHERE is_active = TRUE;

-- Fired alert history
CREATE TABLE IF NOT EXISTS scouting.alert_history (
    id SERIAL PRIMARY KEY,
    alert_id INT NOT NULL REFERENCES scouting.alerts(id) ON DELETE CASCADE,
    fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trigger_data JSONB NOT NULL,  -- What triggered it (old_grade, new_grade, report_id, etc.)
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_alert_history_alert ON scouting.alert_history (alert_id);
CREATE INDEX idx_alert_history_unread ON scouting.alert_history (is_read) WHERE is_read = FALSE;
```

**Step 2: Commit**

```bash
git add src/storage/schema.sql
git commit -m "feat: add alert system schema tables"
```

---

## Task 2: Apply Alert Schema Migration

**Files:**
- None (Supabase MCP)

**Step 1: Apply migration via Supabase MCP**

Use `mcp__supabase__apply_migration` with name `add_alert_system_tables` and the SQL from Task 1.

**Step 2: Verify tables exist**

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'scouting' AND table_name IN ('alerts', 'alert_history');
```

Expected: 2 rows returned.

---

## Task 3: Add Alert Database Functions

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_alerts.py`

**Step 1: Write failing test**

```python
# tests/test_alerts.py
"""Tests for alert functions."""

from src.storage.db import (
    get_connection,
    create_alert,
    get_user_alerts,
    fire_alert,
    get_unread_alerts,
)


def test_create_alert():
    """Test creating an alert."""
    conn = get_connection()

    try:
        alert_id = create_alert(
            conn,
            user_id="test-alert-user",
            name="Arch Manning Grade Alert",
            alert_type="grade_change",
            player_id=None,  # Will use player_id if exists
            threshold={"min_change": 5},
        )

        assert alert_id is not None
        assert alert_id > 0

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.alerts WHERE user_id = 'test-alert-user'")
        conn.commit()
        conn.close()


def test_get_user_alerts():
    """Test retrieving user's alerts."""
    conn = get_connection()

    try:
        create_alert(conn, "test-alert-user-2", "Alert 1", "grade_change")
        create_alert(conn, "test-alert-user-2", "Alert 2", "new_report")

        alerts = get_user_alerts(conn, "test-alert-user-2")

        assert len(alerts) == 2

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.alerts WHERE user_id = 'test-alert-user-2'")
        conn.commit()
        conn.close()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_alerts.py -v
```

Expected: FAIL with "ImportError: cannot import name 'create_alert'"

**Step 3: Add alert db functions to db.py**

```python
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
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_alerts.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/storage/db.py tests/test_alerts.py
git commit -m "feat: add alert database functions"
```

---

## Task 4: Create Alert Processing Module

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/alerting.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_alerting.py`

**Step 1: Write failing test**

```python
# tests/test_alerting.py
"""Tests for alert processing."""

from src.processing.alerting import (
    check_grade_change_alert,
    AlertCheckResult,
)


def test_check_grade_change_alert_triggers():
    """Test that grade change alert triggers when threshold exceeded."""
    result = check_grade_change_alert(
        old_grade=75,
        new_grade=82,
        threshold={"min_change": 5},
    )

    assert result.should_fire is True
    assert result.message is not None
    assert "increased" in result.message.lower()


def test_check_grade_change_alert_no_trigger():
    """Test that grade change alert doesn't trigger below threshold."""
    result = check_grade_change_alert(
        old_grade=75,
        new_grade=77,
        threshold={"min_change": 5},
    )

    assert result.should_fire is False


def test_check_grade_change_alert_decrease():
    """Test that grade decrease also triggers."""
    result = check_grade_change_alert(
        old_grade=80,
        new_grade=72,
        threshold={"min_change": 5},
    )

    assert result.should_fire is True
    assert "decreased" in result.message.lower()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_alerting.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write alerting module**

```python
# src/processing/alerting.py
"""Alert processing and condition checking."""

import logging
from dataclasses import dataclass
from datetime import datetime

from ..storage.db import (
    get_connection,
    get_user_alerts,
    get_scouting_player,
    get_player_timeline,
    fire_alert,
    update_alert_checked,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertCheckResult:
    """Result of checking an alert condition."""

    should_fire: bool
    message: str | None = None
    trigger_data: dict | None = None


def check_grade_change_alert(
    old_grade: int | None,
    new_grade: int | None,
    threshold: dict | None = None,
) -> AlertCheckResult:
    """Check if grade change exceeds threshold.

    Args:
        old_grade: Previous grade
        new_grade: Current grade
        threshold: Config with min_change key

    Returns:
        AlertCheckResult with should_fire and message
    """
    if old_grade is None or new_grade is None:
        return AlertCheckResult(should_fire=False)

    min_change = (threshold or {}).get("min_change", 5)
    change = new_grade - old_grade

    if abs(change) >= min_change:
        direction = "increased" if change > 0 else "decreased"
        return AlertCheckResult(
            should_fire=True,
            message=f"Grade {direction} by {abs(change)} points (from {old_grade} to {new_grade})",
            trigger_data={
                "old_grade": old_grade,
                "new_grade": new_grade,
                "change": change,
            },
        )

    return AlertCheckResult(should_fire=False)


def check_status_change_alert(
    old_status: str | None,
    new_status: str | None,
    threshold: dict | None = None,
) -> AlertCheckResult:
    """Check if player status changed.

    Args:
        old_status: Previous status
        new_status: Current status
        threshold: Optional config (can filter specific statuses)

    Returns:
        AlertCheckResult
    """
    if old_status == new_status:
        return AlertCheckResult(should_fire=False)

    if old_status is None:
        return AlertCheckResult(should_fire=False)

    watch_statuses = (threshold or {}).get("statuses", [])
    if watch_statuses and new_status not in watch_statuses:
        return AlertCheckResult(should_fire=False)

    return AlertCheckResult(
        should_fire=True,
        message=f"Status changed from '{old_status}' to '{new_status}'",
        trigger_data={
            "old_status": old_status,
            "new_status": new_status,
        },
    )


def check_new_report_alert(
    report_count_before: int,
    report_count_after: int,
    threshold: dict | None = None,
) -> AlertCheckResult:
    """Check if new reports were added.

    Args:
        report_count_before: Previous count
        report_count_after: Current count
        threshold: Optional config (min_reports to trigger)

    Returns:
        AlertCheckResult
    """
    min_reports = (threshold or {}).get("min_reports", 1)
    new_reports = report_count_after - report_count_before

    if new_reports >= min_reports:
        return AlertCheckResult(
            should_fire=True,
            message=f"{new_reports} new report(s) found",
            trigger_data={
                "new_reports": new_reports,
                "total_reports": report_count_after,
            },
        )

    return AlertCheckResult(should_fire=False)


def check_trend_change_alert(
    old_direction: str | None,
    new_direction: str,
    threshold: dict | None = None,
) -> AlertCheckResult:
    """Check if trend direction changed.

    Args:
        old_direction: Previous trend direction
        new_direction: Current trend direction
        threshold: Optional config

    Returns:
        AlertCheckResult
    """
    if old_direction == new_direction:
        return AlertCheckResult(should_fire=False)

    if old_direction is None:
        return AlertCheckResult(should_fire=False)

    # Only fire for significant changes
    significant_changes = [
        ("stable", "rising"),
        ("stable", "falling"),
        ("falling", "rising"),
        ("rising", "falling"),
    ]

    if (old_direction, new_direction) in significant_changes:
        return AlertCheckResult(
            should_fire=True,
            message=f"Trend changed from '{old_direction}' to '{new_direction}'",
            trigger_data={
                "old_direction": old_direction,
                "new_direction": new_direction,
            },
        )

    return AlertCheckResult(should_fire=False)


def process_alerts_for_player(player_id: int) -> list[dict]:
    """Check all alerts for a specific player.

    Args:
        player_id: Player to check alerts for

    Returns:
        List of fired alert details
    """
    conn = get_connection()
    cur = conn.cursor()
    fired = []

    try:
        # Get all active alerts for this player
        cur.execute(
            """
            SELECT a.id, a.user_id, a.name, a.alert_type, a.threshold, a.last_checked_at
            FROM scouting.alerts a
            WHERE a.player_id = %s AND a.is_active = TRUE
            """,
            (player_id,),
        )

        alerts = cur.fetchall()
        if not alerts:
            return []

        # Get player data
        player = get_scouting_player(conn, player_id)
        if not player:
            return []

        timeline = get_player_timeline(conn, player_id, limit=2)

        for alert_row in alerts:
            alert_id, user_id, name, alert_type, threshold, last_checked = alert_row

            result = AlertCheckResult(should_fire=False)

            if alert_type == "grade_change" and len(timeline) >= 2:
                result = check_grade_change_alert(
                    old_grade=timeline[1].get("grade_at_time"),
                    new_grade=timeline[0].get("grade_at_time"),
                    threshold=threshold,
                )

            elif alert_type == "status_change" and len(timeline) >= 2:
                result = check_status_change_alert(
                    old_status=timeline[1].get("status"),
                    new_status=timeline[0].get("status"),
                    threshold=threshold,
                )

            if result.should_fire:
                history_id = fire_alert(
                    conn,
                    alert_id,
                    result.trigger_data or {},
                    result.message or "",
                )
                fired.append({
                    "alert_id": alert_id,
                    "history_id": history_id,
                    "alert_name": name,
                    "message": result.message,
                    "player_id": player_id,
                    "player_name": player.get("name"),
                })

            update_alert_checked(conn, alert_id)

        return fired

    finally:
        cur.close()
        conn.close()


def run_alert_check() -> dict:
    """Run alert check for all active alerts.

    Returns:
        Summary of alerts processed and fired
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get distinct players with active alerts
        cur.execute(
            """
            SELECT DISTINCT player_id
            FROM scouting.alerts
            WHERE is_active = TRUE AND player_id IS NOT NULL
            """
        )

        player_ids = [row[0] for row in cur.fetchall()]

        total_fired = []
        for player_id in player_ids:
            fired = process_alerts_for_player(player_id)
            total_fired.extend(fired)

        return {
            "players_checked": len(player_ids),
            "alerts_fired": len(total_fired),
            "fired_details": total_fired,
            "timestamp": datetime.now().isoformat(),
        }

    finally:
        cur.close()
        conn.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_alerting.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/alerting.py tests/test_alerting.py
git commit -m "feat: add alert processing module"
```

---

## Task 5: Add Alert API Endpoints

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/api/models.py`
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/api/main.py`

**Step 1: Add new Pydantic models to models.py**

```python
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
```

**Step 2: Add alert endpoints to main.py**

Add imports:
```python
from ..storage.db import (
    # ... existing imports ...
    create_alert,
    get_user_alerts,
    get_alert,
    deactivate_alert,
    delete_alert,
    get_unread_alerts,
    mark_alert_read,
)
from .models import (
    # ... existing imports ...
    AlertCreate,
    Alert,
    AlertHistoryEntry,
)
```

Add endpoints:
```python
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
            # Get all history - need to add this function if needed
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
```

**Step 3: Commit**

```bash
git add src/api/models.py src/api/main.py
git commit -m "feat: add alert API endpoints"
```

---

## Task 6: Add Transfer Portal Schema

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/schema.sql`

**Step 1: Add transfer portal tables to schema**

Add to end of schema.sql:

```sql
-- Transfer portal events
CREATE TABLE IF NOT EXISTS scouting.transfer_events (
    id SERIAL PRIMARY KEY,
    player_id INT REFERENCES scouting.players(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('entered', 'committed', 'withdrawn')),
    from_team TEXT,
    to_team TEXT,  -- NULL if entered, set if committed
    event_date DATE NOT NULL,
    source_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, event_type, event_date)
);

CREATE INDEX idx_transfer_events_player ON scouting.transfer_events (player_id);
CREATE INDEX idx_transfer_events_date ON scouting.transfer_events (event_date DESC);
CREATE INDEX idx_transfer_events_type ON scouting.transfer_events (event_type);
CREATE INDEX idx_transfer_events_to_team ON scouting.transfer_events (to_team) WHERE to_team IS NOT NULL;

-- Portal activity tracking (for historical analysis)
CREATE TABLE IF NOT EXISTS scouting.portal_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    total_in_portal INT NOT NULL DEFAULT 0,
    by_position JSONB DEFAULT '{}',
    by_conference JSONB DEFAULT '{}',
    notable_entries TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date)
);

CREATE INDEX idx_portal_snapshots_date ON scouting.portal_snapshots (snapshot_date DESC);
```

**Step 2: Commit**

```bash
git add src/storage/schema.sql
git commit -m "feat: add transfer portal schema tables"
```

---

## Task 7: Apply Transfer Portal Schema Migration

**Files:**
- None (Supabase MCP)

**Step 1: Apply migration via Supabase MCP**

Use `mcp__supabase__apply_migration` with name `add_transfer_portal_tables` and the SQL from Task 6.

**Step 2: Verify tables exist**

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'scouting' AND table_name IN ('transfer_events', 'portal_snapshots');
```

Expected: 2 rows returned.

---

## Task 8: Add Transfer Portal Database Functions

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/storage/db.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_transfer_portal.py`

**Step 1: Write failing test**

```python
# tests/test_transfer_portal.py
"""Tests for transfer portal functions."""

from datetime import date

from src.storage.db import (
    get_connection,
    insert_transfer_event,
    get_player_transfer_history,
    get_active_portal_players,
)


def test_insert_transfer_event():
    """Test inserting a transfer event."""
    conn = get_connection()

    try:
        # First create a test player
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scouting.players (name, team, class_year)
            VALUES ('Test Transfer Player', 'Texas', 2025)
            RETURNING id
            """
        )
        player_id = cur.fetchone()[0]
        conn.commit()

        event_id = insert_transfer_event(
            conn,
            player_id=player_id,
            event_type="entered",
            from_team="Texas",
            event_date=date.today(),
        )

        assert event_id is not None
        assert event_id > 0

    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM scouting.players WHERE name = 'Test Transfer Player'")
        conn.commit()
        conn.close()


def test_get_active_portal_players():
    """Test getting players currently in portal."""
    conn = get_connection()

    try:
        players = get_active_portal_players(conn)
        assert isinstance(players, list)

    finally:
        conn.close()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_transfer_portal.py -v
```

Expected: FAIL with "ImportError: cannot import name 'insert_transfer_event'"

**Step 3: Add transfer portal db functions to db.py**

```python
def insert_transfer_event(
    conn: connection,
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
    cur.execute(
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
    event_id = cur.fetchone()[0]
    conn.commit()
    return event_id


def get_player_transfer_history(
    conn: connection,
    player_id: int,
) -> list[dict]:
    """Get transfer history for a player."""
    cur = conn.cursor()
    cur.execute(
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
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_active_portal_players(
    conn: connection,
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

    cur.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_team_transfer_activity(
    conn: connection,
    team: str,
) -> dict:
    """Get transfer activity for a team (incoming and outgoing)."""
    cur = conn.cursor()

    # Outgoing (players who left)
    cur.execute(
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
    outgoing = [dict(zip(columns, row)) for row in cur.fetchall()]

    # Incoming (players who committed)
    cur.execute(
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
    incoming = [dict(zip(columns, row)) for row in cur.fetchall()]

    return {
        "team": team,
        "outgoing": outgoing,
        "incoming": incoming,
        "net": len(incoming) - len(outgoing),
    }


def insert_portal_snapshot(
    conn: connection,
    snapshot_date: date,
    total_in_portal: int,
    by_position: dict | None = None,
    by_conference: dict | None = None,
    notable_entries: list[str] | None = None,
) -> int:
    """Insert a daily portal snapshot."""
    import json

    cur = conn.cursor()
    cur.execute(
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
    snapshot_id = cur.fetchone()[0]
    conn.commit()
    return snapshot_id
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_transfer_portal.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/storage/db.py tests/test_transfer_portal.py
git commit -m "feat: add transfer portal database functions"
```

---

## Task 9: Create Transfer Portal Processing Module

**Files:**
- Create: `/Users/robstover/Development/personal/cfb-scout/src/processing/transfer_portal.py`
- Create: `/Users/robstover/Development/personal/cfb-scout/tests/test_portal_processing.py`

**Step 1: Write failing test**

```python
# tests/test_portal_processing.py
"""Tests for transfer portal processing."""

from src.processing.transfer_portal import (
    extract_portal_mentions,
    predict_destination,
)


def test_extract_portal_mentions_finds_keywords():
    """Test that portal-related text is detected."""
    text = "Breaking: Arch Manning has entered the transfer portal from Texas"
    result = extract_portal_mentions(text)

    assert result["is_portal_related"] is True
    assert "entered" in result["event_type"]


def test_extract_portal_mentions_no_match():
    """Test text without portal mentions."""
    text = "Arch Manning had a great game against Alabama"
    result = extract_portal_mentions(text)

    assert result["is_portal_related"] is False


def test_predict_destination_returns_list():
    """Test destination prediction returns ranked list."""
    # Mock input - player with certain traits/history
    predictions = predict_destination(
        position="QB",
        from_team="Texas",
        composite_grade=85,
        class_year=2025,
    )

    assert isinstance(predictions, list)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_portal_processing.py -v
```

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write transfer portal processing module**

```python
# src/processing/transfer_portal.py
"""Transfer portal processing and analysis."""

import logging
import re
from datetime import date

from ..storage.db import (
    get_connection,
    get_active_portal_players,
    insert_portal_snapshot,
)

logger = logging.getLogger(__name__)

# Keywords indicating portal activity
PORTAL_KEYWORDS = [
    r"\btransfer portal\b",
    r"\bentered the portal\b",
    r"\bin the portal\b",
    r"\bcommitted to\b.*\btransfer\b",
    r"\bwithdrew from.*(portal|transfer)",
    r"\btransferring to\b",
    r"\btransfer from\b",
]

EVENT_PATTERNS = {
    "entered": [
        r"entered the (transfer )?portal",
        r"in the portal",
        r"entering the portal",
        r"has entered",
    ],
    "committed": [
        r"committed to",
        r"transferring to",
        r"will transfer to",
        r"announces commitment",
    ],
    "withdrawn": [
        r"withdrew from",
        r"withdrawn from the portal",
        r"removed.*from.*portal",
        r"staying at",
    ],
}


def extract_portal_mentions(text: str) -> dict:
    """Extract transfer portal mentions from text.

    Args:
        text: Text to analyze

    Returns:
        Dict with is_portal_related, event_type, confidence
    """
    text_lower = text.lower()

    # Check if portal-related
    is_related = any(re.search(kw, text_lower) for kw in PORTAL_KEYWORDS)

    if not is_related:
        return {
            "is_portal_related": False,
            "event_type": None,
            "confidence": 0.0,
        }

    # Determine event type
    event_type = None
    confidence = 0.5

    for etype, patterns in EVENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                event_type = etype
                confidence = 0.8
                break
        if event_type:
            break

    return {
        "is_portal_related": True,
        "event_type": event_type or "entered",  # Default to entered
        "confidence": confidence,
    }


def predict_destination(
    position: str,
    from_team: str,
    composite_grade: int | None = None,
    class_year: int | None = None,
) -> list[dict]:
    """Predict likely transfer destinations.

    Uses historical patterns and player profile to suggest destinations.

    Args:
        position: Player position
        from_team: Team player is leaving
        composite_grade: Player's composite grade
        class_year: Player's class year

    Returns:
        List of {team, probability, reasoning} dicts
    """
    # Historical destination patterns by position and grade tier
    # This is a simplified heuristic - could be enhanced with ML
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get historical commitments for similar players
        cur.execute(
            """
            SELECT te.to_team, COUNT(*) as count
            FROM scouting.transfer_events te
            JOIN scouting.players p ON te.player_id = p.id
            WHERE te.event_type = 'committed'
            AND te.to_team IS NOT NULL
            AND UPPER(p.position) = UPPER(%s)
            AND te.from_team != %s
            GROUP BY te.to_team
            ORDER BY count DESC
            LIMIT 10
            """,
            (position, from_team),
        )

        historical = cur.fetchall()

        if not historical:
            # Return generic predictions based on grade tier
            if composite_grade and composite_grade >= 80:
                return [
                    {"team": "Alabama", "probability": 0.15, "reasoning": "Elite program, high-grade target"},
                    {"team": "Georgia", "probability": 0.15, "reasoning": "Elite program, high-grade target"},
                    {"team": "Ohio State", "probability": 0.12, "reasoning": "Elite program, high-grade target"},
                ]
            else:
                return [
                    {"team": "Unknown", "probability": 0.5, "reasoning": "Insufficient historical data"},
                ]

        total_count = sum(row[1] for row in historical)
        predictions = []

        for team, count in historical[:5]:
            prob = round(count / total_count, 2)
            predictions.append({
                "team": team,
                "probability": prob,
                "reasoning": f"Historical {position} destination ({count} transfers)",
            })

        return predictions

    finally:
        cur.close()
        conn.close()


def generate_portal_snapshot() -> dict:
    """Generate a daily snapshot of portal activity.

    Returns:
        Summary dict of portal state
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get all active portal players
        active = get_active_portal_players(conn, limit=1000)

        # Count by position
        by_position = {}
        for player in active:
            pos = player.get("position") or "Unknown"
            by_position[pos] = by_position.get(pos, 0) + 1

        # Count by conference (if we have that data - simplified for now)
        by_conference = {}  # Would need conference mapping

        # Notable entries (top graded players)
        notable = [
            f"{p['name']} ({p['position']}, {p['composite_grade']})"
            for p in sorted(active, key=lambda x: x.get("composite_grade") or 0, reverse=True)[:10]
        ]

        # Insert snapshot
        snapshot_id = insert_portal_snapshot(
            conn,
            snapshot_date=date.today(),
            total_in_portal=len(active),
            by_position=by_position,
            by_conference=by_conference,
            notable_entries=notable,
        )

        return {
            "snapshot_id": snapshot_id,
            "date": date.today().isoformat(),
            "total_in_portal": len(active),
            "by_position": by_position,
            "notable_entries": notable,
        }

    finally:
        cur.close()
        conn.close()


def analyze_team_portal_impact(team: str) -> dict:
    """Analyze the impact of transfers on a team.

    Args:
        team: Team to analyze

    Returns:
        Impact analysis dict
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Get outgoing players (grade lost)
        cur.execute(
            """
            SELECT p.position, p.composite_grade
            FROM scouting.transfer_events te
            JOIN scouting.players p ON te.player_id = p.id
            WHERE te.from_team = %s AND te.event_type = 'entered'
            AND te.event_date >= CURRENT_DATE - INTERVAL '1 year'
            """,
            (team,),
        )
        outgoing = cur.fetchall()
        outgoing_grades = [g for _, g in outgoing if g]
        avg_outgoing = sum(outgoing_grades) / len(outgoing_grades) if outgoing_grades else 0

        # Get incoming players (grade gained)
        cur.execute(
            """
            SELECT p.position, p.composite_grade
            FROM scouting.transfer_events te
            JOIN scouting.players p ON te.player_id = p.id
            WHERE te.to_team = %s AND te.event_type = 'committed'
            AND te.event_date >= CURRENT_DATE - INTERVAL '1 year'
            """,
            (team,),
        )
        incoming = cur.fetchall()
        incoming_grades = [g for _, g in incoming if g]
        avg_incoming = sum(incoming_grades) / len(incoming_grades) if incoming_grades else 0

        # Position group impact
        position_impact = {}
        for pos, grade in outgoing:
            if pos not in position_impact:
                position_impact[pos] = {"lost": 0, "gained": 0}
            position_impact[pos]["lost"] += 1

        for pos, grade in incoming:
            if pos not in position_impact:
                position_impact[pos] = {"lost": 0, "gained": 0}
            position_impact[pos]["gained"] += 1

        return {
            "team": team,
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
            "net_transfers": len(incoming) - len(outgoing),
            "avg_grade_lost": round(avg_outgoing, 1),
            "avg_grade_gained": round(avg_incoming, 1),
            "grade_delta": round(avg_incoming - avg_outgoing, 1),
            "position_impact": position_impact,
        }

    finally:
        cur.close()
        conn.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_portal_processing.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/processing/transfer_portal.py tests/test_portal_processing.py
git commit -m "feat: add transfer portal processing module"
```

---

## Task 10: Add Transfer Portal API Endpoints

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/api/models.py`
- Modify: `/Users/robstover/Development/personal/cfb-scout/src/api/main.py`

**Step 1: Add new Pydantic models to models.py**

```python
class TransferEvent(BaseModel):
    """Transfer portal event."""

    id: int
    player_id: int
    event_type: str
    from_team: str | None
    to_team: str | None
    event_date: date
    source_url: str | None
    notes: str | None
    created_at: datetime


class PortalPlayer(BaseModel):
    """Player in the transfer portal."""

    id: int
    name: str
    team: str | None
    position: str | None
    class_year: int | None
    composite_grade: int | None
    portal_entry_date: date
    from_team: str | None


class DestinationPrediction(BaseModel):
    """Predicted transfer destination."""

    team: str
    probability: float
    reasoning: str


class TeamTransferActivity(BaseModel):
    """Team transfer activity summary."""

    team: str
    outgoing: list[dict]
    incoming: list[dict]
    net: int


class PortalImpact(BaseModel):
    """Team portal impact analysis."""

    team: str
    outgoing_count: int
    incoming_count: int
    net_transfers: int
    avg_grade_lost: float
    avg_grade_gained: float
    grade_delta: float
    position_impact: dict
```

**Step 2: Add transfer portal endpoints to main.py**

Add imports:
```python
from ..storage.db import (
    # ... existing imports ...
    get_active_portal_players,
    get_player_transfer_history,
    get_team_transfer_activity,
    insert_transfer_event,
)
from ..processing.transfer_portal import (
    predict_destination,
    analyze_team_portal_impact,
    generate_portal_snapshot,
)
from .models import (
    # ... existing imports ...
    TransferEvent,
    PortalPlayer,
    DestinationPrediction,
    TeamTransferActivity,
    PortalImpact,
)
```

Add endpoints:
```python
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
```

**Step 3: Commit**

```bash
git add src/api/models.py src/api/main.py
git commit -m "feat: add transfer portal API endpoints"
```

---

## Task 11: Add API Tests for Phase 5 Endpoints

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/tests/test_api.py`

**Step 1: Add new endpoint tests**

```python
# Add to tests/test_api.py

def test_get_alerts_requires_user_id():
    """Test that alerts endpoints require user_id."""
    response = client.get("/alerts")
    assert response.status_code == 422


def test_get_alert_history():
    """Test alert history endpoint."""
    response = client.get("/alerts/history?user_id=test-user")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_active_portal_players():
    """Test active portal players endpoint."""
    response = client.get("/transfer-portal/active")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_portal_players_by_position():
    """Test portal players filtered by position."""
    response = client.get("/transfer-portal/active?position=QB")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_team_transfers():
    """Test team transfer activity endpoint."""
    response = client.get("/teams/Texas/transfers")
    assert response.status_code == 200
    data = response.json()
    assert "outgoing" in data
    assert "incoming" in data
    assert "net" in data
```

**Step 2: Run all tests**

```bash
python -m pytest tests/test_api.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_api.py
git commit -m "test: add API tests for Phase 5 endpoints"
```

---

## Task 12: Update Documentation and Final Verification

**Files:**
- Modify: `/Users/robstover/Development/personal/cfb-scout/README.md`

**Step 1: Update README with Phase 5 features**

Add to README:

```markdown
## Phase 5 Status

- [x] Alert system (grade/status/report changes)
- [x] Alert history and notifications
- [x] Transfer portal tracking
- [x] Destination predictions
- [x] Team portal impact analysis

## API Endpoints (continued)

### Alerts
- `GET /alerts?user_id=X` - User's active alerts
- `POST /alerts?user_id=X` - Create alert rule
- `DELETE /alerts/{id}` - Delete alert
- `POST /alerts/{id}/deactivate` - Deactivate alert
- `GET /alerts/history?user_id=X` - Fired alerts
- `POST /alerts/history/{id}/read` - Mark as read

### Transfer Portal
- `GET /transfer-portal/active` - Current portal players
- `GET /transfer-portal/player/{id}` - Player transfer history
- `GET /transfer-portal/player/{id}/predict` - Destination predictions
- `GET /teams/{name}/transfers` - Team transfer activity
- `GET /teams/{name}/portal-impact` - Portal impact analysis
- `POST /transfer-portal/snapshot` - Generate daily snapshot
```

**Step 2: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass

**Step 3: Run lint**

```bash
ruff check src/ tests/ --fix
ruff format src/ tests/
```

**Step 4: Final commit and push**

```bash
git add -A
git commit -m "docs: update README with Phase 5 features"
git push origin main
```

---

## Success Criteria Checklist

### Alert System
- [ ] Alerts schema deployed (alerts, alert_history tables)
- [ ] Alert CRUD operations work
- [ ] Grade change alerts fire correctly
- [ ] Status change alerts fire correctly
- [ ] Alert history tracks fired alerts
- [ ] API endpoints return correct responses

### Transfer Portal
- [ ] Transfer schema deployed (transfer_events, portal_snapshots)
- [ ] Portal entry/commit/withdraw events tracked
- [ ] Active portal players queryable
- [ ] Team transfer activity shows incoming/outgoing
- [ ] Destination predictions return results
- [ ] Portal impact analysis calculates grade deltas
- [ ] API endpoints return correct responses

### Overall
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] API documentation accessible at `/docs`
- [ ] README updated with new features
