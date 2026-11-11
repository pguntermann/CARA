"""Tests for _tag_row_helpers.node_info (no Qt required)."""

import io
import unittest

import chess.pgn

from app.views.dialogs._tag_row_helpers import node_info

_PGN = (
    '[Event "T"][Site "?"][Date "?"][Round "?"]'
    '[White "?"][Black "?"][Result "*"]\n\n'
    "1. e4 e5 *\n"
)


def _parse(pgn_text: str) -> chess.pgn.Game:
    return chess.pgn.read_game(io.StringIO(pgn_text))


class TestNodeInfoMoverIsBlack(unittest.TestCase):
    def test_white_move_returns_false(self):
        game = _parse(_PGN)
        _, _, _, mover_is_black = node_info(game, "0")
        self.assertFalse(mover_is_black)

    def test_black_move_returns_true(self):
        game = _parse(_PGN)
        _, _, _, mover_is_black = node_info(game, "0.0")
        self.assertTrue(mover_is_black)

    def test_none_game_returns_false(self):
        _, _, _, mover_is_black = node_info(None, "0")
        self.assertFalse(mover_is_black)

    def test_invalid_path_returns_false(self):
        game = _parse(_PGN)
        _, _, _, mover_is_black = node_info(game, "9.9.9")
        self.assertFalse(mover_is_black)

    def test_empty_path_returns_false(self):
        game = _parse(_PGN)
        _, _, _, mover_is_black = node_info(game, "")
        self.assertFalse(mover_is_black)

    def test_fen_still_returned(self):
        game = _parse(_PGN)
        fen, move, label, mover_is_black = node_info(game, "0")
        self.assertTrue(fen.startswith("rnbqkbnr"))
        self.assertIsNotNone(move)
        self.assertIn("e4", label)


if __name__ == "__main__":
    unittest.main()
