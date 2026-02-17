"""Tests for film_parser.frame_classifier — black ratio based classification."""

from unittest.mock import MagicMock, patch

import numpy as np

from src.film_parser.frame_classifier import (
    _compute_frame_features,
    classify_segment,
    classify_segments,
)
from src.film_parser.models import Segment, SegmentType


class TestComputeFrameFeatures:
    def test_returns_expected_keys(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        features = _compute_frame_features(frame)
        assert "color_variance" in features
        assert "edge_density" in features
        assert "black_ratio" in features

    def test_all_black_frame(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        features = _compute_frame_features(frame)
        assert features["black_ratio"] == 1.0

    def test_all_white_frame(self) -> None:
        frame = np.full((100, 200, 3), 255, dtype=np.uint8)
        features = _compute_frame_features(frame)
        assert features["black_ratio"] == 0.0

    def test_mixed_frame_black_ratio(self) -> None:
        frame = np.full((100, 200, 3), 128, dtype=np.uint8)
        # Top half black
        frame[:50, :, :] = 0
        features = _compute_frame_features(frame)
        assert 0.4 < features["black_ratio"] < 0.6

    def test_edge_density_range(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        features = _compute_frame_features(frame)
        assert 0.0 <= features["edge_density"] <= 1.0


class TestClassifySegment:
    @patch("src.film_parser.frame_classifier.sample_frames")
    def test_too_few_frames_returns_game_action(self, mock_sample: MagicMock) -> None:
        mock_sample.return_value = [np.zeros((100, 200, 3), dtype=np.uint8)]
        seg = Segment(start_time=0.0, end_time=2.0)
        result = classify_segment("/fake/video.mp4", seg)
        assert result == SegmentType.GAME_ACTION

    @patch("src.film_parser.frame_classifier.sample_frames")
    def test_high_black_ratio_is_situation(self, mock_sample: MagicMock) -> None:
        """Frames with >20% black pixels (like Catapult scoreboard) -> SITUATION."""
        # Simulate scoreboard: ~66% black
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        frame[0:34, :, :] = 150  # top third non-black
        mock_sample.return_value = [frame.copy(), frame.copy(), frame.copy()]

        seg = Segment(start_time=0.0, end_time=3.0)
        result = classify_segment("/fake/video.mp4", seg)
        assert result == SegmentType.SITUATION

    @patch("src.film_parser.frame_classifier.sample_frames")
    def test_low_black_ratio_is_game_action(self, mock_sample: MagicMock) -> None:
        """Frames with <1% black pixels (field footage) -> GAME_ACTION."""
        frame = np.full((100, 200, 3), 100, dtype=np.uint8)  # all mid-gray, 0% black
        mock_sample.return_value = [frame.copy(), frame.copy(), frame.copy()]

        seg = Segment(start_time=0.0, end_time=3.0)
        result = classify_segment("/fake/video.mp4", seg)
        assert result == SegmentType.GAME_ACTION

    @patch("src.film_parser.frame_classifier.sample_frames")
    def test_custom_threshold(self, mock_sample: MagicMock) -> None:
        """Custom black_ratio_threshold overrides default."""
        # 50% black frame
        frame = np.full((100, 200, 3), 128, dtype=np.uint8)
        frame[:50, :, :] = 0
        mock_sample.return_value = [frame.copy(), frame.copy(), frame.copy()]

        seg = Segment(start_time=0.0, end_time=3.0)
        # With high threshold, should be GAME_ACTION
        result = classify_segment("/fake/video.mp4", seg, black_ratio_threshold=0.60)
        assert result == SegmentType.GAME_ACTION
        # With low threshold, should be SITUATION
        result = classify_segment("/fake/video.mp4", seg, black_ratio_threshold=0.30)
        assert result == SegmentType.SITUATION


class TestClassifySegments:
    @patch("src.film_parser.frame_classifier.cv2")
    def test_opens_video_once_and_releases(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_POS_MSEC = 0
        # Return bright frames (no black = game action)
        mock_cap.read.return_value = (True, np.full((100, 200, 3), 128, dtype=np.uint8))
        mock_cv2.COLOR_BGR2GRAY = 6
        mock_cv2.cvtColor.return_value = np.full((100, 200), 128, dtype=np.uint8)
        mock_cv2.Canny.return_value = np.zeros((100, 200), dtype=np.uint8)

        segments = [
            Segment(start_time=0.0, end_time=2.0),
            Segment(start_time=2.0, end_time=4.0),
        ]

        result = classify_segments("/fake/video.mp4", segments)

        assert len(result) == 2
        mock_cv2.VideoCapture.assert_called_once_with("/fake/video.mp4")
        mock_cap.release.assert_called_once()

    @patch("src.film_parser.frame_classifier.cv2")
    def test_all_segments_get_classified(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_POS_MSEC = 0
        mock_cap.read.return_value = (True, np.full((100, 200, 3), 128, dtype=np.uint8))
        mock_cv2.COLOR_BGR2GRAY = 6
        mock_cv2.cvtColor.return_value = np.full((100, 200), 128, dtype=np.uint8)
        mock_cv2.Canny.return_value = np.zeros((100, 200), dtype=np.uint8)

        segments = [
            Segment(start_time=0.0, end_time=1.0),
            Segment(start_time=1.0, end_time=2.0),
            Segment(start_time=2.0, end_time=3.0),
        ]

        result = classify_segments("/fake/video.mp4", segments)

        assert len(result) == 3
        for seg in result:
            assert seg.segment_type != SegmentType.UNCLASSIFIED

    @patch("src.film_parser.frame_classifier.cv2")
    def test_empty_segments(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap

        result = classify_segments("/fake/video.mp4", [])

        assert result == []
        mock_cap.release.assert_called_once()

    @patch("src.film_parser.frame_classifier.cv2")
    def test_releases_on_exception(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_POS_MSEC = 0
        mock_cap.read.side_effect = RuntimeError("video error")

        segments = [Segment(start_time=0.0, end_time=2.0)]

        try:
            classify_segments("/fake/video.mp4", segments)
        except RuntimeError:
            pass

        mock_cap.release.assert_called_once()
