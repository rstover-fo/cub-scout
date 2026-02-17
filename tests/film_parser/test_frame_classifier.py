"""Tests for film_parser.frame_classifier — feature computation and segment classification."""

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

    def test_uniform_frame_low_variance(self) -> None:
        frame = np.full((100, 200, 3), 128, dtype=np.uint8)
        features = _compute_frame_features(frame)
        assert features["color_variance"] == 0.0

    def test_high_variance_frame(self) -> None:
        rng = np.random.default_rng(42)
        frame = rng.integers(0, 256, (100, 200, 3), dtype=np.uint8)
        features = _compute_frame_features(frame)
        assert features["color_variance"] > 0

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
    def test_low_variance_high_edge_low_motion_is_situation(self, mock_sample: MagicMock) -> None:
        # Three identical low-variance frames with edge structure
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        # Add horizontal lines to create edge density
        for row in range(0, 100, 5):
            frame[row, :, :] = 255
        mock_sample.return_value = [frame.copy(), frame.copy(), frame.copy()]

        seg = Segment(start_time=0.0, end_time=2.0)
        result = classify_segment(
            "/fake/video.mp4",
            seg,
            color_var_threshold=50000,
            edge_density_threshold=0.01,
            motion_threshold=50.0,
        )
        assert result == SegmentType.SITUATION

    @patch("src.film_parser.frame_classifier.sample_frames")
    def test_high_motion_is_game_action(self, mock_sample: MagicMock) -> None:
        frame1 = np.zeros((100, 200, 3), dtype=np.uint8)
        frame2 = np.full((100, 200, 3), 200, dtype=np.uint8)
        frame3 = np.zeros((100, 200, 3), dtype=np.uint8)
        mock_sample.return_value = [frame1, frame2, frame3]

        seg = Segment(start_time=0.0, end_time=2.0)
        result = classify_segment("/fake/video.mp4", seg, motion_threshold=1.0)
        assert result == SegmentType.GAME_ACTION


class TestClassifySegments:
    @patch("src.film_parser.frame_classifier.cv2")
    def test_opens_video_once_and_releases(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_POS_MSEC = 0
        # Return enough frames for each segment (3 timestamps * 2 segments = 6 reads)
        mock_cap.read.return_value = (True, np.zeros((100, 200, 3), dtype=np.uint8))
        mock_cv2.COLOR_BGR2GRAY = 6
        mock_cv2.cvtColor.return_value = np.zeros((100, 200), dtype=np.uint8)
        mock_cv2.Canny.return_value = np.zeros((100, 200), dtype=np.uint8)

        segments = [
            Segment(start_time=0.0, end_time=2.0),
            Segment(start_time=2.0, end_time=4.0),
        ]

        result = classify_segments("/fake/video.mp4", segments)

        assert len(result) == 2
        # Video should be opened only once
        mock_cv2.VideoCapture.assert_called_once_with("/fake/video.mp4")
        mock_cap.release.assert_called_once()

    @patch("src.film_parser.frame_classifier.cv2")
    def test_all_segments_get_classified(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_POS_MSEC = 0
        mock_cap.read.return_value = (True, np.zeros((100, 200, 3), dtype=np.uint8))
        mock_cv2.COLOR_BGR2GRAY = 6
        mock_cv2.cvtColor.return_value = np.zeros((100, 200), dtype=np.uint8)
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
