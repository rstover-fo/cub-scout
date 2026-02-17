"""Scene detection using PySceneDetect ContentDetector."""

import logging
from pathlib import Path

from scenedetect import ContentDetector, detect

from src.film_parser.models import Segment, SegmentType

logger = logging.getLogger(__name__)


def detect_scenes(
    video_path: str | Path,
    threshold: float = 27.0,
    min_scene_len: float = 0.5,
) -> list[Segment]:
    """Detect scene boundaries in a video file.

    Args:
        video_path: Path to the video file.
        threshold: ContentDetector threshold for scene change sensitivity.
        min_scene_len: Minimum scene duration in seconds. Shorter scenes are discarded.

    Returns:
        List of Segment objects for each detected scene.
    """
    scene_list = detect(str(video_path), ContentDetector(threshold=threshold))

    segments: list[Segment] = []
    for start_tc, end_tc in scene_list:
        start = start_tc.get_seconds()
        end = end_tc.get_seconds()
        if (end - start) < min_scene_len:
            continue
        segments.append(
            Segment(
                start_time=start,
                end_time=end,
                segment_type=SegmentType.UNCLASSIFIED,
            )
        )

    logger.info("Detected %d scenes in %s", len(segments), video_path)
    return segments
