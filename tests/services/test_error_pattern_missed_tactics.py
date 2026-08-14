"""Error-pattern detection for repeated missed tactics."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.database_model import GameData
from app.services.error_pattern_service import ErrorPatternService
from app.services.game_summary_service import CriticalMove, GameSummaryService, critical_moments_display_counts


def _svc(threshold: int = 3) -> ErrorPatternService:
    return ErrorPatternService(
        {
            "player_stats": {
                "error_patterns": {"thresholds": {"tactical_miss_count": threshold}}
            }
        }
    )


def _game(n: int, *, white: str = "Alice", black: str = "Bob") -> GameData:
    return GameData(n, white=white, black=black)


def _miss(move_number: int, kind: str) -> CriticalMove:
    return CriticalMove(
        move_number,
        f"{move_number}. Ke2",
        180.0,
        "Miss",
        "-2.00",
        best_move="Nd6",
        tactic_type=kind,
    )


def _summary(*, white=None, black=None) -> SimpleNamespace:
    return SimpleNamespace(
        white_missed_tactics=list(white or []),
        black_missed_tactics=list(black or []),
    )


class TestTacticalMissErrorPatterns(unittest.TestCase):
    def test_forks_above_threshold_link_to_plies(self) -> None:
        games = [_game(i) for i in range(4)]
        summaries = [
            _summary(white=[_miss(10, "fork")]),
            _summary(white=[_miss(12, "fork"), _miss(20, "capture")]),
            _summary(white=[_miss(8, "check")]),
            _summary(white=[_miss(15, "fork")]),
        ]
        patterns = _svc(threshold=3)._detect_tactical_miss_patterns(
            "Alice", games, summaries
        )
        self.assertEqual(len(patterns), 1)
        pattern = patterns[0]
        self.assertEqual(pattern.pattern_type, "tactical_misses")
        self.assertIn("forks", pattern.description)
        self.assertEqual(pattern.frequency, 3)
        self.assertEqual(len(pattern.related_games), 3)
        self.assertEqual(
            [ply for _game, ply in pattern.related_ref_plies],
            [19, 23, 29],
        )

    def test_below_threshold_is_omitted(self) -> None:
        games = [_game(1), _game(2)]
        summaries = [
            _summary(white=[_miss(10, "fork")]),
            _summary(white=[_miss(11, "fork")]),
        ]
        patterns = _svc(threshold=10)._detect_tactical_miss_patterns(
            "Alice", games, summaries
        )
        self.assertEqual(patterns, [])

    def test_mate_is_a_separate_pattern(self) -> None:
        games = [_game(i) for i in range(3)]
        summaries = [
            _summary(white=[_miss(10, "fork"), _miss(11, "mate")]),
            _summary(white=[_miss(12, "fork"), _miss(13, "mate")]),
            _summary(white=[_miss(14, "fork"), _miss(15, "mate")]),
        ]
        patterns = _svc(threshold=3)._detect_tactical_miss_patterns(
            "Alice", games, summaries
        )
        kinds = {p.description.split("(")[0].strip() for p in patterns}
        self.assertEqual(
            kinds,
            {"Frequently misses forks", "Frequently misses mates"},
        )

    def test_black_uses_black_missed_tactics(self) -> None:
        games = [_game(i) for i in range(3)]
        summaries = [
            _summary(black=[_miss(10, "pin")]),
            _summary(black=[_miss(11, "pin")]),
            _summary(black=[_miss(12, "pin")]),
        ]
        patterns = _svc(threshold=3)._detect_tactical_miss_patterns(
            "Bob", games, summaries
        )
        self.assertEqual(len(patterns), 1)
        self.assertIn("pins", patterns[0].description)
        self.assertEqual(patterns[0].related_ref_plies[0][1], 20)

    def test_white_misses_are_not_counted_for_black(self) -> None:
        games = [_game(i) for i in range(3)]
        summaries = [_summary(white=[_miss(10, "fork")]) for _ in games]
        patterns = _svc(threshold=3)._detect_tactical_miss_patterns(
            "Bob", games, summaries
        )
        self.assertEqual(patterns, [])


class TestMissedTacticsCountConfig(unittest.TestCase):
    def test_defaults_store_and_display_99(self) -> None:
        svc = GameSummaryService({})
        self.assertEqual(svc.missed_tactics_count, 99)
        self.assertEqual(svc.missed_tactics_display_count, 99)
        self.assertEqual(svc.worst_move_count, 3)
        self.assertEqual(svc.best_move_count, 3)
        self.assertEqual(critical_moments_display_counts({}), (3, 3, 99))

    def test_display_counts_read_config(self) -> None:
        config = {
            "ui": {
                "panels": {
                    "detail": {
                        "summary": {
                            "critical_moments": {
                                "worst_count": 5,
                                "best_count": 4,
                                "missed_tactics_display_count": 2,
                            }
                        }
                    }
                }
            }
        }
        self.assertEqual(critical_moments_display_counts(config), (5, 4, 2))


if __name__ == "__main__":
    unittest.main()
