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
        # Suppress PaddleOCR's verbose logging
        logging.getLogger("ppocr").setLevel(logging.WARNING)
        _ocr = PaddleOCR(use_angle_cls=True, lang="en")
    return _ocr


# Regex patterns for broadcast-style overlays (e.g. "2ND & 7")
_QUARTER_PREFIX = re.compile(r"(?:Q|QTR)\s*([1-4])", re.IGNORECASE)
_QUARTER_SUFFIX = re.compile(r"([1-4])(?:ST|ND|RD|TH)\s*(?:QTR|QUARTER)", re.IGNORECASE)
_DOWN_DISTANCE = re.compile(r"([1-4])(?:ST|ND|RD|TH)\s*(?:&|AND)\s*(\d+|GOAL)", re.IGNORECASE)
_CLOCK = re.compile(r"(\d{1,2}:[0-5]\d)")
_PLAY_NUMBER_LABELED = re.compile(r"(?:PLAY|#)\s*(\d+)", re.IGNORECASE)
_YARD_LINE = re.compile(r"\b([A-Z]{2,})\s+(\d{1,2})\b", re.IGNORECASE)
_YARD_LINE_EXCLUDE = {"play", "qtr", "quarter", "q", "st", "nd", "rd", "th", "and", "vs"}

# Catapult-specific pattern: "{QUARTER_ORD} DOWN TO GO BALL ON Main Clock {values}"
# Values section contains DOWN_ORD, DISTANCE, YARD_LINE, CLOCK in variable order.
_CATAPULT_HEADER = re.compile(
    r"([1-4])(?:ST|ND|RD|TH)\s+DOWN\s+TO\s+GO\s+BALL\s+ON\s+(?:Main\s+)?Clock\s+(.*)",
    re.IGNORECASE,
)
_ORDINAL = re.compile(r"([1-4])(?:ST|ND|RD|TH)", re.IGNORECASE)
_PLAIN_NUMBER = re.compile(r"\b(\d{1,2})\b")


def _run_ocr(frame: np.ndarray) -> str:
    """Run PaddleOCR on a frame and return concatenated text."""
    ocr = _get_ocr()
    result = ocr.predict(frame)
    if not result or not result[0]:
        return ""
    page = result[0]
    texts = page.get("rec_texts", []) if hasattr(page, "get") else getattr(page, "rec_texts", [])
    return " ".join(str(t) for t in texts if t)


def _parse_catapult_format(text: str) -> SituationData | None:
    """Parse Catapult-specific overlay format.

    Catapult OCR reads as:
      {TEAMS} {SCORES} {QUARTER_ORD} DOWN TO GO BALL ON Main Clock {values}

    The quarter ordinal appears before "DOWN". After "Main Clock", the values
    section contains the down ordinal, distance, yard line, and clock in
    variable order (ordinal can appear first or last).

    Returns SituationData if the Catapult format is detected, else None.
    """
    match = _CATAPULT_HEADER.search(text)
    if not match:
        return None

    quarter = int(match.group(1))
    values_text = match.group(2).strip()

    # Find clock (MM:SS)
    clock_match = _CLOCK.search(values_text)
    clock = clock_match.group(1) if clock_match else None

    # Find down ordinal in the values section
    down: int | None = None
    ord_match = _ORDINAL.search(values_text)
    if ord_match:
        down = int(ord_match.group(1))

    # Remove the clock and ordinal to isolate the two plain numbers (distance, yard_line)
    remaining = values_text
    if clock_match:
        remaining = remaining[: clock_match.start()] + remaining[clock_match.end() :]
    if ord_match:
        remaining = remaining[: ord_match.start()] + remaining[ord_match.end() :]

    # Extract the two remaining plain numbers: first = distance, second = yard_line
    numbers = _PLAIN_NUMBER.findall(remaining)
    distance: int | None = int(numbers[0]) if len(numbers) >= 1 else None
    yard_line: str | None = str(numbers[1]) if len(numbers) >= 2 else None

    # Try to extract play number from the full text (before the header)
    play_number: int | None = None
    pn_match = _PLAY_NUMBER_LABELED.search(text)
    if pn_match:
        play_number = int(pn_match.group(1))

    return SituationData(
        quarter=quarter,
        down=down,
        distance=distance,
        yard_line=yard_line,
        clock=clock,
        play_number=play_number,
        raw_ocr_text=text,
    )


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

    Tries Catapult-specific layout parser first, falls back to generic regexes.
    Never raises on OCR failure -- returns partial data with raw_ocr_text.
    """
    try:
        raw_text = _run_ocr(frame)
    except Exception:
        logger.warning("OCR failed on frame", exc_info=True)
        return SituationData(raw_ocr_text="")

    # Try Catapult-specific parser first (detects "DOWN TO GO BALL ON ... Clock")
    catapult_result = _parse_catapult_format(raw_text)
    if catapult_result is not None:
        return catapult_result

    # Fall back to generic broadcast-style regex parsing
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
