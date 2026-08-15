"""Tactic label preference: rule priority + exclusive groups."""

from __future__ import annotations

import os
import sys
import unittest
from typing import List

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.moveslist_model import MoveData
from app.services.best_move_ranking import detect_best_tactic, load_best_move_tactic_rules
from app.services.game_highlights.base_rule import GameHighlight, HighlightRule
from app.services.game_highlights.highlight_detector import prefer_tactic_type
from app.services.missed_tactic_ranking import (
    _synthetic_pv1_move,
    detect_pv1_tactic,
    load_missed_tactic_rules,
)
from tests.highlight_rules.helpers import moves_from_pgn


def _hl(rule_type: str, priority: int, *, is_white: bool = True) -> GameHighlight:
    return GameHighlight(
        move_number=10,
        is_white=is_white,
        move_notation="10. Ra5",
        description=rule_type,
        priority=priority,
        rule_type=rule_type,
    )


class _FixedRule(HighlightRule):
    """Rule that always returns the given highlights (for detector wiring tests)."""

    def __init__(self, highlights: List[GameHighlight]) -> None:
        super().__init__({})
        self._highlights = highlights

    def evaluate(self, move, context) -> List[GameHighlight]:
        return list(self._highlights)


class TestPreferTacticType(unittest.TestCase):
    def test_skewer_outranks_fork_by_priority(self) -> None:
        # Load order historically preferred fork first; priority must win.
        chosen = prefer_tactic_type([_hl("fork", 45), _hl("skewer", 46)])
        self.assertEqual(chosen, "skewer")

    def test_exclusive_group_keeps_skewer_even_if_fork_listed_first(self) -> None:
        chosen = prefer_tactic_type([_hl("fork", 45), _hl("skewer", 46), _hl("pin", 38)])
        self.assertEqual(chosen, "skewer")

    def test_higher_priority_among_non_exclusive(self) -> None:
        chosen = prefer_tactic_type([_hl("pin", 38), _hl("discovered_attack", 45)])
        self.assertEqual(chosen, "discovered_attack")

    def test_empty(self) -> None:
        self.assertEqual(prefer_tactic_type([]), "")


class TestDetectorsUsePreference(unittest.TestCase):
    def test_detect_pv1_prefers_skewer_over_earlier_fork_rule(self) -> None:
        fen = "2r3k1/1q6/8/5N2/8/8/8/4K3 w - - 0 10"
        prev = MoveData(move_number=9, black_move="a6", fen_black=fen)
        row = MoveData(move_number=10, white_move="Ke2", fen_white="dummy")
        board = chess.Board(fen)
        after = board.copy()
        after.push_san("Nd6")
        synth = _synthetic_pv1_move(
            row,
            is_white=True,
            pv1="Nd6",
            fen_after=after.fen(),
            capture="",
        )
        # Fork rule listed first (old behavior would return "fork").
        rules = [
            _FixedRule([_hl("fork", 45)]),
            _FixedRule([_hl("skewer", 46)]),
        ]
        kind = detect_pv1_tactic(
            [prev, row],
            1,
            is_white=True,
            synth=synth,
            fen_before=fen,
            tactic_rules=rules,
            opening_end=10,
            middlegame_end=30,
            good_move_max_cpl=50,
            inaccuracy_max_cpl=100,
            mistake_max_cpl=200,
        )
        self.assertEqual(kind, "skewer")

    def test_detect_best_prefers_skewer_over_earlier_fork_rule(self) -> None:
        moves = moves_from_pgn(
            "Nd6",
            starting_fen="2r3k1/1q6/8/5N2/8/8/8/4K3 w - - 0 10",
            analysis={10: {"white": {"cpl": "0", "assess": "Best Move"}}},
        )
        rules = [
            _FixedRule([_hl("fork", 45)]),
            _FixedRule([_hl("skewer", 46)]),
        ]
        kind = detect_best_tactic(
            moves,
            0,
            is_white=True,
            tactic_rules=rules,
            opening_end=10,
            middlegame_end=30,
            good_move_max_cpl=50,
            inaccuracy_max_cpl=100,
            mistake_max_cpl=200,
        )
        self.assertEqual(kind, "skewer")

    def test_quiet_fork_still_labels_as_fork(self) -> None:
        fen = "2r3k1/1q6/8/5N2/8/8/8/4K3 w - - 0 10"
        best_moves = moves_from_pgn(
            "Nd6",
            starting_fen=fen,
            analysis={10: {"white": {"cpl": "0", "assess": "Best Move", "eval": "3.00"}}},
        )
        kind = detect_best_tactic(
            best_moves,
            0,
            is_white=True,
            tactic_rules=load_best_move_tactic_rules(),
            opening_end=10,
            middlegame_end=30,
            good_move_max_cpl=50,
            inaccuracy_max_cpl=100,
            mistake_max_cpl=200,
        )
        self.assertEqual(kind, "fork")
        self.assertTrue(load_missed_tactic_rules())


if __name__ == "__main__":
    unittest.main()
