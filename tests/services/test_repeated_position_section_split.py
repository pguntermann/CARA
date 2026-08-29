"""Repeated same-position patterns are separate from Error Patterns coverage filtering."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.database_model import GameData
from app.models.moveslist_model import MoveData
from app.services.error_pattern_service import (
    ErrorPatternService,
    filter_patterns_by_coverage,
)


def _svc() -> ErrorPatternService:
    return ErrorPatternService(
        {
            "player_stats": {
                "error_patterns": {
                    "min_pattern_games": 2,
                    "thresholds": {
                        "repeated_position_min_games_blunder": 2,
                        "repeated_position_min_games_mistake": 2,
                        "repeated_position_min_games_miss": 2,
                        "repeated_position_min_games_inaccuracy": 2,
                    },
                }
            }
        }
    )


def _game(gid: int, white: str = "Alice", black: str = "Bob") -> GameData:
    return GameData(gid, white=white, black=black, result="1-0")


def _white_blunder_moves(fen_before: str) -> list[MoveData]:
    # First white move uses start FEN as fen_before when prev is None.
    m = MoveData(1)
    m.white_move = "e4"
    m.assess_white = "Blunder"
    m.fen_black = fen_before
    return [m]


class TestRepeatedPositionSectionSplit(unittest.TestCase):
    def test_detect_error_patterns_excludes_repeated_position(self) -> None:
        svc = _svc()
        games = [_game(1), _game(2)]
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        precomputed = [_white_blunder_moves(fen), _white_blunder_moves(fen)]
        # Empty summaries / zero aggregated stats → no other patterns, and repeated not included.
        patterns = svc.detect_error_patterns(
            "Alice",
            games,
            aggregated_stats=None,
            game_summaries=[],
            precomputed_moves=precomputed,
        )
        self.assertEqual(patterns, [])

    def test_detect_repeated_position_patterns_finds_blunders(self) -> None:
        svc = _svc()
        # 10 games so two matching occurrences → 20% coverage (below default 25% slider).
        games = [_game(i) for i in range(10)]
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        precomputed: list = [None] * 10
        precomputed[0] = _white_blunder_moves(fen)
        precomputed[1] = _white_blunder_moves(fen)
        patterns = svc.detect_repeated_position_patterns(
            "Alice", games, precomputed_moves=precomputed
        )
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].pattern_type, "repeated_blunders_same_position")
        self.assertAlmostEqual(patterns[0].game_coverage, 20.0)
        # Would be hidden by the Error Patterns coverage slider…
        filtered = filter_patterns_by_coverage(patterns, 25.0)
        self.assertEqual(filtered, [])
        # …but the dedicated section shows them unfiltered.
        self.assertEqual(len(patterns), 1)

if __name__ == "__main__":
    unittest.main()
