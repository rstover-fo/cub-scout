"""Tests for play_assembler state machine."""

import pytest

from src.film_parser.models import (
    CameraAngle,
    GameMetadata,
    Segment,
    SegmentType,
    Side,
)
from src.film_parser.play_assembler import assemble_plays


@pytest.fixture
def game_meta() -> GameMetadata:
    return GameMetadata(
        team="Alabama",
        side=Side.OFFENSE,
        opponent="Georgia",
        opponent_side=Side.DEFENSE,
        season_year=2025,
        filename="Alabama_O_Georgia_D_2025.mp4",
    )


def _seg(start: float, end: float, seg_type: SegmentType) -> Segment:
    return Segment(start_time=start, end_time=end, segment_type=seg_type)


SIT = SegmentType.SITUATION
GA = SegmentType.GAME_ACTION
UC = SegmentType.UNCLASSIFIED


class TestCleanTriplets:
    def test_three_complete_plays(self, game_meta: GameMetadata) -> None:
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 5.0, GA),
            _seg(5.0, 9.0, GA),
            _seg(9.0, 10.0, SIT),
            _seg(10.0, 14.0, GA),
            _seg(14.0, 18.0, GA),
            _seg(18.0, 19.0, SIT),
            _seg(19.0, 23.0, GA),
            _seg(23.0, 27.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 3
        assert catalog.plays[0].play_number == 1
        assert catalog.plays[1].play_number == 2
        assert catalog.plays[2].play_number == 3

        for play in catalog.plays:
            assert play.sideline.camera_angle == CameraAngle.SIDELINE
            assert play.endzone.camera_angle == CameraAngle.ENDZONE

        q = catalog.quality_metrics
        assert q.total_segments == 9
        assert q.classified_situations == 3
        assert q.classified_game_actions == 6
        assert q.complete_triplets == 3
        assert q.orphaned_segments == 0


class TestConsecutiveSituations:
    def test_second_situation_resets_state(self, game_meta: GameMetadata) -> None:
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 2.0, SIT),  # resets, first situation orphaned
            _seg(2.0, 6.0, GA),
            _seg(6.0, 10.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 1
        assert catalog.plays[0].situation.start_time == 1.0
        assert catalog.quality_metrics.orphaned_segments == 1


class TestTrailingIncomplete:
    def test_trailing_situation_only(self, game_meta: GameMetadata) -> None:
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 5.0, GA),
            _seg(5.0, 9.0, GA),
            _seg(9.0, 10.0, SIT),  # trailing, no game actions follow
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 1
        assert catalog.quality_metrics.orphaned_segments == 1

    def test_trailing_situation_plus_one_action(self, game_meta: GameMetadata) -> None:
        """Trailing SIT + GA emits a doublet play (no endzone)."""
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 5.0, GA),
            _seg(5.0, 9.0, GA),
            _seg(9.0, 10.0, SIT),
            _seg(10.0, 14.0, GA),  # only one GA, no endzone
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 2
        assert catalog.plays[1].endzone is None  # doublet
        assert catalog.plays[1].sideline.camera_angle == CameraAngle.SIDELINE
        assert catalog.quality_metrics.orphaned_segments == 0


class TestDoubletPlays:
    def test_doublet_emitted_when_sit_interrupts(self, game_meta: GameMetadata) -> None:
        """SIT → GA → SIT should emit a doublet (no endzone), not orphan."""
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 5.0, GA),  # sideline (combined clip, no endzone cut)
            _seg(5.0, 6.0, SIT),  # next play's situation
            _seg(6.0, 10.0, GA),
            _seg(10.0, 14.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 2
        # First play is a doublet
        assert catalog.plays[0].endzone is None
        assert catalog.plays[0].sideline.start_time == 1.0
        # Second play is a full triplet
        assert catalog.plays[1].endzone is not None
        assert catalog.quality_metrics.orphaned_segments == 0

    def test_multiple_consecutive_doublets(self, game_meta: GameMetadata) -> None:
        """Multiple SIT → GA → SIT → GA patterns."""
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 5.0, GA),
            _seg(5.0, 6.0, SIT),
            _seg(6.0, 10.0, GA),
            _seg(10.0, 11.0, SIT),
            _seg(11.0, 15.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 3
        for play in catalog.plays:
            assert play.endzone is None  # all doublets
        assert catalog.quality_metrics.orphaned_segments == 0

    def test_mixed_doublets_and_triplets(self, game_meta: GameMetadata) -> None:
        """Mix of SIT→GA and SIT→GA→GA patterns."""
        segments = [
            _seg(0.0, 1.0, SIT),
            _seg(1.0, 5.0, GA),  # doublet
            _seg(5.0, 6.0, SIT),
            _seg(6.0, 10.0, GA),  # triplet
            _seg(10.0, 14.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 2
        assert catalog.plays[0].endzone is None  # doublet
        assert catalog.plays[1].endzone is not None  # triplet


class TestEmptyInput:
    def test_empty_segments(self, game_meta: GameMetadata) -> None:
        catalog = assemble_plays([], game_meta)

        assert len(catalog.plays) == 0
        assert catalog.quality_metrics.total_segments == 0
        assert catalog.quality_metrics.orphaned_segments == 0


class TestAllGameActionsNoSituations:
    def test_all_orphaned(self, game_meta: GameMetadata) -> None:
        segments = [
            _seg(0.0, 4.0, GA),
            _seg(4.0, 8.0, GA),
            _seg(8.0, 12.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 0
        assert catalog.quality_metrics.classified_game_actions == 3
        assert catalog.quality_metrics.orphaned_segments == 3


class TestUnclassifiedSegments:
    def test_unclassified_skipped(self, game_meta: GameMetadata) -> None:
        segments = [
            _seg(0.0, 0.5, UC),
            _seg(0.5, 1.0, SIT),
            _seg(1.0, 5.0, GA),
            _seg(5.0, 5.5, UC),
            _seg(5.5, 9.0, GA),
        ]
        catalog = assemble_plays(segments, game_meta)

        assert len(catalog.plays) == 1
        assert catalog.quality_metrics.total_segments == 5
        assert catalog.quality_metrics.classified_situations == 1
        assert catalog.quality_metrics.classified_game_actions == 2
