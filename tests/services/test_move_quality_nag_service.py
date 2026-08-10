"""Unit tests for MoveQualityNagService."""

from __future__ import annotations

import io
import unittest

import chess.pgn

from app.models.database_model import GameData
from app.models.moveslist_model import MoveData
from app.services.move_quality_nag_service import (
    ASSESSMENT_TO_QUALITY_NAG,
    DEFAULT_MOVE_QUALITY_NAG_MAPPING,
    QUALITY_NAGS,
    MoveQualityNagService,
    default_move_quality_nag_mapping,
    nag_for_assessment,
    normalize_move_quality_nag_mapping,
)


class TestNagForAssessment(unittest.TestCase):
    def test_mapped_assessments(self):
        self.assertEqual(nag_for_assessment("Brilliant"), chess.pgn.NAG_BRILLIANT_MOVE)
        self.assertEqual(nag_for_assessment("Inaccuracy"), chess.pgn.NAG_DUBIOUS_MOVE)
        self.assertEqual(nag_for_assessment("Mistake"), chess.pgn.NAG_MISTAKE)
        self.assertEqual(nag_for_assessment("Miss"), chess.pgn.NAG_BLUNDER)
        self.assertEqual(nag_for_assessment("Blunder"), chess.pgn.NAG_BLUNDER)

    def test_brilliant_with_suffix(self):
        self.assertEqual(
            nag_for_assessment("Brilliant (3,4,5)"), chess.pgn.NAG_BRILLIANT_MOVE
        )

    def test_best_good_and_book_write_nothing_by_default(self):
        self.assertIsNone(nag_for_assessment("Best Move"))
        self.assertIsNone(nag_for_assessment("Good Move"))
        self.assertIsNone(nag_for_assessment("Book Move"))
        self.assertIsNone(nag_for_assessment(""))
        self.assertIsNone(nag_for_assessment(None))
        # Best Move keeps ! assigned when disabled so re-enabling is one click.
        self.assertEqual(
            DEFAULT_MOVE_QUALITY_NAG_MAPPING["Best Move"]["nag"],
            chess.pgn.NAG_GOOD_MOVE,
        )
        self.assertFalse(DEFAULT_MOVE_QUALITY_NAG_MAPPING["Best Move"]["enabled"])

    def test_mapping_table_complete(self):
        self.assertEqual(
            set(ASSESSMENT_TO_QUALITY_NAG),
            {"Brilliant", "Inaccuracy", "Mistake", "Miss", "Blunder"},
        )

    def test_custom_mapping_and_disabled(self):
        mapping = default_move_quality_nag_mapping()
        mapping["Best Move"] = {"enabled": False, "nag": 1}
        mapping["Good Move"] = {"enabled": True, "nag": chess.pgn.NAG_GOOD_MOVE}
        mapping["Blunder"] = {"enabled": True, "nag": chess.pgn.NAG_MISTAKE}
        self.assertIsNone(nag_for_assessment("Best Move", mapping))
        self.assertEqual(nag_for_assessment("Good Move", mapping), chess.pgn.NAG_GOOD_MOVE)
        self.assertEqual(nag_for_assessment("Blunder", mapping), chess.pgn.NAG_MISTAKE)

    def test_normalize_clamps_invalid_nag(self):
        raw = {"Mistake": {"enabled": True, "nag": 99}}
        normalized = normalize_move_quality_nag_mapping(raw)
        self.assertEqual(
            normalized["Mistake"]["nag"], DEFAULT_MOVE_QUALITY_NAG_MAPPING["Mistake"]["nag"]
        )


class TestApplyMoveQualityNags(unittest.TestCase):
    def _game_with_pgn(self, pgn: str) -> GameData:
        return GameData(
            game_number=1,
            white="W",
            black="B",
            result="*",
            pgn=pgn,
        )

    def test_applies_and_overrides_quality_nags(self):
        pgn = """[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "W"]
[Black "B"]
[Result "*"]

1. e4 $2 e5 $1 2. Nf3 *
"""
        game = self._game_with_pgn(pgn)
        moves = [
            MoveData(
                move_number=1,
                white_move="e4",
                black_move="e5",
                assess_white="Blunder",
                assess_black="Best Move",
            ),
            MoveData(
                move_number=2,
                white_move="Nf3",
                black_move="",
                assess_white="Good Move",
                assess_black="",
            ),
        ]
        mapping = default_move_quality_nag_mapping()
        mapping["Best Move"] = {"enabled": True, "nag": chess.pgn.NAG_GOOD_MOVE}
        self.assertTrue(MoveQualityNagService.apply_to_game(game, moves, mapping))

        parsed = chess.pgn.read_game(io.StringIO(game.pgn))
        self.assertIsNotNone(parsed)
        e4 = parsed.variation(0)
        e5 = e4.variation(0)
        nf3 = e5.variation(0)

        self.assertEqual(e4.nags & QUALITY_NAGS, {chess.pgn.NAG_BLUNDER})
        self.assertEqual(e5.nags & QUALITY_NAGS, {chess.pgn.NAG_GOOD_MOVE})
        self.assertEqual(nf3.nags & QUALITY_NAGS, set())

    def test_preserves_non_quality_nags(self):
        pgn = """[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "W"]
[Black "B"]
[Result "*"]

1. e4 $10 *
"""
        game = self._game_with_pgn(pgn)
        moves = [
            MoveData(
                move_number=1,
                white_move="e4",
                black_move="",
                assess_white="Mistake",
                assess_black="",
            ),
        ]
        mapping = default_move_quality_nag_mapping()
        self.assertTrue(MoveQualityNagService.apply_to_game(game, moves, mapping))
        parsed = chess.pgn.read_game(io.StringIO(game.pgn))
        e4 = parsed.variation(0)
        self.assertIn(chess.pgn.NAG_DRAWISH_POSITION, e4.nags)
        self.assertEqual(e4.nags & QUALITY_NAGS, {chess.pgn.NAG_MISTAKE})

    def test_miss_maps_to_blunder_nag(self):
        pgn = """[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "W"]
[Black "B"]
[Result "*"]

1. e4 *
"""
        game = self._game_with_pgn(pgn)
        moves = [
            MoveData(
                move_number=1,
                white_move="e4",
                black_move="",
                assess_white="Miss",
                assess_black="",
            ),
        ]
        mapping = default_move_quality_nag_mapping()
        self.assertTrue(MoveQualityNagService.apply_to_game(game, moves, mapping))
        parsed = chess.pgn.read_game(io.StringIO(game.pgn))
        e4 = parsed.variation(0)
        self.assertEqual(e4.nags & QUALITY_NAGS, {chess.pgn.NAG_BLUNDER})

    def test_custom_mapping_applied(self):
        pgn = """[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "W"]
[Black "B"]
[Result "*"]

1. e4 *
"""
        game = self._game_with_pgn(pgn)
        moves = [
            MoveData(
                move_number=1,
                white_move="e4",
                black_move="",
                assess_white="Inaccuracy",
                assess_black="",
            ),
        ]
        mapping = default_move_quality_nag_mapping()
        mapping["Inaccuracy"] = {"enabled": True, "nag": chess.pgn.NAG_SPECULATIVE_MOVE}
        self.assertTrue(MoveQualityNagService.apply_to_game(game, moves, mapping))
        parsed = chess.pgn.read_game(io.StringIO(game.pgn))
        e4 = parsed.variation(0)
        self.assertEqual(e4.nags & QUALITY_NAGS, {chess.pgn.NAG_SPECULATIVE_MOVE})


if __name__ == "__main__":
    unittest.main()
