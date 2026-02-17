"""Classify video segments as SITUATION or GAME_ACTION using OpenCV heuristics.

Calibrated against Catapult All-22 exports where situation frames are scoreboard
graphics with large black regions (~66% of pixels), while game action frames are
live field footage (<1% black pixels).
"""

import logging
from pathlib import Path

import cv2
import numpy as np

from src.film_parser.models import Segment, SegmentType
from src.film_parser.utils import sample_frames

logger = logging.getLogger(__name__)

# Default threshold: fraction of pixels below brightness 30 (out of 255).
# Situation frames: ~0.66 (scoreboard graphics on black background)
# Game action frames: ~0.004 (live field footage)
# Threshold of 0.20 gives wide separation margin.
DEFAULT_BLACK_RATIO_THRESHOLD = 0.20


def _compute_frame_features(frame: np.ndarray) -> dict[str, float]:
    """Compute visual features from a single BGR frame.

    Returns:
        Dict with color_variance, edge_density, and black_ratio.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    return {
        "color_variance": float(np.var(frame)),
        "edge_density": float(np.count_nonzero(edges) / edges.size),
        "black_ratio": float(np.sum(gray < 30) / gray.size),
    }


def classify_segment(
    video_path: str | Path,
    segment: Segment,
    black_ratio_threshold: float = DEFAULT_BLACK_RATIO_THRESHOLD,
) -> SegmentType:
    """Classify a single segment as SITUATION or GAME_ACTION.

    Samples 3 evenly-spaced frames (25%, 50%, 75% of duration) and uses
    majority vote on black pixel ratio to classify.

    Situation frames (Catapult scoreboard graphics) have ~66% black pixels.
    Game action frames (live field footage) have <1% black pixels.
    """
    duration = segment.end_time - segment.start_time
    timestamps = [segment.start_time + duration * frac for frac in (0.25, 0.50, 0.75)]
    frames = sample_frames(video_path, timestamps)

    if len(frames) < 2:
        return SegmentType.GAME_ACTION

    situation_votes = 0
    for frame in frames:
        features = _compute_frame_features(frame)
        if features["black_ratio"] > black_ratio_threshold:
            situation_votes += 1

    if situation_votes > len(frames) / 2:
        return SegmentType.SITUATION
    return SegmentType.GAME_ACTION


def _classify_segment_with_cap(
    cap: cv2.VideoCapture,
    segment: Segment,
    black_ratio_threshold: float = DEFAULT_BLACK_RATIO_THRESHOLD,
) -> SegmentType:
    """Classify a segment using a pre-opened video capture (batch optimization)."""
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
    for frame in frames:
        features = _compute_frame_features(frame)
        if features["black_ratio"] > black_ratio_threshold:
            situation_votes += 1

    if situation_votes > len(frames) / 2:
        return SegmentType.SITUATION
    return SegmentType.GAME_ACTION


def classify_segments(video_path: str | Path, segments: list[Segment]) -> list[Segment]:
    """Classify all segments and return updated copies.

    Opens the video capture once and reuses it for all segments.
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
