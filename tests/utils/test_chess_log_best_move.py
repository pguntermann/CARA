"""Tests for chess_log_best_move.resolve_best_move_for_path."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import chess


def _make_game(pgn: str = "", game_number: int = 1):
    from app.models.database_model import GameData
    return GameData(game_number=game_number, pgn=pgn)


def _make_move_data(best_white: str = "", best_black: str = ""):
    from app.models.moveslist_model import MoveData
    return MoveData(
        move_number=0,
        white_move="",
        black_move="",
        eval_white="",
        eval_black="",
        cpl_white="",
        cpl_black="",
        cpl_white_2="",
        cpl_white_3="",
        cpl_black_2="",
        cpl_black_3="",
        assess_white="",
        assess_black="",
        best_white=best_white,
        best_black=best_black,
    )


# Minimal 3-move PGN: 1. e4 e5 2. Nf3
_PGN_3PLY = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 *\n"
)

# PGN with one mainline move and a variation (for variation test)
_PGN_WITH_VARIATION = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 (1. d4 d5) e5 *\n"
)

_CLAMP_PATH_PLY1 = "0"  # mainline ply 1 (white's first move, path length 1)
_CLAMP_PATH_PLY2 = "0.0"  # mainline ply 2 (black's first move, path length 2)
_CLAMP_PATH_PLY3 = "0.0.0"  # mainline ply 3 (white's second move, path length 3)
_VARIATION_PATH = "1"  # variation fork at root (non-zero child index)


class TestReturnsNoneForUnanalyzedGame(unittest.TestCase):
    def test_no_analysis_data(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        game = _make_game(_PGN_3PLY)
        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=False,
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY1, None)
        self.assertIsNone(result)

    def test_none_game_returns_none(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        result = resolve_best_move_for_path(None, _CLAMP_PATH_PLY1, None)
        self.assertIsNone(result)

    def test_empty_path_key_returns_none(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        game = _make_game(_PGN_3PLY)
        result = resolve_best_move_for_path(game, "", None)
        self.assertIsNone(result)


class TestReturnsNoneForVariationPath(unittest.TestCase):
    def test_variation_path_returns_none(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        game = _make_game(_PGN_WITH_VARIATION)
        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[_make_move_data(best_white="d4", best_black="d5")],
        ):
            result = resolve_best_move_for_path(game, _VARIATION_PATH, None)
        self.assertIsNone(result)


class TestReturnsBestMoveForMainlinePath(unittest.TestCase):
    def test_white_ply1_returns_best_white(self):
        """Path of length 1 → ply 1 → white's move → best_white at row 0."""
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        import chess.pgn
        from io import StringIO

        game = _make_game(_PGN_3PLY)
        pgn_game = chess.pgn.read_game(StringIO(_PGN_3PLY))
        played = chess.Move.from_uci("e2e4")  # 1. e4

        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[_make_move_data(best_white="d4")],
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY1, played, pgn_game)

        self.assertIsNotNone(result)
        self.assertEqual(result, chess.Move.from_uci("d2d4"))

    def test_black_ply2_returns_best_black(self):
        """Path of length 2 → ply 2 → black's move → best_black at row 0."""
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        import chess.pgn
        from io import StringIO

        game = _make_game(_PGN_3PLY)
        pgn_game = chess.pgn.read_game(StringIO(_PGN_3PLY))
        played = chess.Move.from_uci("e7e5")  # 1...e5

        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[_make_move_data(best_black="c5")],
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY2, played, pgn_game)

        self.assertIsNotNone(result)
        self.assertEqual(result, chess.Move.from_uci("c7c5"))

    def test_white_ply3_reads_row1(self):
        """Path of length 3 → ply 3 → white's move → best_white at row 1."""
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        import chess.pgn
        from io import StringIO

        game = _make_game(_PGN_3PLY)
        pgn_game = chess.pgn.read_game(StringIO(_PGN_3PLY))
        played = chess.Move.from_uci("g1f3")  # 2. Nf3

        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[
                _make_move_data(best_white="e4", best_black="e5"),  # row 0
                _make_move_data(best_white="Nc3"),                  # row 1
            ],
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY3, played, pgn_game)

        self.assertIsNotNone(result)
        self.assertEqual(result, chess.Move.from_uci("b1c3"))


class TestSuppressesEqualBestMove(unittest.TestCase):
    def test_best_equals_played_returns_none(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        import chess.pgn
        from io import StringIO

        game = _make_game(_PGN_3PLY)
        pgn_game = chess.pgn.read_game(StringIO(_PGN_3PLY))
        played = chess.Move.from_uci("e2e4")

        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[_make_move_data(best_white="e4")],
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY1, played, pgn_game)

        self.assertIsNone(result)


class TestReturnsNoneOnSanParseFail(unittest.TestCase):
    def test_malformed_san_returns_none(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        import chess.pgn
        from io import StringIO

        game = _make_game(_PGN_3PLY)
        pgn_game = chess.pgn.read_game(StringIO(_PGN_3PLY))

        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[_make_move_data(best_white="INVALID??!!")],
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY1, None, pgn_game)

        self.assertIsNone(result)

    def test_empty_best_san_returns_none(self):
        from app.utils.chess_log_best_move import resolve_best_move_for_path
        import chess.pgn
        from io import StringIO

        game = _make_game(_PGN_3PLY)
        pgn_game = chess.pgn.read_game(StringIO(_PGN_3PLY))

        with patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.has_analysis_data",
            return_value=True,
        ), patch(
            "app.services.analysis_data_storage_service.AnalysisDataStorageService.load_analysis_data",
            return_value=[_make_move_data(best_white="")],
        ):
            result = resolve_best_move_for_path(game, _CLAMP_PATH_PLY1, None, pgn_game)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
