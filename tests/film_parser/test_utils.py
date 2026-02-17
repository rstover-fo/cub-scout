"""Tests for film_parser.utils — format_timestamp and get_video_info."""

from unittest.mock import MagicMock, patch

import pytest

from src.film_parser.utils import format_timestamp, get_video_info


class TestFormatTimestamp:
    def test_zero(self) -> None:
        assert format_timestamp(0.0) == "00:00:00.000"

    def test_one_second(self) -> None:
        assert format_timestamp(1.0) == "00:00:01.000"

    def test_fractional_seconds(self) -> None:
        assert format_timestamp(1.5) == "00:00:01.500"

    def test_minutes_and_seconds(self) -> None:
        assert format_timestamp(83.456) == "00:01:23.456"

    def test_hours(self) -> None:
        assert format_timestamp(3661.0) == "01:01:01.000"

    def test_large_value(self) -> None:
        # 2 hours, 30 minutes, 45.123 seconds
        assert format_timestamp(9045.123) == "02:30:45.123"

    def test_small_fraction(self) -> None:
        assert format_timestamp(0.001) == "00:00:00.001"

    def test_rounding(self) -> None:
        # 0.9999 should round to 1.000
        assert format_timestamp(0.9999) == "00:00:01.000"


class TestGetVideoInfo:
    @patch("src.film_parser.utils.cv2")
    def test_returns_metadata(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        def _get(prop: int) -> float:
            return {5: 30.0, 7: 900, 3: 1920, 4: 1080}[prop]

        mock_cap.get.side_effect = _get

        info = get_video_info("/fake/video.mp4")

        assert info["fps"] == 30.0
        assert info["frame_count"] == 900
        assert info["width"] == 1920
        assert info["height"] == 1080
        assert info["duration"] == 30.0  # 900 / 30
        mock_cap.release.assert_called_once()

    @patch("src.film_parser.utils.cv2")
    def test_video_not_opened_raises(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = False

        with pytest.raises(ValueError, match="Cannot open video"):
            get_video_info("/fake/missing.mp4")

    @patch("src.film_parser.utils.cv2")
    def test_zero_fps_returns_zero_duration(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4

        def _get(prop: int) -> float:
            return {5: 0.0, 7: 100, 3: 640, 4: 480}[prop]

        mock_cap.get.side_effect = _get

        info = get_video_info("/fake/video.mp4")
        assert info["duration"] == 0.0
        mock_cap.release.assert_called_once()
