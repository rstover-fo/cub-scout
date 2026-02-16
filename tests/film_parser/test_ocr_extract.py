"""Tests for OCR extraction of situation data from film frames."""

from unittest.mock import MagicMock, patch

import numpy as np

from src.film_parser.models import Segment, SegmentType, SituationData
from src.film_parser.ocr_extract import (
    _parse_clock,
    _parse_down_distance,
    _parse_play_number,
    _parse_quarter,
    _parse_yard_line,
    extract_all_situation_data,
    extract_situation_data,
)

# ---------------------------------------------------------------------------
# Quarter regex tests
# ---------------------------------------------------------------------------


class TestParseQuarter:
    def test_q_prefix(self):
        assert _parse_quarter("Q1 some text") == 1

    def test_qtr_prefix(self):
        assert _parse_quarter("QTR 3") == 3

    def test_suffix_st(self):
        assert _parse_quarter("1ST QTR") == 1

    def test_suffix_nd(self):
        assert _parse_quarter("2ND QUARTER") == 2

    def test_suffix_rd(self):
        assert _parse_quarter("3RD QTR") == 3

    def test_suffix_th(self):
        assert _parse_quarter("4TH QUARTER") == 4

    def test_case_insensitive(self):
        assert _parse_quarter("qtr 2") == 2

    def test_no_match(self):
        assert _parse_quarter("no quarter here") is None

    def test_empty(self):
        assert _parse_quarter("") is None


# ---------------------------------------------------------------------------
# Down & distance regex tests
# ---------------------------------------------------------------------------


class TestParseDownDistance:
    def test_standard(self):
        assert _parse_down_distance("2ND & 7") == (2, 7)

    def test_goal(self):
        assert _parse_down_distance("3RD & GOAL") == (3, "GOAL")

    def test_and_word(self):
        assert _parse_down_distance("1ST AND 10") == (1, 10)

    def test_fourth_down(self):
        assert _parse_down_distance("4TH & 1") == (4, 1)

    def test_case_insensitive(self):
        assert _parse_down_distance("2nd & goal") == (2, "GOAL")

    def test_no_match(self):
        assert _parse_down_distance("nothing here") == (None, None)

    def test_empty(self):
        assert _parse_down_distance("") == (None, None)


# ---------------------------------------------------------------------------
# Clock regex tests
# ---------------------------------------------------------------------------


class TestParseClock:
    def test_standard(self):
        assert _parse_clock("12:45") == "12:45"

    def test_single_digit_minute(self):
        assert _parse_clock("5:03") == "5:03"

    def test_within_text(self):
        assert _parse_clock("Q1 8:22 2ND & 5") == "8:22"

    def test_no_match(self):
        assert _parse_clock("no clock") is None

    def test_empty(self):
        assert _parse_clock("") is None


# ---------------------------------------------------------------------------
# Play number regex tests
# ---------------------------------------------------------------------------


class TestParsePlayNumber:
    def test_play_label(self):
        assert _parse_play_number("PLAY 42") == 42

    def test_hash_label(self):
        assert _parse_play_number("# 7") == 7

    def test_standalone_number_not_matched(self):
        """Standalone numbers should NOT match -- only labeled play numbers."""
        assert _parse_play_number("55") is None

    def test_case_insensitive(self):
        assert _parse_play_number("play 12") == 12

    def test_no_match(self):
        assert _parse_play_number("no play number here at all") is None

    def test_empty(self):
        assert _parse_play_number("") is None


# ---------------------------------------------------------------------------
# Yard line regex tests
# ---------------------------------------------------------------------------


class TestParseYardLine:
    def test_standard(self):
        assert _parse_yard_line("OPP 35") == "OPP 35"

    def test_team_name(self):
        assert _parse_yard_line("ALA 45") == "ALA 45"

    def test_own_side(self):
        assert _parse_yard_line("OWN 20") == "OWN 20"

    def test_no_match(self):
        assert _parse_yard_line("5") is None

    def test_empty(self):
        assert _parse_yard_line("") is None


# ---------------------------------------------------------------------------
# OCR integration: extract_situation_data
# ---------------------------------------------------------------------------


def _make_ocr_result(text_blocks: list[str]):
    """Build a PaddleOCR-shaped result from a list of text strings."""
    return [[[[[0, 0], [100, 0], [100, 30], [0, 30]], (text, 0.95)] for text in text_blocks]]


class TestExtractSituationData:
    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_full_extraction(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = _make_ocr_result(
            ["Q2", "3RD & 7", "12:30", "PLAY 15", "OPP 40"]
        )
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert result.quarter == 2
        assert result.down == 3
        assert result.distance == 7
        assert result.clock == "12:30"
        assert result.play_number == 15
        assert result.yard_line == "OPP 40"
        assert "Q2" in result.raw_ocr_text
        assert "3RD & 7" in result.raw_ocr_text

    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_partial_extraction(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = _make_ocr_result(["Q1", "5:00"])
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert result.quarter == 1
        assert result.clock == "5:00"
        assert result.down is None
        assert result.distance is None
        assert result.play_number is None

    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_empty_ocr(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[]]
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert result.raw_ocr_text == ""
        assert result.quarter is None
        assert result.down is None

    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_none_ocr_result(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = None
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert result.raw_ocr_text == ""

    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_ocr_exception(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.side_effect = RuntimeError("OCR engine crashed")
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert isinstance(result, SituationData)
        assert result.raw_ocr_text == ""

    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_garbage_text(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = _make_ocr_result(["xxxx", "!@#$", "????"])
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert result.quarter is None
        assert result.down is None
        assert result.clock is None
        assert result.play_number is None
        assert len(result.raw_ocr_text) > 0

    @patch("src.film_parser.ocr_extract._get_ocr")
    def test_goal_line(self, mock_get_ocr):
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = _make_ocr_result(["1ST & GOAL", "Q4", "0:15"])
        mock_get_ocr.return_value = mock_ocr

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = extract_situation_data(frame)

        assert result.down == 1
        assert result.distance == "GOAL"
        assert result.quarter == 4
        assert result.clock == "0:15"


# ---------------------------------------------------------------------------
# extract_all_situation_data
# ---------------------------------------------------------------------------


class TestExtractAllSituationData:
    @patch("src.film_parser.ocr_extract.extract_situation_data")
    @patch("src.film_parser.ocr_extract.cv2")
    def test_processes_situation_segments(self, mock_cv2, mock_extract):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0
        mock_cap.read.return_value = (True, np.zeros((100, 200, 3), dtype=np.uint8))

        mock_extract.return_value = SituationData(
            quarter=1, down=2, distance=10, clock="10:00", raw_ocr_text="Q1 2ND & 10"
        )

        segments = [
            Segment(start_time=0.0, end_time=2.0, segment_type=SegmentType.SITUATION),
            Segment(start_time=2.0, end_time=5.0, segment_type=SegmentType.GAME_ACTION),
            Segment(start_time=5.0, end_time=7.0, segment_type=SegmentType.SITUATION),
        ]

        results = extract_all_situation_data("/fake/video.mp4", segments)

        assert len(results) == 2
        assert 0 in results
        assert 2 in results
        assert 1 not in results
        assert results[0].quarter == 1

    @patch("src.film_parser.ocr_extract.cv2")
    def test_video_open_failure(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = False

        segments = [
            Segment(start_time=0.0, end_time=2.0, segment_type=SegmentType.SITUATION),
        ]

        results = extract_all_situation_data("/fake/video.mp4", segments)
        assert results == {}

    @patch("src.film_parser.ocr_extract.extract_situation_data")
    @patch("src.film_parser.ocr_extract.cv2")
    def test_frame_read_failure(self, mock_cv2, mock_extract):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0
        mock_cap.read.return_value = (False, None)

        segments = [
            Segment(start_time=0.0, end_time=2.0, segment_type=SegmentType.SITUATION),
        ]

        results = extract_all_situation_data("/fake/video.mp4", segments)
        assert len(results) == 1
        assert results[0].raw_ocr_text == ""
        mock_extract.assert_not_called()

    @patch("src.film_parser.ocr_extract.cv2")
    def test_no_situation_segments(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0

        segments = [
            Segment(start_time=0.0, end_time=2.0, segment_type=SegmentType.GAME_ACTION),
            Segment(start_time=2.0, end_time=4.0, segment_type=SegmentType.UNCLASSIFIED),
        ]

        results = extract_all_situation_data("/fake/video.mp4", segments)
        assert results == {}
        mock_cap.release.assert_called_once()
