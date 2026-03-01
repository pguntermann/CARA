"""Unit tests for material balance and piece counting utilities."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
import chess
from app.utils.material_tracker import (
    calculate_material_balance,
    calculate_material_loss,
    get_captured_piece_letter,
    calculate_material_count,
    count_pieces,
    PIECE_VALUES,
)


class TestCalculateMaterialBalance(unittest.TestCase):
    """Tests for calculate_material_balance."""

    def test_starting_position_zero(self):
        board = chess.Board()
        self.assertEqual(calculate_material_balance(board), 0)

    def test_white_pawn_up_positive(self):
        # Black missing one pawn (e.g. h7) -> white +100
        board = chess.Board("rnbqkbnr/pppppp1p/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
        self.assertEqual(calculate_material_balance(board), 100)

    def test_black_knight_up_negative(self):
        # White one knight (R1BQKBNR), black two knights (r1bqkbnr + Nc6) -> -300
        board = chess.Board("r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/R1BQKBNR w KQkq - 0 1")
        self.assertEqual(calculate_material_balance(board), -300)

    def test_queen_capture_balance(self):
        # White has no queen (RNB1KBNR), black has queen (rnbqkbnr) -> -900
        board = chess.Board("rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 1")
        self.assertEqual(calculate_material_balance(board), -900)


class TestCalculateMaterialLoss(unittest.TestCase):
    """Tests for calculate_material_loss."""

    def test_white_captures_black_pawn_negative_loss(self):
        # Position: white e5, black d6. Move exd6. After: white up a pawn -> loss -100 (gain).
        board_before = chess.Board("rnbqkbnr/ppp1pppp/3p4/4P3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
        move = chess.Move(chess.parse_square("e5"), chess.parse_square("d6"))
        board_after = board_before.copy()
        board_after.push(move)
        loss = calculate_material_loss(board_before, board_after, is_white_to_move=True)
        self.assertEqual(loss, -100)

    def test_white_drops_piece_positive_loss(self):
        # Before: equal. After: white lost knight.
        board_before = chess.Board()
        board_after = board_before.copy()
        board_after.remove_piece_at(chess.parse_square("b1"))  # white loses knight
        loss = calculate_material_loss(board_before, board_after, is_white_to_move=True)
        self.assertEqual(loss, 300)

    def test_black_captures_white_pawn_negative_loss(self):
        # Black e4 captures white pawn on e3. After: black up a pawn -> loss -100 (gain).
        board_before = chess.Board("rnbqkbnr/pppp1ppp/8/8/4p3/4P3/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        move = chess.Move(chess.parse_square("e4"), chess.parse_square("e3"))
        board_after = board_before.copy()
        board_after.push(move)
        loss = calculate_material_loss(board_before, board_after, is_white_to_move=False)
        self.assertEqual(loss, -100)


class TestGetCapturedPieceLetter(unittest.TestCase):
    """Tests for get_captured_piece_letter."""

    def test_no_capture_returns_empty(self):
        board = chess.Board()
        move = chess.Move(chess.parse_square("e2"), chess.parse_square("e4"))
        self.assertEqual(get_captured_piece_letter(board, move), "")

    def test_capture_pawn_returns_p(self):
        # exd6: white e5 captures black pawn on d6
        board = chess.Board("rnbqkbnr/ppp1pppp/3p4/4P3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
        move = chess.Move(chess.parse_square("e5"), chess.parse_square("d6"))
        self.assertEqual(get_captured_piece_letter(board, move), "p")

    def test_capture_rook_returns_r(self):
        # e5 captures rook on d6
        board = chess.Board("rnbqkbnr/ppp2ppp/3r4/4P3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
        move = chess.Move(chess.parse_square("e5"), chess.parse_square("d6"))
        self.assertTrue(board.is_capture(move))
        self.assertEqual(get_captured_piece_letter(board, move), "r")

    def test_capture_knight_returns_n(self):
        board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4P3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
        move = chess.Move(chess.parse_square("e5"), chess.parse_square("c6"))
        self.assertEqual(get_captured_piece_letter(board, move), "n")

    def test_capture_bishop_returns_b(self):
        board = chess.Board("rnbqk1nr/pppp1ppp/4p3/4P3/1b6/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
        move = chess.Move(chess.parse_square("e5"), chess.parse_square("b4"))
        self.assertEqual(get_captured_piece_letter(board, move), "b")

    def test_capture_queen_returns_q(self):
        board = chess.Board("rnb1kbnr/pppp1ppp/4p3/4P3/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
        board.set_piece_at(chess.parse_square("d6"), chess.Piece(chess.QUEEN, chess.BLACK))
        move = chess.Move(chess.parse_square("e5"), chess.parse_square("d6"))
        self.assertEqual(get_captured_piece_letter(board, move), "q")


class TestCalculateMaterialCount(unittest.TestCase):
    """Tests for calculate_material_count."""

    def test_starting_white(self):
        board = chess.Board()
        self.assertEqual(calculate_material_count(board, is_white=True), 8*100 + 2*300 + 2*300 + 2*500 + 900)

    def test_starting_black_same_as_white(self):
        board = chess.Board()
        white_val = calculate_material_count(board, is_white=True)
        black_val = calculate_material_count(board, is_white=False)
        self.assertEqual(white_val, black_val)

    def test_white_missing_queen(self):
        board = chess.Board()
        board.remove_piece_at(chess.parse_square("d1"))
        white_val = calculate_material_count(board, is_white=True)
        self.assertEqual(white_val, 8*100 + 2*300 + 2*300 + 2*500)  # no queen


class TestCountPieces(unittest.TestCase):
    """Tests for count_pieces."""

    def test_starting_white_counts(self):
        board = chess.Board()
        counts = count_pieces(board, is_white=True)
        self.assertEqual(counts[chess.PAWN], 8)
        self.assertEqual(counts[chess.KNIGHT], 2)
        self.assertEqual(counts[chess.BISHOP], 2)
        self.assertEqual(counts[chess.ROOK], 2)
        self.assertEqual(counts[chess.QUEEN], 1)
        self.assertNotIn(chess.KING, counts)

    def test_starting_black_counts(self):
        board = chess.Board()
        counts = count_pieces(board, is_white=False)
        self.assertEqual(counts[chess.PAWN], 8)
        self.assertEqual(counts[chess.QUEEN], 1)

    def test_after_capture(self):
        board = chess.Board()
        board.remove_piece_at(chess.parse_square("b1"))
        counts = count_pieces(board, is_white=True)
        self.assertEqual(counts[chess.KNIGHT], 1)


class TestPieceValuesConstant(unittest.TestCase):
    """Sanity check PIECE_VALUES."""

    def test_expected_values(self):
        self.assertEqual(PIECE_VALUES[chess.PAWN], 100)
        self.assertEqual(PIECE_VALUES[chess.KNIGHT], 300)
        self.assertEqual(PIECE_VALUES[chess.BISHOP], 300)
        self.assertEqual(PIECE_VALUES[chess.ROOK], 500)
        self.assertEqual(PIECE_VALUES[chess.QUEEN], 900)
        self.assertEqual(PIECE_VALUES[chess.KING], 0)


if __name__ == "__main__":
    unittest.main()
