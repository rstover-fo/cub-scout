"""FFmpeg stream-copy clip extraction and frame capture."""

import logging
import subprocess
from pathlib import Path

import cv2

from src.film_parser.models import PlayCatalog, Segment

logger = logging.getLogger(__name__)


def extract_clip(
    video_path: str | Path,
    start_sec: float,
    end_sec: float,
    output_path: str | Path,
) -> Path:
    """Extract a clip from video using ffmpeg stream copy (no re-encode).

    Args:
        video_path: Path to the source video file.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.
        output_path: Path for the output clip.

    Returns:
        Path to the created clip file.

    Raises:
        RuntimeError: If ffmpeg fails.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-to",
        str(end_sec),
        "-i",
        str(video_path),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as e:
        raise RuntimeError("ffmpeg not found. Install via: brew install ffmpeg") from e
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else "unknown error"
        raise RuntimeError(f"ffmpeg failed: {stderr}") from e

    return output_path


def extract_play_clips(
    video_path: str | Path,
    play_catalog: PlayCatalog,
    output_dir: str | Path,
) -> list[Path]:
    """Extract situation, sideline, and endzone clips for every play.

    Args:
        video_path: Path to the source video file.
        play_catalog: Catalog containing plays with segment timestamps.
        output_dir: Directory to write clip files into.

    Returns:
        List of paths to all created clip files.
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    total = len(play_catalog.plays)

    for i, play in enumerate(play_catalog.plays, start=1):
        logger.info("Extracting clips for play %d/%d (play_number=%d)", i, total, play.play_number)

        segments: list[tuple[str, Segment]] = [
            ("situation", play.situation),
            ("sideline", play.sideline),
        ]
        if play.endzone is not None:
            segments.append(("endzone", play.endzone))

        for label, segment in segments:
            filename = f"play_{play.play_number:03d}_{label}.mp4"
            out_path = output_dir / filename
            try:
                clip_path = extract_clip(video_path, segment.start_time, segment.end_time, out_path)
                created.append(clip_path)
            except RuntimeError:
                logger.warning(
                    "Failed to extract %s clip for play %d, skipping",
                    label,
                    play.play_number,
                    exc_info=True,
                )

    logger.info("Extracted %d clips to %s", len(created), output_dir)
    return created


def extract_situation_frames(
    video_path: str | Path,
    play_catalog: PlayCatalog,
    output_dir: str | Path,
) -> list[Path]:
    """Extract a single frame image from the midpoint of each situation segment.

    Args:
        video_path: Path to the source video file.
        play_catalog: Catalog containing plays with situation timestamps.
        output_dir: Directory to write frame images into.

    Returns:
        List of paths to all created PNG files.
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    created: list[Path] = []

    try:
        for play in play_catalog.plays:
            try:
                mid_sec = (play.situation.start_time + play.situation.end_time) / 2
                cap.set(cv2.CAP_PROP_POS_MSEC, mid_sec * 1000)

                ret, frame = cap.read()
                if not ret:
                    logger.warning(
                        "Failed to read frame at %.2fs for play %d", mid_sec, play.play_number
                    )
                    continue

                filename = f"play_{play.play_number:03d}_situation.png"
                out_path = output_dir / filename
                cv2.imwrite(str(out_path), frame)
                created.append(out_path)
            except RuntimeError:
                logger.warning(
                    "Failed to extract situation frame for play %d, skipping",
                    play.play_number,
                    exc_info=True,
                )
    finally:
        cap.release()

    logger.info("Extracted %d situation frames to %s", len(created), output_dir)
    return created
