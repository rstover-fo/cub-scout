"""Tests for film_parser.scene_detect — detect_scenes with mocked scenedetect."""

from unittest.mock import MagicMock, patch

from src.film_parser.models import SegmentType
from src.film_parser.scene_detect import detect_scenes


def _make_timecode(seconds: float) -> MagicMock:
    """Create a mock scenedetect FrameTimecode."""
    tc = MagicMock()
    tc.get_seconds.return_value = seconds
    return tc


class TestDetectScenes:
    @patch("src.film_parser.scene_detect.detect")
    @patch("src.film_parser.scene_detect.ContentDetector")
    def test_returns_segments(self, mock_detector_cls: MagicMock, mock_detect: MagicMock) -> None:
        mock_detect.return_value = [
            (_make_timecode(0.0), _make_timecode(3.0)),
            (_make_timecode(3.0), _make_timecode(7.0)),
            (_make_timecode(7.0), _make_timecode(12.0)),
        ]

        segments = detect_scenes("/fake/video.mp4")

        assert len(segments) == 3
        assert segments[0].start_time == 0.0
        assert segments[0].end_time == 3.0
        assert segments[1].start_time == 3.0
        assert segments[1].end_time == 7.0
        assert segments[2].start_time == 7.0
        assert segments[2].end_time == 12.0

    @patch("src.film_parser.scene_detect.detect")
    @patch("src.film_parser.scene_detect.ContentDetector")
    def test_all_segments_unclassified(
        self, mock_detector_cls: MagicMock, mock_detect: MagicMock
    ) -> None:
        mock_detect.return_value = [
            (_make_timecode(0.0), _make_timecode(5.0)),
        ]

        segments = detect_scenes("/fake/video.mp4")

        for seg in segments:
            assert seg.segment_type == SegmentType.UNCLASSIFIED

    @patch("src.film_parser.scene_detect.detect")
    @patch("src.film_parser.scene_detect.ContentDetector")
    def test_short_scenes_filtered(
        self, mock_detector_cls: MagicMock, mock_detect: MagicMock
    ) -> None:
        mock_detect.return_value = [
            (_make_timecode(0.0), _make_timecode(0.3)),  # too short (< 0.5s)
            (_make_timecode(0.3), _make_timecode(3.0)),  # valid
            (_make_timecode(3.0), _make_timecode(3.2)),  # too short
        ]

        segments = detect_scenes("/fake/video.mp4", min_scene_len=0.5)

        assert len(segments) == 1
        assert segments[0].start_time == 0.3

    @patch("src.film_parser.scene_detect.detect")
    @patch("src.film_parser.scene_detect.ContentDetector")
    def test_empty_scene_list(self, mock_detector_cls: MagicMock, mock_detect: MagicMock) -> None:
        mock_detect.return_value = []

        segments = detect_scenes("/fake/video.mp4")

        assert segments == []

    @patch("src.film_parser.scene_detect.detect")
    @patch("src.film_parser.scene_detect.ContentDetector")
    def test_custom_threshold_passed(
        self, mock_detector_cls: MagicMock, mock_detect: MagicMock
    ) -> None:
        mock_detect.return_value = []

        detect_scenes("/fake/video.mp4", threshold=42.0)

        mock_detector_cls.assert_called_once_with(threshold=42.0)

    @patch("src.film_parser.scene_detect.detect")
    @patch("src.film_parser.scene_detect.ContentDetector")
    def test_duration_computed(self, mock_detector_cls: MagicMock, mock_detect: MagicMock) -> None:
        mock_detect.return_value = [
            (_make_timecode(1.0), _make_timecode(4.5)),
        ]

        segments = detect_scenes("/fake/video.mp4")

        assert segments[0].duration == 3.5
