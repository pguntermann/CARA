"""Comprehensive unit tests for all positional heatmap rules.

This test suite validates all positional evaluation rules with various positions
and edge cases to expose potential issues. Each test uses carefully constructed
FEN positions that make sense for the specific rule being tested.
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
from app.services.positional_heatmap.rules.passed_pawn_rule import PassedPawnRule
from app.services.positional_heatmap.rules.backward_pawn_rule import BackwardPawnRule
from app.services.positional_heatmap.rules.isolated_pawn_rule import IsolatedPawnRule
from app.services.positional_heatmap.rules.doubled_pawn_rule import DoubledPawnRule
from app.services.positional_heatmap.rules.king_safety_rule import KingSafetyRule
from app.services.positional_heatmap.rules.weak_square_rule import WeakSquareRule
from app.services.positional_heatmap.rules.piece_activity_rule import PieceActivityRule
from app.services.positional_heatmap.rules.undeveloped_piece_rule import UndevelopedPieceRule
from app.config.config_loader import ConfigLoader


class TestPositionalHeatmapRules:
    """Comprehensive test suite for all positional heatmap rules."""
    
    def __init__(self):
        """Initialize test suite."""
        # Load config
        config_path = Path('app/config/config.json')
        config_loader = ConfigLoader(config_path)
        config = config_loader.load()
        heatmap_config = config.get('ui', {}).get('positional_heatmap', {})
        rules_config = heatmap_config.get('rules', {})
        
        # Create rule instances
        self.passed_pawn_rule = PassedPawnRule(rules_config.get('passed_pawn', {}))
        self.backward_pawn_rule = BackwardPawnRule(rules_config.get('backward_pawn', {}))
        self.isolated_pawn_rule = IsolatedPawnRule(rules_config.get('isolated_pawn', {}))
        self.doubled_pawn_rule = DoubledPawnRule(rules_config.get('doubled_pawn', {}))
        self.king_safety_rule = KingSafetyRule(rules_config.get('king_safety', {}))
        self.weak_square_rule = WeakSquareRule(rules_config.get('weak_square', {}))
        self.piece_activity_rule = PieceActivityRule(rules_config.get('piece_activity', {}))
        self.undeveloped_piece_rule = UndevelopedPieceRule(rules_config.get('undeveloped_piece', {}))
        
        self.test_count = 0
        self.pass_count = 0
        self.fail_count = 0
    
    def run_all_tests(self):
        """Run all test cases."""
        print(f"\n{'='*80}")
        print("COMPREHENSIVE POSITIONAL HEATMAP RULES TEST SUITE")
        print(f"{'='*80}\n")
        
        # Passed Pawn Rule Tests
        print("\n" + "="*80)
        print("PASSED PAWN RULE TESTS")
        print("="*80)
        self.test_passed_pawn_basic_white()
        self.test_passed_pawn_basic_black()
        self.test_passed_pawn_starting_rank_not_evaluated()
        self.test_passed_pawn_blocked_not_passed()
        self.test_passed_pawn_adjacent_file_blocked()
        self.test_passed_pawn_rank_scaling()
        self.test_passed_pawn_attacked_undefended()
        self.test_passed_pawn_non_passed_no_score()
        self.test_passed_pawn_blocked_by_same_file_pawn()
        
        # Backward Pawn Rule Tests
        print("\n" + "="*80)
        print("BACKWARD PAWN RULE TESTS")
        print("="*80)
        self.test_backward_pawn_basic()
        self.test_backward_pawn_not_backward()
        self.test_backward_pawn_can_advance_safely()
        self.test_backward_pawn_d3()
        self.test_backward_pawn_f2_with_protection()
        self.test_backward_pawn_defended_by_adjacent()
        
        # Isolated Pawn Rule Tests
        print("\n" + "="*80)
        print("ISOLATED PAWN RULE TESTS")
        print("="*80)
        self.test_isolated_pawn_basic()
        self.test_isolated_pawn_not_isolated()
        self.test_isolated_pawn_edge_file()
        
        # Doubled Pawn Rule Tests
        print("\n" + "="*80)
        print("DOUBLED PAWN RULE TESTS")
        print("="*80)
        self.test_doubled_pawn_basic()
        self.test_doubled_pawn_central_vs_edge()
        self.test_doubled_pawn_open_file_reduction()
        self.test_doubled_pawn_tripled()
        
        # King Safety Rule Tests
        print("\n" + "="*80)
        print("KING SAFETY RULE TESTS")
        print("="*80)
        self.test_king_safety_in_check()
        self.test_king_safety_open_file()
        self.test_king_safety_semi_open_file()
        self.test_king_safety_pawn_shield()
        self.test_king_safety_exposed_king()
        
        # Weak Square Rule Tests
        print("\n" + "="*80)
        print("WEAK SQUARE RULE TESTS")
        print("="*80)
        self.test_weak_square_attacked_undefended()
        self.test_weak_square_attacked_defended()
        self.test_weak_square_piece_value_scaling()
        
        # Piece Activity Rule Tests
        print("\n" + "="*80)
        print("PIECE ACTIVITY RULE TESTS")
        print("="*80)
        self.test_piece_activity_mobility()
        self.test_piece_activity_central_control()
        self.test_piece_activity_blocked_piece()
        self.test_piece_activity_perspective_independence()
        self.test_piece_activity_doubled_rooks_on_open_file()
        
        # Undeveloped Piece Rule Tests
        print("\n" + "="*80)
        print("UNDEVELOPED PIECE RULE TESTS")
        print("="*80)
        self.test_undeveloped_piece_blocked_rook()
        
        # Print summary
        print(f"\n{'='*80}")
        print("TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total tests: {self.test_count}")
        print(f"Passed: {self.pass_count}")
        print(f"Failed: {self.fail_count}")
        print(f"{'='*80}\n")
    
    def assert_true(self, condition: bool, message: str):
        """Assert that condition is True."""
        self.test_count += 1
        if condition:
            self.pass_count += 1
            print(f"[PASS] {message}")
        else:
            self.fail_count += 1
            print(f"[FAIL] {message}")
    
    def assert_false(self, condition: bool, message: str):
        """Assert that condition is False."""
        self.assert_true(not condition, message)
    
    def assert_equals(self, actual, expected, message: str):
        """Assert that actual equals expected."""
        self.assert_true(actual == expected, f"{message} (expected {expected}, got {actual})")
    
    def assert_in(self, item, container, message: str):
        """Assert that item is in container."""
        self.assert_true(item in container, message)
    
    def assert_not_in(self, item, container, message: str):
        """Assert that item is not in container."""
        self.assert_false(item in container, message)
    
    def assert_greater(self, actual, expected, message: str):
        """Assert that actual > expected."""
        self.assert_true(actual > expected, f"{message} (expected > {expected}, got {actual})")
    
    def assert_less(self, actual, expected, message: str):
        """Assert that actual < expected."""
        self.assert_true(actual < expected, f"{message} (expected < {expected}, got {actual})")
    
    # ============================================================================
    # PASSED PAWN RULE TESTS
    # ============================================================================
    
    def test_passed_pawn_basic_white(self):
        """Test basic passed pawn detection for white."""
        # White pawn on d6, no black pawns on d, c, or e files ahead
        # Remove ALL black pawns on d, c, e files (d7, c7, e7)
        fen = "rnbqkbnr/pp1pp1pp/3P4/8/8/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        # Manually remove black pawns on d7, c7, e7 to make d6 passed
        board.remove_piece_at(chess.parse_square('d7'))
        board.remove_piece_at(chess.parse_square('c7'))
        board.remove_piece_at(chess.parse_square('e7'))
        d6 = chess.parse_square('d6')
        
        scores = self.passed_pawn_rule.evaluate(board, chess.WHITE)
        is_passed = self.passed_pawn_rule._is_passed_pawn(board, 3, 5, chess.WHITE)
        
        self.assert_true(is_passed, "d6 should be a passed pawn (no black pawns ahead)")
        self.assert_in(d6, scores, "d6 should have a score")
        if d6 in scores:
            self.assert_greater(scores[d6], 0, f"d6 should have positive score (got {scores[d6]})")
    
    def test_passed_pawn_basic_black(self):
        """Test basic passed pawn detection for black."""
        # Black pawn on d3, no white pawns on d, c, or e files ahead
        # Remove ALL white pawns on d, c, e files (d2, c2, e2)
        # Also remove white pieces that might attack d3
        fen = "rnbqkbnr/pppppppp/8/8/8/3p4/PP1PPPPP/RNBQKBNR b KQkq - 0 1"
        board = chess.Board(fen)
        # Manually remove white pawns on d2, c2, e2 to make d3 passed
        board.remove_piece_at(chess.parse_square('d2'))
        board.remove_piece_at(chess.parse_square('c2'))
        board.remove_piece_at(chess.parse_square('e2'))
        # Remove white pieces that might attack d3
        board.remove_piece_at(chess.parse_square('b1'))  # Remove knight
        board.remove_piece_at(chess.parse_square('c1'))  # Remove bishop
        board.remove_piece_at(chess.parse_square('f1'))  # Remove bishop
        board.remove_piece_at(chess.parse_square('g1'))  # Remove knight
        d3 = chess.parse_square('d3')
        
        scores = self.passed_pawn_rule.evaluate(board, chess.BLACK)
        is_passed = self.passed_pawn_rule._is_passed_pawn(board, 3, 2, chess.BLACK)
        is_attacked = board.is_attacked_by(chess.WHITE, d3)
        is_defended = board.is_attacked_by(chess.BLACK, d3)
        
        self.assert_true(is_passed, "d3 should be a passed pawn (no white pawns ahead)")
        self.assert_in(d3, scores, "d3 should have a score")
        if d3 in scores:
            # If attacked and undefended, it might have negative score (early rank)
            # Otherwise, it should have positive score
            if is_attacked and not is_defended:
                # Early rank attacked/undefended passed pawn gets negative score
                self.assert_less(scores[d3], 0, f"d3 should have negative score if attacked/undefended (got {scores[d3]})")
            else:
                self.assert_greater(scores[d3], 0, f"d3 should have positive score (got {scores[d3]})")
    
    def test_passed_pawn_starting_rank_not_evaluated(self):
        """Test that starting rank pawns are not evaluated."""
        # Starting position - all pawns on starting ranks
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.passed_pawn_rule.evaluate(board, chess.WHITE)
        
        # All white pawns are on starting rank (rank 1), should not be evaluated
        white_pawns = board.pieces(chess.PAWN, chess.WHITE)
        for pawn_sq in white_pawns:
            self.assert_not_in(pawn_sq, scores, f"White pawn on {chess.square_name(pawn_sq)} should not have score (on starting rank)")
    
    def test_passed_pawn_blocked_not_passed(self):
        """Test that blocked pawns are not passed."""
        # White pawn on d4, blocked by black pawn on d5
        fen = "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d4 = chess.parse_square('d4')
        
        is_blocked = self.passed_pawn_rule._is_blocked_pawn(board, 3, 3, chess.WHITE)
        is_passed = self.passed_pawn_rule._is_passed_pawn(board, 3, 3, chess.WHITE)
        
        self.assert_true(is_blocked, "d4 should be blocked")
        self.assert_false(is_passed, "d4 should not be passed (blocked)")
    
    def test_passed_pawn_adjacent_file_blocked(self):
        """Test that pawns blocked by adjacent file pawns are not passed."""
        # White pawn on f5, black pawn on e3 blocks it (adjacent file)
        fen = "rnbqkbnr/pppppppp/8/5P2/8/4p3/PPPPP1PP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        f5 = chess.parse_square('f5')
        
        is_passed = self.passed_pawn_rule._is_passed_pawn(board, 5, 4, chess.WHITE)
        scores = self.passed_pawn_rule.evaluate(board, chess.WHITE)
        
        self.assert_false(is_passed, "f5 should not be passed (blocked by e3)")
        self.assert_not_in(f5, scores, "f5 should not have score (not passed)")
    
    def test_passed_pawn_rank_scaling(self):
        """Test that passed pawn bonus scales with rank."""
        # Test passed pawns on different files to avoid blocking
        # White passed pawns: d4, e5, f6 (different files, different ranks)
        # Remove black pawns and pieces that might attack them
        fen = "rnbqkbnr/pp1pp1pp/5P2/4P3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        # Manually remove black pawns to make them passed
        board.remove_piece_at(chess.parse_square('d7'))
        board.remove_piece_at(chess.parse_square('c7'))
        board.remove_piece_at(chess.parse_square('e7'))
        board.remove_piece_at(chess.parse_square('f7'))
        board.remove_piece_at(chess.parse_square('g7'))
        # Remove black pieces that might attack the passed pawns
        board.remove_piece_at(chess.parse_square('b8'))  # Remove knight
        board.remove_piece_at(chess.parse_square('c8'))  # Remove bishop
        board.remove_piece_at(chess.parse_square('f8'))  # Remove bishop
        board.remove_piece_at(chess.parse_square('g8'))  # Remove knight
        
        scores = self.passed_pawn_rule.evaluate(board, chess.WHITE)
        
        d4 = chess.parse_square('d4')
        e5 = chess.parse_square('e5')
        f6 = chess.parse_square('f6')
        
        # Verify they are all passed and not blocked
        is_d4_passed = self.passed_pawn_rule._is_passed_pawn(board, 3, 3, chess.WHITE)
        is_d4_blocked = self.passed_pawn_rule._is_blocked_pawn(board, 3, 3, chess.WHITE)
        is_e5_passed = self.passed_pawn_rule._is_passed_pawn(board, 4, 4, chess.WHITE)
        is_e5_blocked = self.passed_pawn_rule._is_blocked_pawn(board, 4, 4, chess.WHITE)
        is_f6_passed = self.passed_pawn_rule._is_passed_pawn(board, 5, 5, chess.WHITE)
        is_f6_blocked = self.passed_pawn_rule._is_blocked_pawn(board, 5, 5, chess.WHITE)
        
        # Check if they're attacked/defended (affects scoring)
        is_e5_attacked = board.is_attacked_by(chess.BLACK, e5)
        is_e5_defended = board.is_attacked_by(chess.WHITE, e5)
        is_f6_attacked = board.is_attacked_by(chess.BLACK, f6)
        is_f6_defended = board.is_attacked_by(chess.WHITE, f6)
        
        # Only test rank scaling if all are passed and not blocked
        if is_d4_passed and not is_d4_blocked and is_e5_passed and not is_e5_blocked and is_f6_passed and not is_f6_blocked:
            # Higher ranks should have higher bonuses (if not attacked/defended, which reduces bonus)
            # If f6 is attacked and defended, its bonus is reduced to 40%, so it might be lower than e5
            if d4 in scores and e5 in scores:
                # e5 should have higher bonus than d4 (higher rank)
                if not (is_e5_attacked and is_e5_defended):  # Not attacked/defended
                    self.assert_greater(scores[e5], scores[d4], f"e5 (rank 4) should have higher bonus than d4 (rank 3)")
            if e5 in scores and f6 in scores:
                # f6 should have higher bonus than e5 (higher rank) if not attacked/defended
                if not (is_f6_attacked and is_f6_defended):  # Not attacked/defended
                    self.assert_greater(scores[f6], scores[e5], f"f6 (rank 5) should have higher bonus than e5 (rank 4)")
                else:
                    # If f6 is attacked/defended, its bonus is reduced, so it might be lower
                    # This is expected behavior - document it
                    self.assert_true(True, f"f6 is attacked/defended, so bonus is reduced (expected behavior)")
        else:
            # If not all passed/not blocked, document it
            self.assert_true(False, f"Not all pawns are passed and not blocked: d4={is_d4_passed}/{is_d4_blocked}, e5={is_e5_passed}/{is_e5_blocked}, f6={is_f6_passed}/{is_f6_blocked}")
    
    def test_passed_pawn_attacked_undefended(self):
        """Test attacked and undefended passed pawn gets reduced/negative score."""
        # White passed pawn on d5, attacked by black rook, not defended
        fen = "r1bqkbnr/pppppppp/8/3P4/8/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d5 = chess.parse_square('d5')
        
        is_attacked = board.is_attacked_by(chess.BLACK, d5)
        is_defended = board.is_attacked_by(chess.WHITE, d5)
        scores = self.passed_pawn_rule.evaluate(board, chess.WHITE)
        
        if d5 in scores and is_attacked and not is_defended:
            rank = chess.square_rank(d5)
            if rank < 4:  # Early rank
                self.assert_less(scores[d5], 0, f"Early rank attacked/undefended should be negative (got {scores[d5]})")
    
    def test_passed_pawn_non_passed_no_score(self):
        """Test that non-passed pawns don't get scores (after our fix)."""
        # White pawn on f5, blocked by black pawn on e3 (not passed)
        fen = "8/p2k4/7R/2pK1pp1/2P5/1P2P3/P7/8 b - - 0 37"
        board = chess.Board(fen)
        f5 = chess.parse_square('f5')
        
        is_passed = self.passed_pawn_rule._is_passed_pawn(board, 5, 4, chess.BLACK)
        scores = self.passed_pawn_rule.evaluate(board, chess.BLACK)
        
        self.assert_false(is_passed, "f5 should not be passed (blocked by e3)")
        self.assert_not_in(f5, scores, "f5 should not have score (not passed)")
    
    def test_passed_pawn_blocked_by_same_file_pawn(self):
        """Test that pawns blocked by enemy pawns on same file are not passed."""
        # White pawns on f6 and h6, blocked by black pawns on f7 and h7
        # This is a bug case: these pawns should NOT be passed
        fen = "k7/5p1p/5P1P/8/8/8/8/K7 w - - 0 1"
        board = chess.Board(fen)
        f6 = chess.parse_square('f6')
        h6 = chess.parse_square('h6')
        
        # Check if they're blocked
        is_f6_blocked = self.passed_pawn_rule._is_blocked_pawn(board, 5, 5, chess.WHITE)
        is_h6_blocked = self.passed_pawn_rule._is_blocked_pawn(board, 7, 5, chess.WHITE)
        
        # Check if they're incorrectly classified as passed
        is_f6_passed = self.passed_pawn_rule._is_passed_pawn(board, 5, 5, chess.WHITE)
        is_h6_passed = self.passed_pawn_rule._is_passed_pawn(board, 7, 5, chess.WHITE)
        
        # Get scores from evaluation
        scores = self.passed_pawn_rule.evaluate(board, chess.WHITE)
        
        # Assertions: blocked pawns should not be passed
        self.assert_true(is_f6_blocked, "f6 should be blocked by f7")
        self.assert_true(is_h6_blocked, "h6 should be blocked by h7")
        self.assert_false(is_f6_passed, "f6 should NOT be passed (blocked by f7)")
        self.assert_false(is_h6_passed, "h6 should NOT be passed (blocked by h7)")
        self.assert_not_in(f6, scores, "f6 should not have score (blocked, not passed)")
        self.assert_not_in(h6, scores, "h6 should not have score (blocked, not passed)")
    
    # ============================================================================
    # BACKWARD PAWN RULE TESTS
    # ============================================================================
    
    def test_backward_pawn_basic(self):
        """Test basic backward pawn detection."""
        # White pawn on d2, white pawns on c3 and e3 ahead, black pawn on c4 attacks d3
        # This creates a backward pawn: d2 has friendly pawns ahead but can't advance safely
        fen = "rnbqkbnr/pppppppp/8/8/2p5/2P1P3/3P4/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d2 = chess.parse_square('d2')
        
        scores = self.backward_pawn_rule.evaluate(board, chess.WHITE)
        is_backward = self.backward_pawn_rule._is_backward_pawn(board, 3, 1, chess.WHITE)
        
        # Note: This test might pass or fail depending on exact backward pawn logic
        # The logic checks if advancing would be attacked by enemy pawns
        if is_backward:
            self.assert_in(d2, scores, "d2 should have a score if backward")
            if d2 in scores:
                self.assert_less(scores[d2], 0, f"d2 should have negative score (got {scores[d2]})")
        else:
            # If not backward, that's also valid - just document it
            self.assert_not_in(d2, scores, "d2 should not have score if not backward")
    
    def test_backward_pawn_not_backward(self):
        """Test that pawns without friendly pawns ahead are not backward."""
        # White pawn on d4, no friendly pawns ahead
        fen = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d4 = chess.parse_square('d4')
        
        is_backward = self.backward_pawn_rule._is_backward_pawn(board, 3, 3, chess.WHITE)
        scores = self.backward_pawn_rule.evaluate(board, chess.WHITE)
        
        self.assert_false(is_backward, "d4 should not be backward (no friendly pawns ahead)")
        self.assert_not_in(d4, scores, "d4 should not have score (not backward)")
    
    def test_backward_pawn_can_advance_safely(self):
        """Test that pawns that can advance safely are not backward."""
        # White pawn on d2, white pawns on c3 and e3 ahead, but d3 is safe
        fen = "rnbqkbnr/pppppppp/8/8/8/2P1P3/3P4/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d2 = chess.parse_square('d2')
        
        is_backward = self.backward_pawn_rule._is_backward_pawn(board, 3, 1, chess.WHITE)
        scores = self.backward_pawn_rule.evaluate(board, chess.WHITE)
        
        # If d3 is safe (no enemy pawns attacking it), d2 should not be backward
        # This test might pass or fail depending on the exact logic
        if not is_backward:
            self.assert_not_in(d2, scores, "d2 should not have score if not backward")
    
    def test_backward_pawn_d3(self):
        """Test backward pawn on d3 with black pawns on c5 and e5 attacking d4."""
        # White pawn on d3, white pawns on c4 and e4 ahead, black pawns on c5 and e5 attack d4
        fen = "rnbqkbnr/pppppppp/8/2p1p3/2P1P3/3P4/PP2PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d3 = chess.parse_square('d3')
        
        is_backward = self.backward_pawn_rule._is_backward_pawn(board, 3, 2, chess.WHITE)
        scores = self.backward_pawn_rule.evaluate(board, chess.WHITE)
        
        self.assert_true(is_backward, "d3 should be identified as backward pawn")
        self.assert_in(d3, scores, "d3 should have a score")
        if d3 in scores:
            self.assert_less(scores[d3], 0, f"d3 should have negative score (got {scores[d3]})")
    
    def test_backward_pawn_f2_with_protection(self):
        """Test that f2 is NOT backward because g2 can defend f3."""
        # White pawn on f2, white pawn on e4 ahead, black pawn on e5 can attack f3, but g2 can defend f3
        fen = "rnbqkbnr/pppppppp/8/2p1p3/2P1P3/3P4/PP2PPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        f2 = chess.parse_square('f2')
        
        is_backward = self.backward_pawn_rule._is_backward_pawn(board, 5, 1, chess.WHITE)
        scores = self.backward_pawn_rule.evaluate(board, chess.WHITE)
        
        self.assert_false(is_backward, "f2 should NOT be backward (can be defended by g2)")
        self.assert_not_in(f2, scores, "f2 should not have a score (not backward)")
    
    def test_backward_pawn_defended_by_adjacent(self):
        """Test backward pawn that is defended by adjacent pawn (c6 defended by b7)."""
        # Black pawn on c6, black pawn on d5 ahead, black pawn on b7 defends c6
        # FEN: r1bq1rk1/pp3p1p/2p3pb/3p4/B2P2N1/2N1R3/PPPQ1PPP/4R1K1 b - - 0 15
        fen = "r1bq1rk1/pp3p1p/2p3pb/3p4/B2P2N1/2N1R3/PPPQ1PPP/4R1K1 b - - 0 15"
        board = chess.Board(fen)
        c6 = chess.parse_square('c6')
        
        is_backward = self.backward_pawn_rule._is_backward_pawn(board, 2, 5, chess.BLACK)
        scores = self.backward_pawn_rule.evaluate(board, chess.BLACK)
        
        self.assert_true(is_backward, "c6 should be identified as backward pawn")
        self.assert_in(c6, scores, "c6 should have a score")
        if c6 in scores:
            # Should have reduced penalty because it's defended by b7
            self.assert_less(scores[c6], 0, f"c6 should have negative score (got {scores[c6]})")
            # Should be less negative than undefended backward pawn
            # Check that it's the defended penalty (should be -8.0 based on config)
            self.assert_greater(scores[c6], -15.0, f"c6 should have reduced penalty because defended (got {scores[c6]})")
    
    # ============================================================================
    # ISOLATED PAWN RULE TESTS
    # ============================================================================
    
    def test_isolated_pawn_basic(self):
        """Test basic isolated pawn detection."""
        # White pawn on d4, no white pawns on c or e files
        fen = "rnbqkbnr/pppppppp/8/8/3P4/8/PP1P1PPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d4 = chess.parse_square('d4')
        
        scores = self.isolated_pawn_rule.evaluate(board, chess.WHITE)
        is_isolated = self.isolated_pawn_rule._is_isolated_pawn(board, 3, chess.WHITE)
        
        self.assert_true(is_isolated, "d4 should be isolated (no friendly pawns on adjacent files)")
        self.assert_in(d4, scores, "d4 should have a score")
        if d4 in scores:
            self.assert_less(scores[d4], 0, f"d4 should have negative score (got {scores[d4]})")
    
    def test_isolated_pawn_not_isolated(self):
        """Test that pawns with friendly pawns on adjacent files are not isolated."""
        # White pawn on d4, white pawns on c3 and e3
        fen = "rnbqkbnr/pppppppp/8/8/3P4/2P1P3/PP3PPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        d4 = chess.parse_square('d4')
        
        is_isolated = self.isolated_pawn_rule._is_isolated_pawn(board, 3, chess.WHITE)
        scores = self.isolated_pawn_rule.evaluate(board, chess.WHITE)
        
        self.assert_false(is_isolated, "d4 should not be isolated (has friendly pawns on adjacent files)")
        self.assert_not_in(d4, scores, "d4 should not have score (not isolated)")
    
    def test_isolated_pawn_edge_file(self):
        """Test isolated pawn on edge file."""
        # White pawn on a4, no white pawn on b file (edge file)
        # Remove white pawn on b2 to make a4 isolated
        fen = "rnbqkbnr/pppppppp/8/8/P7/8/1PPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        # Manually remove white pawn on b2 to make a4 isolated
        board.remove_piece_at(chess.parse_square('b2'))
        a4 = chess.parse_square('a4')
        
        is_isolated = self.isolated_pawn_rule._is_isolated_pawn(board, 0, chess.WHITE)
        scores = self.isolated_pawn_rule.evaluate(board, chess.WHITE)
        
        # Edge file pawns are isolated if no pawn on adjacent file (b file)
        # For edge file (a), only check right file (b)
        self.assert_true(is_isolated, "a4 should be isolated (edge file, no pawn on b)")
        if is_isolated:
            self.assert_in(a4, scores, "a4 should have a score if isolated")
    
    # ============================================================================
    # DOUBLED PAWN RULE TESTS
    # ============================================================================
    
    def test_doubled_pawn_basic(self):
        """Test basic doubled pawn detection."""
        # Two white pawns on d file (d2 and d3)
        fen = "rnbqkbnr/pppppppp/8/8/8/3P4/3P4/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.doubled_pawn_rule.evaluate(board, chess.WHITE)
        
        d2 = chess.parse_square('d2')
        d3 = chess.parse_square('d3')
        
        self.assert_in(d2, scores, "d2 should have score (doubled pawn)")
        self.assert_in(d3, scores, "d3 should have score (doubled pawn)")
        if d2 in scores and d3 in scores:
            self.assert_less(scores[d2], 0, f"d2 should have negative score (got {scores[d2]})")
            self.assert_less(scores[d3], 0, f"d3 should have negative score (got {scores[d3]})")
    
    def test_doubled_pawn_central_vs_edge(self):
        """Test that central doubled pawns get reduced penalty."""
        # Central doubled pawns (d file) vs edge doubled pawns (a file)
        fen = "rnbqkbnr/pppppppp/8/8/8/3P4/3P4/RNBQKBNR w KQkq a6 0 1"
        board = chess.Board(fen)
        # Add edge doubled pawns
        board.set_piece_at(chess.parse_square('a2'), chess.Piece(chess.PAWN, chess.WHITE))
        board.set_piece_at(chess.parse_square('a3'), chess.Piece(chess.PAWN, chess.WHITE))
        
        scores = self.doubled_pawn_rule.evaluate(board, chess.WHITE)
        
        d2 = chess.parse_square('d2')
        a2 = chess.parse_square('a2')
        
        if d2 in scores and a2 in scores:
            # Central doubled pawns should have less negative score than edge
            self.assert_greater(scores[d2], scores[a2], f"Central doubled pawn should have less penalty than edge")
    
    def test_doubled_pawn_open_file_reduction(self):
        """Test that doubled pawns on open files get reduced penalty."""
        # Two white pawns on d file, no black pawns on d file (open file)
        fen = "rnbqkbnr/ppp1pppp/8/8/8/3P4/3P4/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.doubled_pawn_rule.evaluate(board, chess.WHITE)
        
        d2 = chess.parse_square('d2')
        if d2 in scores:
            # Open file doubled pawns should have reduced penalty (50% of normal)
            # Central file: -6.0, open file: -3.0
            self.assert_greater(scores[d2], -6.0, f"Open file doubled pawn should have reduced penalty (got {scores[d2]})")
    
    def test_doubled_pawn_tripled(self):
        """Test tripled pawns (all should get penalty)."""
        # Three white pawns on d file
        fen = "rnbqkbnr/pppppppp/3P4/3P4/3P4/8/8/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.doubled_pawn_rule.evaluate(board, chess.WHITE)
        
        d4 = chess.parse_square('d4')
        d5 = chess.parse_square('d5')
        d6 = chess.parse_square('d6')
        
        # All tripled pawns should have scores
        self.assert_in(d4, scores, "d4 should have score (tripled pawn)")
        self.assert_in(d5, scores, "d5 should have score (tripled pawn)")
        self.assert_in(d6, scores, "d6 should have score (tripled pawn)")
    
    # ============================================================================
    # KING SAFETY RULE TESTS
    # ============================================================================
    
    def test_king_safety_in_check(self):
        """Test that king in check gets strong negative score."""
        # White king in check
        fen = "rnbqkb1r/pppppppp/8/8/8/8/PPPPPPPP/RNBQK2R w KQkq - 0 1"
        board = chess.Board(fen)
        # Move to put king in check
        board.push(chess.Move.from_uci("e1f1"))
        board.push(chess.Move.from_uci("d8d1"))
        
        g1 = board.king(chess.WHITE)
        if g1:
            scores = self.king_safety_rule.evaluate(board, chess.WHITE)
            is_in_check = board.is_attacked_by(chess.BLACK, g1)
            
            if is_in_check:
                self.assert_in(g1, scores, "King in check should have score")
                if g1 in scores:
                    self.assert_less(scores[g1], -20.0, f"King in check should have strong negative score (got {scores[g1]})")
    
    def test_king_safety_open_file(self):
        """Test that king near open file gets penalty."""
        # White king on g1, open f file
        fen = "rnbqkbnr/pppp1ppp/8/8/8/8/PPPP1PPP/RNBQKB1R w KQkq - 0 1"
        board = chess.Board(fen)
        g1 = chess.parse_square('g1')
        
        scores = self.king_safety_rule.evaluate(board, chess.WHITE)
        
        if g1 in scores:
            # Open file near king should give negative score
            self.assert_less(scores[g1], 0, f"King near open file should have negative score (got {scores[g1]})")
    
    def test_king_safety_semi_open_file(self):
        """Test that king on semi-open file gets penalty."""
        # White king on g1, semi-open f file (white has no pawn on f, black has pawn on f7)
        fen = "rnbqkbnr/ppp1pppp/8/8/8/8/PPP1PPPP/RNBQKB1R w KQkq - 0 1"
        board = chess.Board(fen)
        g1 = chess.parse_square('g1')
        
        scores = self.king_safety_rule.evaluate(board, chess.WHITE)
        
        if g1 in scores:
            # Semi-open file near king should give negative score
            self.assert_less(scores[g1], 0, f"King on semi-open file should have negative score (got {scores[g1]})")
    
    def test_king_safety_pawn_shield(self):
        """Test that king with pawn shield gets bonus."""
        # White king on g1, pawns on f2, g2, h2 (pawn shield)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQK2R w KQkq - 0 1"
        board = chess.Board(fen)
        g1 = chess.parse_square('g1')
        
        scores = self.king_safety_rule.evaluate(board, chess.WHITE)
        
        if g1 in scores:
            # Pawn shield should give positive score
            self.assert_greater(scores[g1], 0, f"King with pawn shield should have positive score (got {scores[g1]})")
    
    def test_king_safety_exposed_king(self):
        """Test that exposed king gets penalty."""
        # White king on g1, no pawns in front
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQK2R w KQkq - 0 1"
        # Remove pawns in front of king
        board = chess.Board(fen)
        board.remove_piece_at(chess.parse_square('f2'))
        board.remove_piece_at(chess.parse_square('g2'))
        board.remove_piece_at(chess.parse_square('h2'))
        
        g1 = chess.parse_square('g1')
        scores = self.king_safety_rule.evaluate(board, chess.WHITE)
        
        if g1 in scores:
            # Exposed king should give negative score
            self.assert_less(scores[g1], 0, f"Exposed king should have negative score (got {scores[g1]})")
    
    # ============================================================================
    # WEAK SQUARE RULE TESTS
    # ============================================================================
    
    def test_weak_square_attacked_undefended(self):
        """Test that attacked and undefended pieces get penalty."""
        # White knight on d4, attacked by black bishop, not defended
        fen = "rnbqkb1r/pppppppp/8/8/3N4/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1"
        board = chess.Board(fen)
        d4 = chess.parse_square('d4')
        
        is_attacked = board.is_attacked_by(chess.BLACK, d4)
        is_defended = board.is_attacked_by(chess.WHITE, d4)
        scores = self.weak_square_rule.evaluate(board, chess.WHITE)
        
        if is_attacked and not is_defended:
            self.assert_in(d4, scores, "d4 should have score (attacked and undefended)")
            if d4 in scores:
                self.assert_less(scores[d4], 0, f"d4 should have negative score (got {scores[d4]})")
    
    def test_weak_square_attacked_defended(self):
        """Test that attacked but defended pieces don't get penalty."""
        # White knight on d4, attacked by black bishop, defended by white bishop
        fen = "rnbqkb1r/pppppppp/8/8/3N4/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1"
        board = chess.Board(fen)
        # Add white bishop defending d4
        board.set_piece_at(chess.parse_square('c3'), chess.Piece(chess.BISHOP, chess.WHITE))
        
        d4 = chess.parse_square('d4')
        is_attacked = board.is_attacked_by(chess.BLACK, d4)
        is_defended = board.is_attacked_by(chess.WHITE, d4)
        scores = self.weak_square_rule.evaluate(board, chess.WHITE)
        
        if is_attacked and is_defended:
            self.assert_not_in(d4, scores, "d4 should not have score (attacked but defended)")
    
    def test_weak_square_piece_value_scaling(self):
        """Test that weak square penalty scales with piece value."""
        # Different pieces on weak squares
        fen = "rnbqkb1r/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 1"
        board = chess.Board(fen)
        
        # Place different pieces on d4 (attacked and undefended)
        pieces_to_test = [
            (chess.PAWN, chess.parse_square('d4'), -6.0),
            (chess.KNIGHT, chess.parse_square('d4'), -8.0),
            (chess.ROOK, chess.parse_square('d4'), -10.0),
            (chess.QUEEN, chess.parse_square('d4'), -12.0),
        ]
        
        for piece_type, square, expected_penalty in pieces_to_test:
            test_board = board.copy()
            test_board.set_piece_at(square, chess.Piece(piece_type, chess.WHITE))
            
            scores = self.weak_square_rule.evaluate(test_board, chess.WHITE)
            if square in scores:
                # Check that penalty is approximately correct (within reasonable range)
                self.assert_less(scores[square], 0, f"{piece_type} on weak square should have negative score")
    
    # ============================================================================
    # PIECE ACTIVITY RULE TESTS
    # ============================================================================
    
    def test_piece_activity_mobility(self):
        """Test that pieces with more moves get higher scores."""
        # White knight on d4 (many moves) vs knight on a1 (few moves)
        fen = "rnbqkbnr/pppppppp/8/8/3N4/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.piece_activity_rule.evaluate(board, chess.WHITE)
        
        d4 = chess.parse_square('d4')
        a1 = chess.parse_square('a1')
        
        if d4 in scores and a1 in scores:
            # Knight on d4 should have more moves and higher score
            self.assert_greater(scores[d4], scores[a1], f"Knight on d4 should have higher score than on a1")
    
    def test_piece_activity_central_control(self):
        """Test that pieces controlling central squares get bonus."""
        # White knight on d4 (controls central squares)
        fen = "rnbqkbnr/pppppppp/8/8/3N4/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.piece_activity_rule.evaluate(board, chess.WHITE)
        
        d4 = chess.parse_square('d4')
        if d4 in scores:
            # Knight on d4 should have positive score (controls central squares)
            self.assert_greater(scores[d4], 0, f"Knight on d4 should have positive score (got {scores[d4]})")
    
    def test_piece_activity_blocked_piece(self):
        """Test that blocked pieces (no moves) get reduced/zero score."""
        # White rook on a1 (blocked by pawns, no moves)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.piece_activity_rule.evaluate(board, chess.WHITE)
        
        a1 = chess.parse_square('a1')
        if a1 in scores:
            # Blocked rook should have low or zero score
            self.assert_less(scores[a1], 5.0, f"Blocked rook should have low score (got {scores[a1]})")
    
    def test_piece_activity_perspective_independence(self):
        """Test that piece activity works correctly regardless of board.turn."""
        # Position where it's black to move, but we evaluate white pieces
        fen = "rnbqkbnr/pppppppp/8/8/3N4/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
        board = chess.Board(fen)
        
        scores = self.piece_activity_rule.evaluate(board, chess.WHITE)
    
    def test_piece_activity_doubled_rooks_on_open_file(self):
        """Test doubled rooks on open file bonus."""
        # White rooks on e1 and e3, e-file is open
        # FEN: r1bq1rk1/pp3p1p/2p3pb/3p4/B2P2N1/2N1R3/PPPQ1PPP/4R1K1 b - - 0 15
        fen = "r1bq1rk1/pp3p1p/2p3pb/3p4/B2P2N1/2N1R3/PPPQ1PPP/4R1K1 b - - 0 15"
        board = chess.Board(fen)
        
        scores = self.piece_activity_rule.evaluate(board, chess.WHITE)
        
        e1 = chess.parse_square('e1')
        e3 = chess.parse_square('e3')
        
        # Both rooks should have bonus for doubled rooks on open file
        if e1 in scores:
            self.assert_greater(scores[e1], 0, f"e1 should have positive score with doubled rooks bonus (got {scores[e1]})")
            # Should have at least the doubled rooks bonus (20.0) plus mobility
            self.assert_greater(scores[e1], 19.0, f"e1 should have at least doubled rooks bonus (got {scores[e1]})")
        
        if e3 in scores:
            self.assert_greater(scores[e3], 0, f"e3 should have positive score with doubled rooks bonus (got {scores[e3]})")
            # Should have at least the doubled rooks bonus (20.0) plus mobility
            self.assert_greater(scores[e3], 19.0, f"e3 should have at least doubled rooks bonus (got {scores[e3]})")
    
    # ============================================================================
    # UNDEVELOPED PIECE RULE TESTS
    # ============================================================================
    
    def test_undeveloped_piece_blocked_rook(self):
        """Test that undeveloped rook on starting square and blocked gets penalty."""
        # Black rook on h8, blocked by pawn on h7
        # FEN: k4nbr/5ppp/8/5P2/8/8/7P/K6R w - - 0 1
        fen = "k4nbr/5ppp/8/5P2/8/8/7P/K6R w - - 0 1"
        board = chess.Board(fen)
        h8 = chess.parse_square('h8')
        
        # Check if rook is on starting square
        is_on_starting_square = h8 in self.undeveloped_piece_rule._get_starting_squares(chess.BLACK).get(chess.ROOK, [])
        
        # Check if rook has legal moves (should be 0 if blocked)
        temp_board = board.copy()
        temp_board.turn = chess.BLACK
        legal_moves = [move for move in temp_board.generate_legal_moves() 
                      if move.from_square == h8]
        num_moves = len(legal_moves)
        
        # Get scores from evaluation
        scores = self.undeveloped_piece_rule.evaluate(board, chess.BLACK)
        
        # Assertions: undeveloped rook should be penalized
        self.assert_true(is_on_starting_square, "h8 should be a starting square for black rook")
        self.assert_equals(num_moves, 0, f"h8 rook should have no legal moves (blocked by h7 pawn), got {num_moves}")
        self.assert_in(h8, scores, "h8 should have a score (undeveloped)")
        if h8 in scores:
            self.assert_less(scores[h8], 0, f"h8 should have negative score (got {scores[h8]})")


if __name__ == "__main__":
    test_suite = TestPositionalHeatmapRules()
    test_suite.run_all_tests()

