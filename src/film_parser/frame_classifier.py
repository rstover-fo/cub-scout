"""Classify video segments as SITUATION or GAME_ACTION using OpenCV heuristics."""

import logging
from pathlib import Path

import cv2
import numpy as np

from src.film_parser.models import Segment, SegmentType
from src.film_parser.utils import sample_frames

logger = logging.getLogger(__name__)


def _compute_frame_features(frame: np.ndarray) -> dict[str, float]:
    """Compute visual features from a single BGR frame.

    Args:
        frame: BGR image as numpy array.

    Returns:
        Dict with color_variance and edge_density.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    return {
        "color_variance": float(np.var(frame)),
        "edge_density": float(np.count_nonzero(edges) / edges.size),
    }


def classify_segment(
    video_path: str | Path,
    segment: Segment,
    color_var_threshold: float = 500.0,
    edge_density_threshold: float = 0.15,
    motion_threshold: float = 2.0,
) -> SegmentType:
    """Classify a single segment as SITUATION or GAME_ACTION.

    Samples 3 evenly-spaced frames (25%, 50%, 75% of duration) and uses
    color variance, edge density, and inter-frame motion to decide.

    Args:
        video_path: Path to the video file.
        segment: Segment with start_time and end_time.
        color_var_threshold: Max color variance for SITUATION.
        edge_density_threshold: Min edge density for SITUATION.
        motion_threshold: Max inter-frame motion for SITUATION.

    Returns:
        SegmentType.SITUATION or SegmentType.GAME_ACTION.
    """
    duration = segment.end_time - segment.start_time
    timestamps = [segment.start_time + duration * frac for frac in (0.25, 0.50, 0.75)]
    frames = sample_frames(video_path, timestamps)

    if len(frames) < 2:
        return SegmentType.GAME_ACTION

    situation_votes = 0
    for i, frame in enumerate(frames):
        features = _compute_frame_features(frame)

        motion = 0.0
        if i > 0:
            motion = float(np.mean(np.abs(frame.astype(float) - frames[i - 1].astype(float))))

        is_situation = (
            features["color_variance"] < color_var_threshold
            and features["edge_density"] > edge_density_threshold
            and motion < motion_threshold
        )
        if is_situation:
            situation_votes += 1

    majority = len(frames) / 2
    if situation_votes > majority:
        return SegmentType.SITUATION
    return SegmentType.GAME_ACTION


def _classify_segment_with_cap(
    cap: cv2.VideoCapture,
    segment: Segment,
    color_var_threshold: float = 500.0,
    edge_density_threshold: float = 0.15,
    motion_threshold: float = 2.0,
) -> SegmentType:
    """Classify a single segment using a pre-opened video capture.

    Internal helper for batch classification -- avoids re-opening the video per segment.
    """
    duration = segment.end_time - segment.start_time
    timestamps = [segment.start_time + duration * frac for frac in (0.25, 0.50, 0.75)]

    frames: list[np.ndarray] = []
    for ts in timestamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    if len(frames) < 2:
        return SegmentType.GAME_ACTION

    situation_votes = 0
    for i, frame in enumerate(frames):
        features = _compute_frame_features(frame)

        motion = 0.0
        if i > 0:
            motion = float(np.mean(np.abs(frame.astype(float) - frames[i - 1].astype(float))))

        is_situation = (
            features["color_variance"] < color_var_threshold
            and features["edge_density"] > edge_density_threshold
            and motion < motion_threshold
        )
        if is_situation:
            situation_votes += 1

    majority = len(frames) / 2
    if situation_votes > majority:
        return SegmentType.SITUATION
    return SegmentType.GAME_ACTION


def classify_segments(video_path: str | Path, segments: list[Segment]) -> list[Segment]:
    """Classify all segments and return updated copies.

    Opens the video capture once and reuses it for all segments (optimized batch path).

    Args:
        video_path: Path to the video file.
        segments: List of segments to classify.

    Returns:
        New list of Segment objects with segment_type set.
    """
    classified = []
    situation_count = 0
    game_action_count = 0

    cap = cv2.VideoCapture(str(video_path))
    try:
        for seg in segments:
            seg_type = _classify_segment_with_cap(cap, seg)
            updated = seg.model_copy(update={"segment_type": seg_type})
            classified.append(updated)

            if seg_type == SegmentType.SITUATION:
                situation_count += 1
            else:
                game_action_count += 1
    finally:
        cap.release()

    logger.info(
        "Classified %d segments: %d situations, %d game actions",
        len(segments),
        situation_count,
        game_action_count,
    )
    return classified
