"""State machine that groups classified segments into play triplets."""

import logging
from enum import Enum

from src.film_parser.models import (
    CameraAngle,
    GameMetadata,
    Play,
    PlayCatalog,
    QualityMetrics,
    Segment,
    SegmentType,
)

logger = logging.getLogger(__name__)


class _State(Enum):
    WAITING_SITUATION = "waiting_situation"
    GOT_SITUATION = "got_situation"
    GOT_SIDELINE = "got_sideline"


def assemble_plays(segments: list[Segment], game_metadata: GameMetadata) -> PlayCatalog:
    """Assemble classified segments into play triplets using a state machine.

    Each play is a triplet: SITUATION -> GAME_ACTION (sideline) -> GAME_ACTION (endzone).
    """
    plays: list[Play] = []
    state = _State.WAITING_SITUATION
    situation: Segment | None = None
    sideline: Segment | None = None
    orphaned = 0
    classified_situations = 0
    classified_game_actions = 0

    for seg in segments:
        if seg.segment_type == SegmentType.UNCLASSIFIED:
            logger.warning("Skipping unclassified segment at %.3f", seg.start_time)
            continue

        if seg.segment_type == SegmentType.SITUATION:
            classified_situations += 1
            if state == _State.GOT_SITUATION:
                logger.warning(
                    "Consecutive situation at %.3f — discarding previous situation",
                    seg.start_time,
                )
                orphaned += 1
            elif state == _State.GOT_SIDELINE:
                # Emit as doublet (no separate endzone clip detected)
                assert situation is not None
                assert sideline is not None
                play = Play(
                    play_number=len(plays) + 1,
                    situation=situation,
                    sideline=sideline,
                )
                plays.append(play)
                logger.debug(
                    "Emitting doublet play %d (no endzone cut detected)",
                    play.play_number,
                )
            situation = seg
            sideline = None
            state = _State.GOT_SITUATION
            continue

        if seg.segment_type == SegmentType.GAME_ACTION:
            classified_game_actions += 1
            if state == _State.WAITING_SITUATION:
                logger.warning(
                    "Game action at %.3f with no situation — orphaned",
                    seg.start_time,
                )
                orphaned += 1
                continue

            if state == _State.GOT_SITUATION:
                sideline = seg.model_copy(update={"camera_angle": CameraAngle.SIDELINE})
                state = _State.GOT_SIDELINE
                continue

            if state == _State.GOT_SIDELINE:
                endzone = seg.model_copy(update={"camera_angle": CameraAngle.ENDZONE})
                assert situation is not None
                assert sideline is not None
                play = Play(
                    play_number=len(plays) + 1,
                    situation=situation,
                    sideline=sideline,
                    endzone=endzone,
                )
                plays.append(play)
                situation = None
                sideline = None
                state = _State.WAITING_SITUATION

    # Handle trailing incomplete state
    if state == _State.GOT_SITUATION:
        orphaned += 1
    elif state == _State.GOT_SIDELINE:
        # Emit trailing doublet
        assert situation is not None
        assert sideline is not None
        play = Play(
            play_number=len(plays) + 1,
            situation=situation,
            sideline=sideline,
        )
        plays.append(play)

    quality = QualityMetrics(
        total_segments=len(segments),
        classified_situations=classified_situations,
        classified_game_actions=classified_game_actions,
        complete_triplets=len(plays),
        orphaned_segments=orphaned,
    )

    return PlayCatalog(
        game_metadata=game_metadata,
        plays=plays,
        quality_metrics=quality,
    )
