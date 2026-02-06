"""Tests for entity linking pipeline."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from src.processing.entity_linking import link_report_entities, run_entity_linking
from src.processing.player_matching import PlayerMatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(**overrides) -> dict:
    """Build a minimal report dict."""
    defaults = {
        "id": 1,
        "raw_text": "QB Arch Manning looked sharp in Texas spring practice.",
        "team_ids": [42],
        "source_url": "https://example.com/report/1",
    }
    defaults.update(overrides)
    return defaults


@asynccontextmanager
async def _mock_conn_ctx():
    """Async context manager yielding a mock connection."""
    mock_conn = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.description = [
        ("id",),
        ("source_url",),
        ("source_name",),
        ("content_type",),
        ("raw_text",),
        ("team_ids",),
    ]
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.cursor.return_value = mock_cursor
    yield mock_conn


def _roster_match(**overrides) -> PlayerMatch:
    """Build a PlayerMatch from roster source."""
    defaults = dict(
        source="roster",
        source_id="100",
        first_name="Arch",
        last_name="Manning",
        team="Texas",
        position="QB",
        year=2025,
        confidence=95.0,
        match_method="deterministic",
    )
    defaults.update(overrides)
    return PlayerMatch(**defaults)


# ---------------------------------------------------------------------------
# link_report_entities tests
# ---------------------------------------------------------------------------

_LINK_PATCHES = {
    "conn": "src.processing.entity_linking.get_connection",
    "upsert": "src.processing.entity_linking.upsert_scouting_player",
    "link": "src.processing.entity_linking.link_report_to_player",
    "regex": "src.processing.entity_linking.extract_player_mentions",
    "claude": "src.processing.entity_linking.extract_player_mentions_claude",
    "match": "src.processing.entity_linking.match_player_with_review",
}


async def test_link_report_entities_regex_extraction():
    """Regex mode extracts names, no match found -> creates unlinked players."""
    report = _make_report()

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx) as _,
        patch(_LINK_PATCHES["regex"], return_value=["Arch Manning", "Quinn Ewers"]) as mock_regex,
        patch(
            _LINK_PATCHES["match"],
            new_callable=AsyncMock,
            return_value=(None, None),
        ) as mock_match,
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=10) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock) as mock_link,
    ):
        result = await link_report_entities(report, use_claude=False)

    assert result == [10, 10]
    mock_regex.assert_called_once_with(report["raw_text"])
    assert mock_match.call_count == 2
    assert mock_upsert.call_count == 2
    assert mock_link.call_count == 2

    # Verify upsert was called with extracted name and default team
    first_upsert_kwargs = mock_upsert.call_args_list[0].kwargs
    assert first_upsert_kwargs["team"] == 42
    assert first_upsert_kwargs["position"] is None
    assert first_upsert_kwargs["current_status"] == "active"


async def test_link_report_entities_claude_extraction():
    """Claude mode extracts structured mentions with position/team."""
    report = _make_report()
    claude_mentions = [
        {"name": "Arch Manning", "position": "QB", "team": "Texas", "context": "starter"},
    ]

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(
            _LINK_PATCHES["claude"],
            new_callable=AsyncMock,
            return_value=claude_mentions,
        ) as mock_claude,
        patch(
            _LINK_PATCHES["match"],
            new_callable=AsyncMock,
            return_value=(None, None),
        ) as mock_match,
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=5) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock),
    ):
        result = await link_report_entities(report, use_claude=True)

    assert result == [5]
    mock_claude.assert_called_once_with(report["raw_text"])

    # match_player_with_review should receive the team from Claude extraction
    match_kwargs = mock_match.call_args.kwargs
    assert match_kwargs["team"] == "Texas"
    assert match_kwargs["position"] == "QB"

    # upsert gets extracted name and team from Claude
    upsert_kwargs = mock_upsert.call_args.kwargs
    assert upsert_kwargs["name"] == "Arch Manning"
    assert upsert_kwargs["team"] == "Texas"
    assert upsert_kwargs["position"] == "QB"


async def test_link_report_entities_with_match():
    """When match_player_with_review returns a match, upsert uses match data."""
    report = _make_report()
    match = _roster_match()

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(_LINK_PATCHES["regex"], return_value=["Arch Manning"]),
        patch(_LINK_PATCHES["match"], new_callable=AsyncMock, return_value=(match, None)),
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=7) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock) as mock_link,
    ):
        result = await link_report_entities(report)

    assert result == [7]

    upsert_kwargs = mock_upsert.call_args.kwargs
    assert upsert_kwargs["name"] == "Arch Manning"
    assert upsert_kwargs["team"] == "Texas"
    assert upsert_kwargs["position"] == "QB"
    assert upsert_kwargs["class_year"] == 2025
    assert upsert_kwargs["current_status"] == "active"
    assert upsert_kwargs["roster_player_id"] == 100
    assert upsert_kwargs["recruit_id"] is None

    mock_link.assert_called_once()


async def test_link_report_entities_with_recruit_match():
    """Recruit match sets recruit_id and status='recruit'."""
    report = _make_report()
    match = _roster_match(source="recruit", source_id="200")

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(_LINK_PATCHES["regex"], return_value=["Arch Manning"]),
        patch(_LINK_PATCHES["match"], new_callable=AsyncMock, return_value=(match, None)),
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=8) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock),
    ):
        result = await link_report_entities(report)

    assert result == [8]
    upsert_kwargs = mock_upsert.call_args.kwargs
    assert upsert_kwargs["current_status"] == "recruit"
    assert upsert_kwargs["recruit_id"] == 200
    assert upsert_kwargs["roster_player_id"] is None


async def test_link_report_entities_pending_link():
    """When match returns pending_link_id, that player is skipped."""
    report = _make_report()

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(_LINK_PATCHES["regex"], return_value=["Arch Manning", "Quinn Ewers"]),
        patch(
            _LINK_PATCHES["match"],
            new_callable=AsyncMock,
            side_effect=[
                (None, 99),  # first player -> pending
                (None, None),  # second player -> no match
            ],
        ),
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=11) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock) as mock_link,
    ):
        result = await link_report_entities(report)

    # Only second player should be linked
    assert result == [11]
    assert mock_upsert.call_count == 1
    assert mock_link.call_count == 1


async def test_link_report_entities_empty_report():
    """Report with no player mentions returns empty list."""
    report = _make_report(raw_text="No players mentioned here.")

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(_LINK_PATCHES["regex"], return_value=[]),
        patch(_LINK_PATCHES["match"], new_callable=AsyncMock) as mock_match,
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock) as mock_link,
    ):
        result = await link_report_entities(report, use_claude=False)

    assert result == []
    mock_match.assert_not_called()
    mock_upsert.assert_not_called()
    mock_link.assert_not_called()


async def test_link_report_entities_default_team():
    """Uses team_ids[0] when Claude mention has no team."""
    report = _make_report(team_ids=[77])
    claude_mentions = [
        {"name": "Some Player", "position": "WR", "team": None, "context": "general"},
    ]

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(_LINK_PATCHES["claude"], new_callable=AsyncMock, return_value=claude_mentions),
        patch(
            _LINK_PATCHES["match"],
            new_callable=AsyncMock,
            return_value=(None, None),
        ) as mock_match,
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=20) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock),
    ):
        result = await link_report_entities(report, use_claude=True)

    assert result == [20]

    # match should fall back to default_team since mention has no team
    match_kwargs = mock_match.call_args.kwargs
    assert match_kwargs["team"] == 77

    # upsert should also use default_team
    upsert_kwargs = mock_upsert.call_args.kwargs
    assert upsert_kwargs["team"] == 77


async def test_link_report_entities_no_team_ids():
    """When report has no team_ids, unlinked player uses 'Unknown' team."""
    report = _make_report(team_ids=[])

    with (
        patch(_LINK_PATCHES["conn"], side_effect=_mock_conn_ctx),
        patch(_LINK_PATCHES["regex"], return_value=["Arch Manning"]),
        patch(_LINK_PATCHES["match"], new_callable=AsyncMock, return_value=(None, None)),
        patch(_LINK_PATCHES["upsert"], new_callable=AsyncMock, return_value=30) as mock_upsert,
        patch(_LINK_PATCHES["link"], new_callable=AsyncMock),
    ):
        result = await link_report_entities(report)

    assert result == [30]
    upsert_kwargs = mock_upsert.call_args.kwargs
    assert upsert_kwargs["team"] == "Unknown"


# ---------------------------------------------------------------------------
# run_entity_linking tests
# ---------------------------------------------------------------------------


async def test_run_entity_linking_processes_batch():
    """Processes all reports returned by the DB query."""
    rows = [
        (1, "https://a.com", "src", "article", "QB Arch Manning plays well.", [42]),
        (2, "https://b.com", "src", "article", "RB Quinshon Judkins is fast.", [42]),
    ]

    @asynccontextmanager
    async def mock_conn_with_rows():
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.description = [
            ("id",),
            ("source_url",),
            ("source_name",),
            ("content_type",),
            ("raw_text",),
            ("team_ids",),
        ]
        mock_cursor.fetchall = AsyncMock(return_value=rows)
        mock_conn.cursor.return_value = mock_cursor
        yield mock_conn

    with (
        patch(
            "src.processing.entity_linking.get_connection",
            side_effect=mock_conn_with_rows,
        ),
        patch(
            "src.processing.entity_linking.link_report_entities",
            new_callable=AsyncMock,
            side_effect=[[10, 11], [12]],
        ) as mock_link,
    ):
        stats = await run_entity_linking(batch_size=10, use_claude=False)

    assert stats["reports_processed"] == 2
    assert stats["reports_linked"] == 2
    assert stats["players_linked"] == 3
    assert stats["errors"] == 0
    assert mock_link.call_count == 2


async def test_run_entity_linking_handles_errors():
    """One report throws exception; processing continues for the rest."""
    rows = [
        (1, "https://a.com", "src", "article", "text1", [42]),
        (2, "https://b.com", "src", "article", "text2", [42]),
        (3, "https://c.com", "src", "article", "text3", [42]),
    ]

    @asynccontextmanager
    async def mock_conn_with_rows():
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.description = [
            ("id",),
            ("source_url",),
            ("source_name",),
            ("content_type",),
            ("raw_text",),
            ("team_ids",),
        ]
        mock_cursor.fetchall = AsyncMock(return_value=rows)
        mock_conn.cursor.return_value = mock_cursor
        yield mock_conn

    with (
        patch(
            "src.processing.entity_linking.get_connection",
            side_effect=mock_conn_with_rows,
        ),
        patch(
            "src.processing.entity_linking.link_report_entities",
            new_callable=AsyncMock,
            side_effect=[[10], RuntimeError("DB error"), [12]],
        ),
    ):
        stats = await run_entity_linking(batch_size=10)

    assert stats["reports_processed"] == 3
    assert stats["reports_linked"] == 2
    assert stats["players_linked"] == 2
    assert stats["errors"] == 1


async def test_run_entity_linking_no_reports():
    """No unprocessed reports returns zeroed stats."""
    with (
        patch(
            "src.processing.entity_linking.get_connection",
            side_effect=_mock_conn_ctx,
        ),
    ):
        stats = await run_entity_linking()

    assert stats == {
        "reports_processed": 0,
        "reports_linked": 0,
        "players_linked": 0,
        "errors": 0,
    }
