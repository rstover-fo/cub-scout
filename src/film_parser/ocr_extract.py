"""OCR extraction of situation data from Catapult film frames."""

import logging
import re
from pathlib import Path

import cv2
import numpy as np
from paddleocr import PaddleOCR

from src.film_parser.models import Segment, SegmentType, SituationData

logger = logging.getLogger(__name__)

_ocr: PaddleOCR | None = None


def _get_ocr() -> PaddleOCR:
    """Lazy singleton PaddleOCR instance."""
    global _ocr
    if _ocr is None:
        _ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _ocr


# Regex patterns for Catapult situation overlay
_QUARTER_PREFIX = re.compile(r"(?:Q|QTR)\s*([1-4])", re.IGNORECASE)
_QUARTER_SUFFIX = re.compile(r"([1-4])(?:ST|ND|RD|TH)\s*(?:QTR|QUARTER)", re.IGNORECASE)
_DOWN_DISTANCE = re.compile(r"([1-4])(?:ST|ND|RD|TH)\s*(?:&|AND)\s*(\d+|GOAL)", re.IGNORECASE)
_CLOCK = re.compile(r"(\d{1,2}:[0-5]\d)")
_PLAY_NUMBER_LABELED = re.compile(r"(?:PLAY|#)\s*(\d+)", re.IGNORECASE)
_YARD_LINE = re.compile(r"\b([A-Z]{2,})\s+(\d{1,2})\b", re.IGNORECASE)
_YARD_LINE_EXCLUDE = {"play", "qtr", "quarter", "q", "st", "nd", "rd", "th", "and", "vs"}


def _run_ocr(frame: np.ndarray) -> str:
    """Run PaddleOCR on a frame and return concatenated text."""
    ocr = _get_ocr()
    result = ocr.ocr(frame, cls=True)
    if not result or not result[0]:
        return ""
    texts = []
    for line in result[0]:
        if line and len(line) >= 2 and line[1]:
            texts.append(str(line[1][0]))
    return " ".join(texts)


def _parse_quarter(text: str) -> int | None:
    """Extract quarter number from OCR text."""
    match = _QUARTER_PREFIX.search(text)
    if match:
        return int(match.group(1))
    match = _QUARTER_SUFFIX.search(text)
    if match:
        return int(match.group(1))
    return None


def _parse_down_distance(text: str) -> tuple[int | None, int | str | None]:
    """Extract down and distance from OCR text."""
    match = _DOWN_DISTANCE.search(text)
    if not match:
        return None, None
    down = int(match.group(1))
    dist_raw = match.group(2).upper()
    distance: int | str = dist_raw if dist_raw == "GOAL" else int(dist_raw)
    return down, distance


def _parse_clock(text: str) -> str | None:
    """Extract game clock from OCR text."""
    match = _CLOCK.search(text)
    return match.group(1) if match else None


def _parse_play_number(text: str) -> int | None:
    """Extract play number from OCR text.

    Only matches labeled patterns like 'PLAY #N' or '#N'.
    Returns None if no labeled play number is found (missing data > wrong data).
    """
    match = _PLAY_NUMBER_LABELED.search(text)
    if match:
        return int(match.group(1))
    return None


def _parse_yard_line(text: str) -> str | None:
    """Extract yard line (e.g. 'OPP 35') from OCR text."""
    for match in _YARD_LINE.finditer(text):
        label = match.group(1).lower()
        if label not in _YARD_LINE_EXCLUDE:
            return f"{match.group(1)} {match.group(2)}"
    return None


def extract_situation_data(frame: np.ndarray) -> SituationData:
    """Extract situation metadata from a single frame via OCR.

    Never raises on OCR failure -- returns partial data with raw_ocr_text.
    """
    try:
        raw_text = _run_ocr(frame)
    except Exception:
        logger.warning("OCR failed on frame", exc_info=True)
        return SituationData(raw_ocr_text="")

    quarter = _parse_quarter(raw_text)
    if quarter is None:
        logger.debug("Could not parse quarter from: %s", raw_text)

    down, distance = _parse_down_distance(raw_text)
    if down is None:
        logger.debug("Could not parse down/distance from: %s", raw_text)

    clock = _parse_clock(raw_text)
    if clock is None:
        logger.debug("Could not parse clock from: %s", raw_text)

    play_number = _parse_play_number(raw_text)
    if play_number is None:
        logger.debug("Could not parse play number from: %s", raw_text)

    yard_line = _parse_yard_line(raw_text)
    if yard_line is None:
        logger.debug("Could not parse yard line from: %s", raw_text)

    return SituationData(
        quarter=quarter,
        down=down,
        distance=distance,
        clock=clock,
        play_number=play_number,
        yard_line=yard_line,
        raw_ocr_text=raw_text,
    )


def extract_all_situation_data(
    video_path: str | Path,
    segments: list[Segment],
) -> dict[int, SituationData]:
    """Extract situation data for all SITUATION segments in a video.

    Returns a dict mapping segment index -> SituationData.
    """
    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("Failed to open video: %s", video_path)
        return {}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    results: dict[int, SituationData] = {}
    total_fields = 0
    parsed_fields = 0

    try:
        for idx, segment in enumerate(segments):
            if segment.segment_type != SegmentType.SITUATION:
                continue

            mid_time = (segment.start_time + segment.end_time) / 2
            frame_num = int(mid_time * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()

            if not ret or frame is None:
                logger.warning("Could not read frame %d for segment %d", frame_num, idx)
                results[idx] = SituationData(raw_ocr_text="")
                continue

            data = extract_situation_data(frame)
            results[idx] = data

            field_count = 5  # quarter, down, distance, clock, play_number
            total_fields += field_count
            for val in [data.quarter, data.down, data.distance, data.clock, data.play_number]:
                if val is not None:
                    parsed_fields += 1
    finally:
        cap.release()

    success_rate = parsed_fields / total_fields if total_fields > 0 else 0.0
    logger.info(
        "OCR extraction complete: %d segments, %.1f%% field success rate",
        len(results),
        success_rate * 100,
    )

    return results
