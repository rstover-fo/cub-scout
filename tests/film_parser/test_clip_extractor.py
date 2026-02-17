"""Tests for film_parser.clip_extractor — clip extraction and error handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.film_parser.clip_extractor import (
    extract_clip,
    extract_play_clips,
    extract_situation_frames,
)
from src.film_parser.models import (
    CameraAngle,
    GameMetadata,
    Play,
    PlayCatalog,
    Segment,
    SegmentType,
    Side,
)


def _make_catalog(play_count: int = 1) -> PlayCatalog:
    """Build a minimal PlayCatalog with N plays."""
    plays = []
    for i in range(play_count):
        base = float(i * 10)
        plays.append(
            Play(
                play_number=i + 1,
                situation=Segment(
                    start_time=base,
                    end_time=base + 2.0,
                    segment_type=SegmentType.SITUATION,
                ),
                sideline=Segment(
                    start_time=base + 2.0,
                    end_time=base + 6.0,
                    segment_type=SegmentType.GAME_ACTION,
                    camera_angle=CameraAngle.SIDELINE,
                ),
                endzone=Segment(
                    start_time=base + 6.0,
                    end_time=base + 10.0,
                    segment_type=SegmentType.GAME_ACTION,
                    camera_angle=CameraAngle.ENDZONE,
                ),
            )
        )
    return PlayCatalog(
        game_metadata=GameMetadata(
            team="Alabama",
            side=Side.OFFENSE,
            opponent="Georgia",
            opponent_side=Side.DEFENSE,
            season_year=2025,
            filename="test.mp4",
        ),
        plays=plays,
    )


class TestExtractClip:
    @patch("src.film_parser.clip_extractor.subprocess.run")
    def test_successful_extraction(self, mock_run: MagicMock, tmp_path: Path) -> None:
        output = tmp_path / "clip.mp4"
        result = extract_clip("/fake/video.mp4", 0.0, 5.0, output)
        assert result == output
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-ss" in cmd
        assert "-to" in cmd

    @patch("src.film_parser.clip_extractor.subprocess.run")
    def test_ffmpeg_failure_raises_runtime_error(self, mock_run: MagicMock, tmp_path: Path) -> None:
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"error msg")
        output = tmp_path / "clip.mp4"

        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            extract_clip("/fake/video.mp4", 0.0, 5.0, output)

    @patch("src.film_parser.clip_extractor.subprocess.run")
    def test_ffmpeg_not_found_raises_with_install_hint(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")
        output = tmp_path / "clip.mp4"

        with pytest.raises(RuntimeError, match="ffmpeg not found.*brew install ffmpeg"):
            extract_clip("/fake/video.mp4", 0.0, 5.0, output)


class TestExtractPlayClips:
    @patch("src.film_parser.clip_extractor.extract_clip")
    def test_extracts_three_clips_per_play(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        mock_extract.side_effect = lambda v, s, e, o: Path(o)
        catalog = _make_catalog(play_count=2)

        clips = extract_play_clips("/fake/video.mp4", catalog, tmp_path)

        # 2 plays * 3 segments each = 6 clips
        assert len(clips) == 6
        assert mock_extract.call_count == 6

    @patch("src.film_parser.clip_extractor.extract_clip")
    def test_continues_on_runtime_error(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        # First call fails, rest succeed
        mock_extract.side_effect = [
            RuntimeError("ffmpeg error"),
            Path("clip2.mp4"),
            Path("clip3.mp4"),
        ]
        catalog = _make_catalog(play_count=1)

        clips = extract_play_clips("/fake/video.mp4", catalog, tmp_path)

        # 1 failed + 2 succeeded = 2 clips
        assert len(clips) == 2
        assert mock_extract.call_count == 3

    @patch("src.film_parser.clip_extractor.extract_clip")
    def test_all_failures_returns_empty(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        mock_extract.side_effect = RuntimeError("ffmpeg error")
        catalog = _make_catalog(play_count=1)

        clips = extract_play_clips("/fake/video.mp4", catalog, tmp_path)

        assert len(clips) == 0

    @patch("src.film_parser.clip_extractor.extract_clip")
    def test_creates_output_dir(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        mock_extract.side_effect = lambda v, s, e, o: Path(o)
        catalog = _make_catalog(play_count=1)
        out_dir = tmp_path / "new_subdir" / "clips"

        extract_play_clips("/fake/video.mp4", catalog, out_dir)

        assert out_dir.exists()


class TestExtractSituationFrames:
    @patch("src.film_parser.clip_extractor.cv2")
    def test_extracts_one_frame_per_play(self, mock_cv2: MagicMock, tmp_path: Path) -> None:
        import numpy as np

        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cv2.CAP_PROP_POS_MSEC = 0
        mock_cap.read.return_value = (True, np.zeros((100, 200, 3), dtype=np.uint8))

        catalog = _make_catalog(play_count=2)

        frames = extract_situation_frames("/fake/video.mp4", catalog, tmp_path)

        assert len(frames) == 2
        mock_cap.release.assert_called_once()

    @patch("src.film_parser.clip_extractor.cv2")
    def test_skips_unreadable_frames(self, mock_cv2: MagicMock, tmp_path: Path) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cv2.CAP_PROP_POS_MSEC = 0
        mock_cap.read.return_value = (False, None)

        catalog = _make_catalog(play_count=2)

        frames = extract_situation_frames("/fake/video.mp4", catalog, tmp_path)

        assert len(frames) == 0
        mock_cap.release.assert_called_once()

    @patch("src.film_parser.clip_extractor.cv2")
    def test_video_open_failure_raises(self, mock_cv2: MagicMock, tmp_path: Path) -> None:
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = False

        catalog = _make_catalog(play_count=1)

        with pytest.raises(RuntimeError, match="Cannot open video"):
            extract_situation_frames("/fake/video.mp4", catalog, tmp_path)

    @patch("src.film_parser.clip_extractor.cv2")
    def test_continues_on_runtime_error(self, mock_cv2: MagicMock, tmp_path: Path) -> None:
        import numpy as np

        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cv2.CAP_PROP_POS_MSEC = 0
        # First read raises RuntimeError, second succeeds
        mock_cap.read.side_effect = [
            RuntimeError("cv2 error"),
            (True, np.zeros((100, 200, 3), dtype=np.uint8)),
        ]

        catalog = _make_catalog(play_count=2)

        frames = extract_situation_frames("/fake/video.mp4", catalog, tmp_path)

        # First play errored, second succeeded
        assert len(frames) == 1
        mock_cap.release.assert_called_once()
