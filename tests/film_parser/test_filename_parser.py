"""Tests for film filename parser."""

import pytest

from src.film_parser.filename_parser import parse_filename
from src.film_parser.models import Side


class TestParseFilenameValid:
    """Valid filename patterns."""

    def test_standard_format(self) -> None:
        result = parse_filename("MICHIGAN O VS. OKLAHOMA D.mp4", 2025)
        assert result.team == "Michigan"
        assert result.side == Side.OFFENSE
        assert result.opponent == "Oklahoma"
        assert result.opponent_side == Side.DEFENSE
        assert result.season_year == 2025
        assert result.filename == "MICHIGAN O VS. OKLAHOMA D.mp4"

    def test_lowercase_input(self) -> None:
        result = parse_filename("michigan o vs. oklahoma d.mp4", 2025)
        assert result.team == "Michigan"
        assert result.side == Side.OFFENSE
        assert result.opponent == "Oklahoma"
        assert result.opponent_side == Side.DEFENSE

    def test_missing_period_after_vs(self) -> None:
        result = parse_filename("MICHIGAN O VS OKLAHOMA D.mp4", 2025)
        assert result.team == "Michigan"
        assert result.opponent == "Oklahoma"

    def test_defense_vs_offense(self) -> None:
        result = parse_filename("TEXAS D VS. ALABAMA O.mp4", 2025)
        assert result.side == Side.DEFENSE
        assert result.opponent_side == Side.OFFENSE

    def test_multi_word_team_names(self) -> None:
        result = parse_filename("OHIO STATE O VS. PENN STATE D.mp4", 2025)
        assert result.team == "Ohio State"
        assert result.opponent == "Penn State"

    def test_path_components_stripped(self) -> None:
        result = parse_filename("/data/films/MICHIGAN O VS. OKLAHOMA D.mp4", 2025)
        assert result.team == "Michigan"
        assert result.opponent == "Oklahoma"

    def test_mixed_case(self) -> None:
        result = parse_filename("Michigan O vs. Oklahoma D.mp4", 2025)
        assert result.team == "Michigan"
        assert result.opponent == "Oklahoma"


class TestParseFilenameInvalid:
    """Invalid filename patterns that should raise ValueError."""

    def test_missing_side_indicator(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse filename"):
            parse_filename("MICHIGAN VS. OKLAHOMA D.mp4", 2025)

    def test_no_vs_separator(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse filename"):
            parse_filename("MICHIGAN O OKLAHOMA D.mp4", 2025)

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse filename"):
            parse_filename("", 2025)

    def test_only_extension(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse filename"):
            parse_filename(".mp4", 2025)

    def test_single_team(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse filename"):
            parse_filename("MICHIGAN O.mp4", 2025)
