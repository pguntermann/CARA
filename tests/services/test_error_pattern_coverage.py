"""Game-coverage rules for player-stats error patterns."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.database_model import GameData
from app.models.moveslist_model import MoveData
from app.services.error_pattern_service import (
    ErrorPattern,
    ErrorPatternService,
    clamp_coverage_cutoff,
    filter_patterns_by_coverage,
)
from app.services.game_summary_service import CriticalMove


def _svc(**threshold_overrides) -> ErrorPatternService:
    thresholds = {
        "tactical_miss_count": 2,
        "opening_error_rate": 30.0,
        "high_cpl_threshold": 50.0,
        "missed_top3_threshold": 60.0,
        "inaccuracy_rate_threshold": 25.0,
        "winning_eval_threshold": 200.0,
        "losing_eval_threshold": -200.0,
    }
    thresholds.update(threshold_overrides)
    return ErrorPatternService(
        {
            "player_stats": {
                "error_patterns": {
                    "min_pattern_games": 2,
                    "thresholds": thresholds,
                }
            }
        }
    )


def _game(
    n: int,
    *,
    white: str = "Alice",
    black: str = "Bob",
    result: str = "1-0",
    eco: str = "",
) -> GameData:
    return GameData(n, white=white, black=black, result=result, eco=eco)


def _phase(**kwargs) -> SimpleNamespace:
    defaults = dict(moves=10, inaccuracies=0, mistakes=0, blunders=0)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _pstats(*, top3: float = 80.0, inaccuracies: int = 1, total_moves: int = 20, cpl: float = 20.0) -> SimpleNamespace:
    return SimpleNamespace(
        top3_move_percentage=top3,
        inaccuracies=inaccuracies,
        total_moves=total_moves,
        average_cpl=cpl,
    )


def _summary(
    *,
    white_stats=None,
    black_stats=None,
    white_opening=None,
    black_opening=None,
    evaluation_data=None,
    white_missed=None,
    black_missed=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        white_stats=white_stats or _pstats(),
        black_stats=black_stats or _pstats(),
        white_opening=white_opening or _phase(),
        black_opening=black_opening or _phase(),
        white_middlegame=_phase(blunders=0),
        black_middlegame=_phase(blunders=0),
        white_endgame=_phase(blunders=0),
        black_endgame=_phase(blunders=0),
        evaluation_data=list(evaluation_data or []),
        white_missed_tactics=list(white_missed or []),
        black_missed_tactics=list(black_missed or []),
    )


def _agg(*, top3: float = 70.0, inaccuracies: int = 10, total_moves: int = 100, cpl: float = 30.0) -> SimpleNamespace:
    return SimpleNamespace(
        player_stats=SimpleNamespace(
            top3_move_percentage=top3,
            inaccuracies=inaccuracies,
            total_moves=total_moves,
            average_cpl=cpl,
        ),
        opening_stats=_phase(blunders=1),
        middlegame_stats=_phase(blunders=0),
        endgame_stats=_phase(blunders=0),
    )


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


class TestCoverageHelpers(unittest.TestCase):
    def test_filter_keeps_patterns_at_or_above_cutoff(self) -> None:
        low = ErrorPattern("tactical_misses", "a", 2, 10.0, "low", [], game_coverage=10.0)
        high = ErrorPattern("tactical_misses", "b", 8, 40.0, "high", [], game_coverage=40.0)
        shown = filter_patterns_by_coverage([low, high], 25.0)
        self.assertEqual(shown, [high])

    def test_clamp_coverage_cutoff(self) -> None:
        self.assertEqual(clamp_coverage_cutoff(25), 25.0)
        self.assertEqual(clamp_coverage_cutoff(1), 5.0)
        self.assertEqual(clamp_coverage_cutoff(99), 95.0)
        self.assertEqual(clamp_coverage_cutoff("nope"), 25.0)


class TestMissedTop3Coverage(unittest.TestCase):
    def test_counts_games_below_top3_bar_not_career_average(self) -> None:
        games = [_game(i) for i in range(10)]
        summaries = [_summary(white_stats=_pstats(top3=80.0)) for _ in games]
        summaries[0] = _summary(white_stats=_pstats(top3=40.0))
        summaries[1] = _summary(white_stats=_pstats(top3=50.0))
        # Career average would fail a 60% bar, but only 2/10 games are actually bad.
        patterns = _svc()._detect_missed_top3_patterns(
            "Alice", games, summaries, _agg(top3=55.0)
        )
        self.assertEqual(len(patterns), 1)
        self.assertEqual(len(patterns[0].related_games), 2)
        self.assertAlmostEqual(patterns[0].game_coverage, 20.0)

    def test_single_bad_game_is_below_floor(self) -> None:
        games = [_game(1), _game(2)]
        summaries = [
            _summary(white_stats=_pstats(top3=40.0)),
            _summary(white_stats=_pstats(top3=90.0)),
        ]
        patterns = _svc()._detect_missed_top3_patterns(
            "Alice", games, summaries, _agg(top3=65.0)
        )
        self.assertEqual(patterns, [])


class TestInaccuracyCoverage(unittest.TestCase):
    def test_counts_games_over_inaccuracy_bar(self) -> None:
        games = [_game(i) for i in range(4)]
        summaries = [
            _summary(white_stats=_pstats(inaccuracies=8, total_moves=20)),  # 40%
            _summary(white_stats=_pstats(inaccuracies=8, total_moves=20)),
            _summary(white_stats=_pstats(inaccuracies=1, total_moves=20)),
            _summary(white_stats=_pstats(inaccuracies=1, total_moves=20)),
        ]
        patterns = _svc()._detect_consistent_inaccuracies(
            "Alice", games, summaries, _agg(inaccuracies=18, total_moves=80)
        )
        self.assertEqual(len(patterns), 1)
        self.assertEqual(len(patterns[0].related_games), 2)
        self.assertAlmostEqual(patterns[0].game_coverage, 50.0)


class TestHighCplNoCareerGate(unittest.TestCase):
    def test_emits_from_high_cpl_games_even_if_career_avg_is_low(self) -> None:
        games = [_game(i) for i in range(4)]
        summaries = [
            _summary(white_stats=_pstats(cpl=80.0)),
            _summary(white_stats=_pstats(cpl=70.0)),
            _summary(white_stats=_pstats(cpl=20.0)),
            _summary(white_stats=_pstats(cpl=15.0)),
        ]
        patterns = _svc()._detect_high_cpl_patterns(
            "Alice", games, summaries, _agg(cpl=40.0), None
        )
        self.assertEqual(len(patterns), 1)
        self.assertEqual(len(patterns[0].related_games), 2)
        self.assertAlmostEqual(patterns[0].game_coverage, 50.0)


class TestConversionOpportunityRate(unittest.TestCase):
    def test_coverage_uses_winning_games_not_all_games(self) -> None:
        games = [
            _game(1, result="0-1"),
            _game(2, result="0-1"),
            _game(3, result="1-0"),
            _game(4, result="1-0"),
            _game(5, result="1-0"),
            _game(6, result="1-0"),
            _game(7, result="1-0"),
            _game(8, result="1-0"),
        ]
        # First two: winning then failed. Next two: winning and converted. Rest: never winning.
        summaries = [
            _summary(evaluation_data=[(1, 250.0)]),
            _summary(evaluation_data=[(1, 300.0)]),
            _summary(evaluation_data=[(1, 250.0)]),
            _summary(evaluation_data=[(1, 250.0)]),
            _summary(evaluation_data=[(1, 0.0)]),
            _summary(evaluation_data=[(1, 10.0)]),
            _summary(evaluation_data=[(1, -20.0)]),
            _summary(evaluation_data=[(1, 50.0)]),
        ]
        patterns = _svc()._detect_conversion_issues("Alice", games, summaries)
        self.assertEqual(len(patterns), 1)
        # 2 failures / 4 winning games = 50%, not 2/8 = 25%.
        self.assertAlmostEqual(patterns[0].game_coverage, 50.0)
        self.assertEqual(len(patterns[0].related_games), 2)


class TestOpeningLossCoverage(unittest.TestCase):
    def test_related_games_are_losses_in_that_opening(self) -> None:
        games = [
            _game(1, result="0-1", eco="B20"),
            _game(2, result="0-1", eco="B20"),
            _game(3, result="1-0", eco="B20"),
            _game(4, result="1-0", eco="B20"),
        ]
        summaries = [
            _summary(white_opening=_phase(moves=10, inaccuracies=4, mistakes=0, blunders=0))
            for _ in games
        ]
        moves = [
            [
                MoveData(
                    1,
                    white_move="e4",
                    assess_white="Inaccuracy",
                    eco="B20",
                    opening_name="Sicilian",
                )
            ]
            for _ in games
        ]
        patterns = _svc()._detect_opening_error_patterns(
            "Alice", games, summaries, _agg(), moves
        )
        self.assertEqual(len(patterns), 1)
        self.assertEqual(len(patterns[0].related_games), 2)
        # Losses / games in this opening = 2/4.
        self.assertAlmostEqual(patterns[0].game_coverage, 50.0)
        self.assertTrue(all(g.result == "0-1" for g in patterns[0].related_games))

    def test_draws_do_not_count_as_losses(self) -> None:
        games = [
            _game(1, result="1/2-1/2", eco="B20"),
            _game(2, result="1/2-1/2", eco="B20"),
        ]
        summaries = [
            _summary(white_opening=_phase(moves=10, inaccuracies=5))
            for _ in games
        ]
        moves = [
            [
                MoveData(
                    1,
                    white_move="e4",
                    assess_white="Inaccuracy",
                    eco="B20",
                    opening_name="Sicilian",
                )
            ]
            for _ in games
        ]
        patterns = _svc()._detect_opening_error_patterns(
            "Alice", games, summaries, _agg(), moves
        )
        self.assertEqual(patterns, [])


class TestTacticalMissFloor(unittest.TestCase):
    def test_two_games_meet_default_floor(self) -> None:
        games = [_game(1), _game(2), _game(3)]
        summaries = [
            _summary(white_missed=[_miss(10, "fork")]),
            _summary(white_missed=[_miss(11, "fork")]),
            _summary(),
        ]
        patterns = _svc()._detect_tactical_miss_patterns("Alice", games, summaries)
        self.assertEqual(len(patterns), 1)
        self.assertAlmostEqual(patterns[0].game_coverage, 200.0 / 3.0, places=4)

    def test_one_game_is_omitted(self) -> None:
        games = [_game(1), _game(2)]
        summaries = [_summary(white_missed=[_miss(10, "fork")]), _summary()]
        patterns = _svc()._detect_tactical_miss_patterns("Alice", games, summaries)
        self.assertEqual(patterns, [])


if __name__ == "__main__":
    unittest.main()
