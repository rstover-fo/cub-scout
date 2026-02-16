"""Video frame sampling and utility functions for the film parser."""

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def sample_frame(video_path: str | Path, timestamp_sec: float) -> np.ndarray:
    """Extract a single frame at the given timestamp.

    Args:
        video_path: Path to the video file.
        timestamp_sec: Timestamp in seconds to extract the frame from.

    Returns:
        BGR image as a numpy array.

    Raises:
        ValueError: If the frame cannot be read at the given timestamp.
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_sec * 1000)
        ret, frame = cap.read()
        if not ret or frame is None:
            raise ValueError(f"Could not read frame at {timestamp_sec}s from {video_path}")
        return frame
    finally:
        cap.release()


def sample_frames(video_path: str | Path, timestamps: list[float]) -> list[np.ndarray]:
    """Batch extract frames at multiple timestamps.

    Opens the video capture once and seeks to each timestamp sequentially.

    Args:
        video_path: Path to the video file.
        timestamps: List of timestamps in seconds.

    Returns:
        List of BGR images as numpy arrays. Unreadable frames are skipped
        with a warning logged.
    """
    frames: list[np.ndarray] = []
    cap = cv2.VideoCapture(str(video_path))
    try:
        for ts in timestamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Skipping unreadable frame at %.3fs in %s", ts, video_path)
                continue
            frames.append(frame)
    finally:
        cap.release()
    return frames


def get_video_info(video_path: str | Path) -> dict:
    """Return basic video metadata.

    Args:
        video_path: Path to the video file.

    Returns:
        Dict with keys: duration (float seconds), fps (float),
        width (int), height (int), frame_count (int).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0.0
        return {
            "duration": duration,
            "fps": fps,
            "width": width,
            "height": height,
            "frame_count": frame_count,
        }
    finally:
        cap.release()


def format_timestamp(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS.mmm format.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted string like '00:01:23.456'.
    """
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
