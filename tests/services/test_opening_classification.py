"""Curated opening classification (Lichess-style named positions)."""

from __future__ import annotations

import os
import sys
import unittest

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config.config_loader import ConfigLoader
from app.services.opening_service import OpeningService


def _fen_after(sans: list[str]) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board.fen()


def _last_named(svc: OpeningService, sans: list[str]) -> tuple[str | None, str | None]:
    last: tuple[str | None, str | None] = (None, None)
    board = chess.Board()
    for san in sans:
        board.push_san(san)
        eco, name = svc.get_opening_info(board.fen())
        if eco:
            last = (eco, name)
    return last


def _replay(sans: list[str]) -> tuple[list[str], list[str], list[str]]:
    board = chess.Board()
    fens = [board.fen()]
    ucis: list[str] = []
    for san in sans:
        move = board.parse_san(san)
        ucis.append(move.uci())
        board.push(move)
        fens.append(board.fen())
    return fens, sans, ucis


class TestOpeningClassification(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.svc = OpeningService(ConfigLoader())
        cls.svc.load()

    def test_modern_line_does_not_become_vant_kruijs(self) -> None:
        sans = ["d4", "g6", "Nf3", "Bg7", "e3", "d6"]
        eco, name = _last_named(self.svc, sans)
        self.assertEqual(eco, "A40")
        self.assertIn("Modern", name or "")
        self.assertNotIn("Kruijs", name or "")
        # Unnamed theory ply: no curated name at the transposed placement.
        self.assertEqual(self.svc.get_opening_info(_fen_after(sans)), (None, None))

    def test_nf3_move_order_same_modern_carry_forward(self) -> None:
        sans = ["Nf3", "g6", "d4", "Bg7", "e3", "d6"]
        eco, name = _last_named(self.svc, sans)
        self.assertEqual(eco, "A40")
        self.assertIn("Modern", name or "")
        self.assertNotIn("Kruijs", name or "")

    def test_true_e3_line_still_vant_kruijs(self) -> None:
        eco, name = self.svc.get_opening_info(_fen_after(["e3"]))
        self.assertEqual(eco, "A00")
        self.assertIn("Van't Kruijs", name or "")

    def test_zukertort_transposes_to_four_knights(self) -> None:
        sans = ["Nf3", "Nf6", "e4", "Nc6", "Nc3", "e5"]
        eco, name = _last_named(self.svc, sans)
        self.assertEqual(eco, "C47")
        self.assertIn("Four Knights", name or "")

    def test_classical_four_knights_unchanged(self) -> None:
        sans = ["e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6"]
        eco, name = self.svc.get_opening_info(_fen_after(sans))
        self.assertEqual(eco, "C47")
        self.assertIn("Four Knights", name or "")

    def test_neighbor_d4_d6_does_not_fall_to_a00(self) -> None:
        sans = ["d4", "d6", "Nf3", "g6", "e3", "Bg7"]
        eco, name = _last_named(self.svc, sans)
        self.assertIsNotNone(eco)
        self.assertNotEqual(eco, "A00")
        self.assertNotIn("Kruijs", name or "")

    def test_path_carries_modern_without_gap(self) -> None:
        sans = ["d4", "g6", "Nf3", "Bg7", "e3", "d6"]
        fens, sans, ucis = _replay(sans)
        path = self.svc.build_path_from_replay(fens, sans, ucis)
        self.assertEqual(path[-1].display.eco, "A40")
        self.assertIn("Modern", path[-1].display.name)
        self.assertIsNone(path[-1].gap_before)
        self.assertTrue(self.svc.is_book_position(fens[-1]))

    def test_final_eco_skips_interpolated_root(self) -> None:
        pgn = """[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "W"]
[Black "B"]
[Result "*"]

1. d4 g6 2. Nf3 Bg7 3. e3 d6 *"""
        eco = self.svc.get_final_eco_for_game(pgn)
        self.assertEqual(eco, "A40")
        last = self.svc.last_opening_for_pgn(pgn)
        self.assertIsNotNone(last)
        self.assertEqual(last.eco, "A40")
        self.assertIn("Modern", last.name)

    def test_last_opening_prefers_later_book_ply(self) -> None:
        """Game ECO is the last named ply, not an earlier row hidden by ``*``."""
        pgn = """[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "W"]
[Black "B"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 *"""
        last = self.svc.last_opening_for_pgn(pgn)
        self.assertIsNotNone(last)
        self.assertEqual(self.svc.get_final_eco_for_game(pgn), last.eco)
        self.assertEqual(last.eco, "C50")
        self.assertIn("Italian", last.name)


if __name__ == "__main__":
    unittest.main()
