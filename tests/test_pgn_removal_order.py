"""Unit tests for different orderings of PGN removal operations.

This test suite validates that removing different PGN elements (non-standard tags,
comments, variations, annotations) in different orders produces correct results
and preserves move parsing.
"""

import unittest
import re
import chess.pgn
from io import StringIO

from app.services.pgn_formatter_service import PgnFormatterService


class TestPgnRemovalOrder(unittest.TestCase):
    """Test different orderings of PGN removal operations."""
    
    # Test PGN with all elements: non-standard tags, comments, variations, annotations
    # Includes edge cases: multi-line comments, nested variations, comments in variations
    TEST_PGN = """[Event "Test Game"]
[Site "Test Site"]
[Date "2025.01.01"]
[Round "1"]
[White "Test White"]
[Black "Test Black"]
[Result "1-0"]

{ [%evp 1,2,3,4,5] [%mdl 8192] [%clk 0:05:00] }
1. e4! { Opening comment } c5? { [%eval 50,20] [%wdl 100,0,0] } (1... e5 { Variation comment } 2. Nf3 Nc6) 2. c3 { [%eval 30,18] } Nf6 3. Qc2 { Middle game comment } e5 (3... d5 { Another variation } 4. d4) 4. d3 { [%mdl 4096] Endgame comment } Nc6 5. h3 d5 6. Nf3 { [%cal Re1e2] } 6... d4 $146 (6... h6 { [%eval -50,15] } 7. Be2 Be7) 7. Bg5 { [%eval -106,29] [%wdl 1,444,555] } (7. Nbd2 $15 { [%eval -63,29] } ) 7... h6 $17 8. Bh4 { Final comment } 8... g5! { [%eval -89,26] } (8... Be6 { [%eval -135,21] } 9. Be2 Bd6) 9. cxd4 $2 { [%eval -386,23] [%mdl 8192] [#] } (9. Bg3 $17 { [%eval -89,26] } ) 9... Nxd4 $2 { [%eval -94,24] } (9... gxh4 $19 { [%eval -386,23] } 10. d5 Nd4) 10. Qc3 $2 { [%eval -539,22] [%mdl 8192] } (10. Nxd4 $17 { [%eval -94,24] } 10... Qxd4) 10... Nxf3+ 11. Ke2 { [%eval -778,22] } (11. gxf3 $142 { [%eval -475,26] } 11... gxh4) 11... Nxh4 12. Qa3 c4 13. Qc3 Qd4 14. Ke1 Qxc3+ 15. Nxc3 Ng6 16. dxc4 Be6 17. Rc1 Bxc4 18. Bxc4 b6 19. Ke2 O-O-O 20. Rhd1 Bd6 21. b3 Nf4+ 22. Ke1 Nxg2+ 23. Kd2 Bb4+ 24. Bd5 Bxc3+ 25. Rxc3+ Kd7 26. b4 Nxd5 27. exd5 Nf4 28. Ke1 Ke7 29. Rc7+ Rd7 30. Rd2 Rxc7 31. d6+ Kd7 32. dxc7+ Kxc7 $19 { [%mdl 4096] Endspiel } 33. Rd1 Rd8 34. a3 Rxd1+ { Comment } 35. Kxd1 Nxh3 36. Kd2 Nxf2 37. Kc3 Ne4+ 38. Kc2 a5 39. bxa5 bxa5 40. Kc1 h5 41. a4 Nc3 42. Kb2 Nxa4+ 43. Kb3 Nc5+ 44. Kc2 Kd6 45. Kb2 Kd5 46. Kc2 Kd4 47. Kb1 Kc3 48. Ka1 Kb3 49. Kb1 Nd3 50. Ka1 Nf2 51. Kb1 Nd1 52. Kc1 Ne3 53. Kb1 h4 54. Kc1 h3 55. Kb1 h2 56. Ka1 h1=N 57. Kb1 Nf2 58. Kc1 Nd3+ 59. Kb1 Nd1 60. Ka1 Nb4 61. Kb1 Nc3+ 62. Kc1 Nba2+ 63. Kd2 Nb1+ 64. Kd3 Nb4+ 65. Ke4 Nc6 66. Kd3 g4 67. Ke3 a4 68. Kf2 a3 69. Kg1 a2 70. Kf2 a1=B 71. Kg3 e4 72. Kf4 g3 73. Kxe4 g2 74. Kf5 g1=B 75. Kg4 Ne5+ 76. Kg3 Nd2 77. Kf4 Bh2+ 78. Ke3 Kc3 79. Ke2 Bf4 80. Kf2 Nd3+ 81. Ke2 Bb2 82. Kd1 Nf2+ 83. Ke1 Bg3 84. Ke2 Bc1 85. Ke3 Nf1+ 86. Kf3 Kd4 87. Ke2 f6 88. Ke1 Ne3 89. Ke2 Ke4 90. Ke1 Nd3+ 91. Ke2 Nf4# { Final game comment } 1-0"""
    
    # Edge case PGN with multi-line comment and complex nested structures
    EDGE_CASE_PGN = """[Event "Edge Case Test"]
[Site "Test"]
[Date "2025.01.01"]
[Round "1"]
[White "White"]
[Black "Black"]
[Result "1-0"]

{ [%evp 1,2,3] [%mdl 8192]
This is a multi-line comment
that spans multiple lines
[%eval 50,20] [%wdl 100,0,0] }
1. e4! { Comment with [%eval 30,18] inside } c5? (1... e5 { Variation with [%eval -50,15] } 2. Nf3 (2. d4 { Nested variation } d5) Nc6) 2. c3 $146 { [%mdl 4096] } Nf6 3. Qc2!? e5 (3... d5 { Another variation } 4. d4) 4. d3 { [%cal Re1e2] } Nc6 5. h3 d5 6. Nf3 { [%eval -106,29] [%wdl 1,444,555] } 6... d4 $2 (6... h6 { [%eval -50,15] } 7. Be2 Be7) 7. Bg5 { [%eval -106,29] } (7. Nbd2 $15 { [%eval -63,29] } ) 7... h6 $17 8. Bh4 { Comment } 8... g5! { [%eval -89,26] } (8... Be6 { [%eval -135,21] } 9. Be2 Bd6) 9. cxd4 $2 { [%eval -386,23] [%mdl 8192] } (9. Bg3 $17 { [%eval -89,26] } ) 9... Nxd4 $2 { [%eval -94,24] } 9... gxh4 $19 { [%eval -386,23] } 10. d5 Nd4 10. Qc3 $2 { [%eval -539,22] [%mdl 8192] } 10... Nxf3+ 11. Ke2 { [%eval -778,22] } 11... Nxh4 12. Qa3 c4 13. Qc3 Qd4 14. Ke1 Qxc3+ 15. Nxc3 Ng6 16. dxc4 Be6 17. Rc1 Bxc4 18. Bxc4 b6 19. Ke2 O-O-O 20. Rhd1 Bd6 21. b3 Nf4+ 22. Ke1 Nxg2+ 23. Kd2 Bb4+ 24. Bd5 Bxc3+ 25. Rxc3+ Kd7 26. b4 Nxd5 27. exd5 Nf4 28. Ke1 Ke7 29. Rc7+ Rd7 30. Rd2 Rxc7 31. d6+ Kd7 32. dxc7+ Kxc7 $19 { [%mdl 4096] } 33. Rd1 Rd8 34. a3 Rxd1+ { Comment } 35. Kxd1 Nxh3 36. Kd2 Nxf2 37. Kc3 Ne4+ 38. Kc2 a5 39. bxa5 bxa5 40. Kc1 h5 41. a4 Nc3 42. Kb2 Nxa4+ 43. Kb3 Nc5+ 44. Kc2 Kd6 45. Kb2 Kd5 46. Kc2 Kd4 47. Kb1 Kc3 48. Ka1 Kb3 49. Kb1 Nd3 50. Ka1 Nf2 51. Kb1 Nd1 52. Kc1 Ne3 53. Kb1 h4 54. Kc1 h3 55. Kb1 h2 56. Ka1 h1=N 57. Kb1 Nf2 58. Kc1 Nd3+ 59. Kb1 Nd1 60. Ka1 Nb4 61. Kb1 Nc3+ 62. Kc1 Nba2+ 63. Kd2 Nb1+ 64. Kd3 Nb4+ 65. Ke4 Nc6 66. Kd3 g4 67. Ke3 a4 68. Kf2 a3 69. Kg1 a2 70. Kf2 a1=B 71. Kg3 e4 72. Kf4 g3 73. Kxe4 g2 74. Kf5 g1=B 75. Kg4 Ne5+ 76. Kg3 Nd2 77. Kf4 Bh2+ 78. Ke3 Kc3 79. Ke2 Bf4 80. Kf2 Nd3+ 81. Ke2 Bb2 82. Kd1 Nf2+ 83. Ke1 Bg3 84. Ke2 Bc1 85. Ke3 Nf1+ 86. Kf3 Kd4 87. Ke2 f6 88. Ke1 Ne3 89. Ke2 Ke4 90. Ke1 Nd3+ 91. Ke2 Nf4# { Final comment } 1-0"""
    
    def _count_moves(self, pgn_text: str) -> int:
        """Count moves in a PGN string."""
        game = chess.pgn.read_game(StringIO(pgn_text))
        if game is None:
            return -1
        return sum(1 for _ in game.mainline())
    
    def _test_removal_order(self, removal_functions, order_name: str):
        """Test a specific order of removal operations.
        
        Args:
            removal_functions: List of (function, name) tuples to apply in order
            order_name: Descriptive name for this order
        """
        pgn = self.TEST_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Original PGN should be parseable")
        
        # Track which removals were applied
        removed_non_standard_tags = False
        removed_comments = False
        removed_variations = False
        removed_annotations = False
        
        # Apply removals in order
        for func, func_name in removal_functions:
            pgn = func(pgn)
            # Verify PGN is still parseable after each step
            moves_after = self._count_moves(pgn)
            self.assertGreater(
                moves_after, 0,
                f"PGN should be parseable after {func_name} in order: {order_name}"
            )
            
            # Track which removals were applied
            if func == PgnFormatterService._remove_non_standard_tags:
                removed_non_standard_tags = True
            elif func == PgnFormatterService._remove_comments:
                removed_comments = True
            elif func == PgnFormatterService._remove_variations:
                removed_variations = True
            elif func == PgnFormatterService._remove_annotations:
                removed_annotations = True
        
        # Final verification
        final_moves = self._count_moves(pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved for order: {order_name} "
            f"(original: {original_moves}, final: {final_moves})"
        )
        
        # Verify no non-standard tags remain (if removed)
        if removed_non_standard_tags:
            self.assertNotIn('[%evp', pgn)
            self.assertNotIn('[%mdl', pgn)
            self.assertNotIn('[%clk', pgn)
            self.assertNotIn('[%eval', pgn)
            self.assertNotIn('[%wdl', pgn)
            self.assertNotIn('[%cal', pgn)
        
        # Verify no comments remain (if removed)
        if removed_comments:
            self.assertNotIn('{', pgn)
            self.assertNotIn('}', pgn)
        
        # Verify no variations remain (if removed)
        if removed_variations:
            self.assertNotIn('(', pgn)
            self.assertNotIn(')', pgn)
        
        # Verify no annotations remain (if removed)
        if removed_annotations:
            # Annotations are !, !!, ?, ??, !?, ?!
            self.assertIsNone(
                re.search(r'[!?]{1,2}', pgn),
                "Annotations (!, !!, ?, etc.) should be removed"
            )
            # NAGs ($1, $2, etc.)
            self.assertIsNone(
                re.search(r'\$\d+', pgn),
                "NAGs ($1, $2, etc.) should be removed"
            )
        
        return final_moves
    
    def test_order_1_non_standard_tags_then_comments(self):
        """Test: Remove non-standard tags, then comments."""
        removals = [
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_comments, "comments"),
        ]
        self._test_removal_order(removals, "non-standard tags → comments")
    
    def test_order_2_comments_then_non_standard_tags(self):
        """Test: Remove comments, then non-standard tags."""
        removals = [
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
        ]
        # Note: This order might not make sense since non-standard tags are in comments,
        # but we test it to ensure it doesn't break
        self._test_removal_order(removals, "comments → non-standard tags")
    
    def test_order_3_non_standard_tags_then_variations(self):
        """Test: Remove non-standard tags, then variations."""
        removals = [
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_variations, "variations"),
        ]
        self._test_removal_order(removals, "non-standard tags → variations")
    
    def test_order_4_variations_then_non_standard_tags(self):
        """Test: Remove variations, then non-standard tags."""
        removals = [
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
        ]
        self._test_removal_order(removals, "variations → non-standard tags")
    
    def test_order_5_comments_then_variations(self):
        """Test: Remove comments, then variations."""
        removals = [
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_variations, "variations"),
        ]
        self._test_removal_order(removals, "comments → variations")
    
    def test_order_6_variations_then_comments(self):
        """Test: Remove variations, then comments."""
        removals = [
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_comments, "comments"),
        ]
        self._test_removal_order(removals, "variations → comments")
    
    def test_order_7_non_standard_tags_then_annotations(self):
        """Test: Remove non-standard tags, then annotations."""
        removals = [
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_annotations, "annotations"),
        ]
        self._test_removal_order(removals, "non-standard tags → annotations")
    
    def test_order_8_annotations_then_non_standard_tags(self):
        """Test: Remove annotations, then non-standard tags."""
        removals = [
            (PgnFormatterService._remove_annotations, "annotations"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
        ]
        self._test_removal_order(removals, "annotations → non-standard tags")
    
    def test_order_9_all_removals_standard_order(self):
        """Test: Remove all elements in recommended order."""
        removals = [
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_annotations, "annotations"),
        ]
        self._test_removal_order(removals, "all removals (standard order)")
    
    def test_order_10_all_removals_reverse_order(self):
        """Test: Remove all elements in reverse order."""
        removals = [
            (PgnFormatterService._remove_annotations, "annotations"),
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
        ]
        self._test_removal_order(removals, "all removals (reverse order)")
    
    def test_order_11_all_removals_mixed_order_1(self):
        """Test: Remove all elements in mixed order 1."""
        removals = [
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_annotations, "annotations"),
            (PgnFormatterService._remove_comments, "comments"),
        ]
        self._test_removal_order(removals, "all removals (mixed order 1)")
    
    def test_order_12_all_removals_mixed_order_2(self):
        """Test: Remove all elements in mixed order 2."""
        removals = [
            (PgnFormatterService._remove_annotations, "annotations"),
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_variations, "variations"),
        ]
        self._test_removal_order(removals, "all removals (mixed order 2)")
    
    def test_order_13_comments_variations_annotations(self):
        """Test: Remove comments, variations, annotations (no non-standard tags)."""
        removals = [
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_annotations, "annotations"),
        ]
        self._test_removal_order(removals, "comments → variations → annotations")
    
    def test_order_14_non_standard_tags_comments_variations(self):
        """Test: Remove non-standard tags, comments, variations."""
        removals = [
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_variations, "variations"),
        ]
        self._test_removal_order(removals, "non-standard tags → comments → variations")
    
    def test_order_15_variations_comments_annotations(self):
        """Test: Remove variations, comments, annotations."""
        removals = [
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_comments, "comments"),
            (PgnFormatterService._remove_annotations, "annotations"),
        ]
        self._test_removal_order(removals, "variations → comments → annotations")
    
    def test_edge_case_multi_line_comment_standard_order(self):
        """Test edge case: Multi-line comment with non-standard tags in standard order."""
        pgn = self.EDGE_CASE_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Edge case PGN should be parseable")
        
        # Standard order: non-standard tags, then comments
        pgn = PgnFormatterService._remove_non_standard_tags(pgn)
        moves_after_tags = self._count_moves(pgn)
        self.assertEqual(
            original_moves, moves_after_tags,
            "Move count should be preserved after removing non-standard tags"
        )
        
        pgn = PgnFormatterService._remove_comments(pgn)
        final_moves = self._count_moves(pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved for edge case "
            f"(original: {original_moves}, final: {final_moves})"
        )
        
        # Verify removals
        self.assertNotIn('[%evp', pgn)
        self.assertNotIn('[%eval', pgn)
        self.assertNotIn('[%mdl', pgn)
        self.assertNotIn('{', pgn)
        self.assertNotIn('}', pgn)
    
    def test_edge_case_all_removals_mixed_order(self):
        """Test edge case: All removals in mixed order."""
        pgn = self.EDGE_CASE_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Edge case PGN should be parseable")
        
        # Mixed order: variations, non-standard tags, annotations, comments
        removals = [
            (PgnFormatterService._remove_variations, "variations"),
            (PgnFormatterService._remove_non_standard_tags, "non-standard tags"),
            (PgnFormatterService._remove_annotations, "annotations"),
            (PgnFormatterService._remove_comments, "comments"),
        ]
        
        for func, func_name in removals:
            pgn = func(pgn)
            moves_after = self._count_moves(pgn)
            self.assertGreater(
                moves_after, 0,
                f"Edge case PGN should be parseable after {func_name}"
            )
        
        final_moves = self._count_moves(pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved for edge case with all removals "
            f"(original: {original_moves}, final: {final_moves})"
        )
        
        # Verify all removals
        self.assertNotIn('[%evp', pgn)
        self.assertNotIn('[%eval', pgn)
        self.assertNotIn('[%mdl', pgn)
        self.assertNotIn('{', pgn)
        self.assertNotIn('}', pgn)
        self.assertNotIn('(', pgn)
        self.assertNotIn(')', pgn)
        self.assertIsNone(
            re.search(r'[!?]{1,2}', pgn),
            "Annotations (!, !!, ?, etc.) should be removed"
        )
        self.assertIsNone(
            re.search(r'\$\d+', pgn),
            "NAGs ($1, $2, etc.) should be removed"
        )


if __name__ == '__main__':
    unittest.main()

