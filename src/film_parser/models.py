"""Pydantic models for the film parser."""

from enum import Enum

from pydantic import BaseModel, computed_field


class SegmentType(str, Enum):
    """Type of video segment."""

    UNCLASSIFIED = "unclassified"
    SITUATION = "situation"
    GAME_ACTION = "game_action"


class Side(str, Enum):
    """Offensive or defensive film perspective."""

    OFFENSE = "O"
    DEFENSE = "D"


class CameraAngle(str, Enum):
    """Camera angle for game action segments."""

    SIDELINE = "sideline"
    ENDZONE = "endzone"


class Segment(BaseModel):
    """A detected scene boundary in the video."""

    start_time: float
    end_time: float
    segment_type: SegmentType = SegmentType.UNCLASSIFIED
    camera_angle: CameraAngle | None = None

    @computed_field
    @property
    def duration(self) -> float:
        return round(self.end_time - self.start_time, 3)


class SituationData(BaseModel):
    """Metadata extracted from a situation frame via OCR."""

    down: int | None = None
    distance: int | str | None = None  # int or "GOAL"
    yard_line: str | None = None
    quarter: int | None = None
    clock: str | None = None
    possession: str | None = None
    hash_mark: str | None = None
    play_number: int | None = None
    raw_ocr_text: str = ""


class GameMetadata(BaseModel):
    """Metadata parsed from the film filename."""

    team: str
    side: Side
    opponent: str
    opponent_side: Side
    season_year: int
    filename: str


class Play(BaseModel):
    """A single play — either a full triplet or doublet (no separate endzone)."""

    play_number: int
    situation: Segment
    sideline: Segment
    endzone: Segment | None = None
    situation_data: SituationData | None = None


class QualityMetrics(BaseModel):
    """Processing quality metrics for the play catalog."""

    total_segments: int = 0
    classified_situations: int = 0
    classified_game_actions: int = 0
    complete_triplets: int = 0
    orphaned_segments: int = 0
    ocr_success_rate: float = 0.0
    fields_extracted: dict[str, int] = {}


class ProcessingInfo(BaseModel):
    """Metadata about the processing run."""

    parser_version: str = "0.1.0"
    scene_threshold: float = 27.0
    processing_time_seconds: float = 0.0
    video_duration_seconds: float = 0.0
    video_resolution: str = ""
    video_fps: float = 0.0


class PlayCatalog(BaseModel):
    """Complete play catalog output for a single film file."""

    game_metadata: GameMetadata
    plays: list[Play] = []
    quality_metrics: QualityMetrics = QualityMetrics()
    processing_info: ProcessingInfo = ProcessingInfo()
