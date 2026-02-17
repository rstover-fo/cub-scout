"""Parse Catapult film filenames into GameMetadata."""

import logging
import re
from pathlib import Path

from src.film_parser.models import GameMetadata, Side

logger = logging.getLogger(__name__)

_FILENAME_PATTERN = re.compile(r"^(.+?)\s+(O|D)\s+VS\.?\s+(.+?)\s+(O|D)$", re.IGNORECASE)


def parse_filename(filename: str, season_year: int) -> GameMetadata:
    """Parse a Catapult film filename into GameMetadata.

    Expected pattern: ``{TEAM} {O|D} VS. {OPPONENT} {O|D}.mp4``

    Args:
        filename: Film filename (with or without path components).
        season_year: The season year for this film.

    Returns:
        GameMetadata populated from the parsed filename.

    Raises:
        ValueError: If the filename does not match the expected pattern.
    """
    stem = Path(filename).stem.strip()
    match = _FILENAME_PATTERN.match(stem)
    if not match:
        raise ValueError(
            f"Cannot parse filename '{filename}'. Expected format: 'TEAM O|D VS. OPPONENT O|D.mp4'"
        )

    team, side, opponent, opponent_side = match.groups()
    logger.debug(
        "Parsed '%s' -> team=%s side=%s opponent=%s opp_side=%s",
        filename,
        team,
        side,
        opponent,
        opponent_side,
    )

    return GameMetadata(
        team=team.strip().title(),
        side=Side(side.upper()),
        opponent=opponent.strip().title(),
        opponent_side=Side(opponent_side.upper()),
        season_year=season_year,
        filename=filename,
    )
