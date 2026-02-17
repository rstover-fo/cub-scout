"""Classify video segments as SITUATION or GAME_ACTION using OpenCV heuristics.

Calibrated against Catapult All-22 exports across 10 games. Situation frames are
scoreboard/title card graphics with elevated black pixel ratios compared to live
field footage. The black_ratio varies by game (0.08–0.66 for situations, <0.04
for game action), so we use both a pixel threshold and a duration guard.

Duration guard: situation title cards are consistently 1–8 seconds across all
games tested, while game action segments are 10–30+ seconds.
"""

import logging
from pathlib import Path

import cv2
import numpy as np

from src.film_parser.models import Segment, SegmentType, SituationData
from src.film_parser.utils import sample_frames

logger = logging.getLogger(__name__)

# Default threshold: fraction of pixels below brightness 30 (out of 255).
# Situation frame black_ratio varies across Catapult exports:
#   Kent State: ~0.66, LSU: ~0.66, Alabama: 0.09–0.60,
#   Tennessee: 0.07–0.71, South Carolina: 0.05–0.09, Texas: 0.04–0.14
# Game action frames are consistently < 0.02 across all games.
# Threshold of 0.04 provides separation with duration guard as safety net.
DEFAULT_BLACK_RATIO_THRESHOLD = 0.04

# Duration bounds for situation segments (seconds).
# Situation title cards are 1–8s across all tested games.
# Game action segments are 10–30+s; transitions are <1s.
MIN_SITUATION_DURATION = 1.0
MAX_SITUATION_DURATION = 8.0

# Post-OCR refinement: short segments with no OCR text are likely dark
# transition frames, not real situation cards. Real short situations (e.g.
# Temple at 1.2s) contain readable text; dark transitions do not.
MAX_DURATION_FOR_OCR_CHECK = 2.5


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

    Applies a duration guard: situation title cards (both digital overlays and
    in-stadium scoreboard camera shots) are consistently 1–8 seconds.
    """
    duration = segment.end_time - segment.start_time

    # Duration guard: situation title cards are 1–8 seconds
    if duration < MIN_SITUATION_DURATION or duration > MAX_SITUATION_DURATION:
        return SegmentType.GAME_ACTION

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
    """Classify a segment using a pre-opened video capture (batch optimization).

    Applies a duration guard: segments outside [1.0, 8.0] seconds are always
    classified as GAME_ACTION, since situation title cards consistently fall
    within this range across all tested Catapult exports.
    """
    duration = segment.end_time - segment.start_time

    # Duration guard: situation title cards are 1–8 seconds
    if duration < MIN_SITUATION_DURATION or duration > MAX_SITUATION_DURATION:
        return SegmentType.GAME_ACTION

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


def refine_classification(
    segments: list[Segment],
    ocr_results: dict[int, SituationData],
) -> list[Segment]:
    """Post-OCR refinement: reclassify false situation segments.

    Some Catapult exports (e.g. Michigan) have brief (~1-2s) dark transition
    frames between plays that pass the black_ratio threshold but contain no
    scoreboard text. Real short situations (e.g. Temple at 1.2s) produce
    readable OCR text. This function downgrades short situations with
    completely empty OCR to GAME_ACTION.

    Args:
        segments: Classified segments (output of classify_segments).
        ocr_results: OCR extraction results keyed by segment index.

    Returns:
        Updated segment list with false situations reclassified.
    """
    refined = []
    reclassified = 0

    for idx, seg in enumerate(segments):
        if (
            seg.segment_type == SegmentType.SITUATION
            and (seg.end_time - seg.start_time) < MAX_DURATION_FOR_OCR_CHECK
        ):
            ocr_data = ocr_results.get(idx)
            has_text = ocr_data is not None and ocr_data.raw_ocr_text.strip() != ""
            if not has_text:
                refined.append(seg.model_copy(update={"segment_type": SegmentType.GAME_ACTION}))
                reclassified += 1
                continue

        refined.append(seg)

    if reclassified > 0:
        logger.info(
            "Post-OCR refinement: reclassified %d short empty situations as game action",
            reclassified,
        )

    return refined
