"""Alert processing and condition checking."""

import logging
from dataclasses import dataclass
from datetime import datetime

from ..storage.db import (
    fire_alert,
    get_connection,
    get_player_timeline,
    get_scouting_player,
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


async def process_alerts_for_player(player_id: int) -> list[dict]:
    """Check all alerts for a specific player.

    Args:
        player_id: Player to check alerts for

    Returns:
        List of fired alert details
    """
    async with get_connection() as conn:
        cur = conn.cursor()
        fired = []

        # Get all active alerts for this player
        await cur.execute(
            """
            SELECT a.id, a.user_id, a.name, a.alert_type, a.threshold, a.last_checked_at
            FROM scouting.alerts a
            WHERE a.player_id = %s AND a.is_active = TRUE
            """,
            (player_id,),
        )

        alerts = await cur.fetchall()
        if not alerts:
            return []

        # Get player data
        player = await get_scouting_player(conn, player_id)
        if not player:
            return []

        timeline = await get_player_timeline(conn, player_id, limit=2)

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
                history_id = await fire_alert(
                    conn,
                    alert_id,
                    result.trigger_data or {},
                    result.message or "",
                )
                fired.append(
                    {
                        "alert_id": alert_id,
                        "history_id": history_id,
                        "alert_name": name,
                        "message": result.message,
                        "player_id": player_id,
                        "player_name": player.get("name"),
                    }
                )

            await update_alert_checked(conn, alert_id)

        return fired


async def run_alert_check() -> dict:
    """Run alert check for all active alerts.

    Returns:
        Summary of alerts processed and fired
    """
    async with get_connection() as conn:
        cur = conn.cursor()

        # Get distinct players with active alerts
        await cur.execute(
            """
            SELECT DISTINCT player_id
            FROM scouting.alerts
            WHERE is_active = TRUE AND player_id IS NOT NULL
            """
        )

        player_ids = [row[0] for row in await cur.fetchall()]

    total_fired = []
    for player_id in player_ids:
        fired = await process_alerts_for_player(player_id)
        total_fired.extend(fired)

    return {
        "players_checked": len(player_ids),
        "alerts_fired": len(total_fired),
        "fired_details": total_fired,
        "timestamp": datetime.now().isoformat(),
    }
