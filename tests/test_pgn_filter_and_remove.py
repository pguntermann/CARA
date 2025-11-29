"""Unit tests combining show/hide filtering with removal operations.

This test suite validates that combining filter_pgn_for_display (show/hide)
with permanent removal operations works correctly and preserves move parsing.
"""

import unittest
import re
import chess.pgn
from io import StringIO

from app.services.pgn_formatter_service import PgnFormatterService


class TestPgnFilterAndRemove(unittest.TestCase):
    """Test combining show/hide filtering with removal operations."""
    
    # Test PGN with all elements: non-standard tags, comments, variations, annotations
    TEST_PGN = """[Event "Test Game"]
[Site "Test Site"]
[Date "2025.01.01"]
[Round "1"]
[White "Test White"]
[Black "Test Black"]
[Result "1-0"]

{ [%evp 1,2,3,4,5] [%mdl 8192] [%clk 0:05:00] }
1. e4! { Opening comment } c5? { [%eval 50,20] [%wdl 100,0,0] } (1... e5 { Variation comment } 2. Nf3 Nc6) 2. c3 { [%eval 30,18] } Nf6 3. Qc2 { Middle game comment } e5 (3... d5 { Another variation } 4. d4) 4. d3 { [%mdl 4096] Endgame comment } Nc6 5. h3 d5 6. Nf3 { [%cal Re1e2] } 6... d4 $146 (6... h6 { [%eval -50,15] } 7. Be2 Be7) 7. Bg5 { [%eval -106,29] [%wdl 1,444,555] } (7. Nbd2 $15 { [%eval -63,29] } ) 7... h6 $17 8. Bh4 { Final comment } 8... g5! { [%eval -89,26] } (8... Be6 { [%eval -135,21] } 9. Be2 Bd6) 9. cxd4 $2 { [%eval -386,23] [%mdl 8192] [#] } (9. Bg3 $17 { [%eval -89,26] } ) 9... Nxd4 $2 { [%eval -94,24] } (9... gxh4 $19 { [%eval -386,23] } 10. d5 Nd4) 10. Qc3 $2 { [%eval -539,22] [%mdl 8192] } (10. Nxd4 $17 { [%eval -94,24] } 10... Qxd4) 10... Nxf3+ 11. Ke2 { [%eval -778,22] } (11. gxf3 $142 { [%eval -475,26] } 11... gxh4) 11... Nxh4 12. Qa3 c4 13. Qc3 Qd4 14. Ke1 Qxc3+ 15. Nxc3 Ng6 16. dxc4 Be6 17. Rc1 Bxc4 18. Bxc4 b6 19. Ke2 O-O-O 20. Rhd1 Bd6 21. b3 Nf4+ 22. Ke1 Nxg2+ 23. Kd2 Bb4+ 24. Bd5 Bxc3+ 25. Rxc3+ Kd7 26. b4 Nxd5 27. exd5 Nf4 28. Ke1 Ke7 29. Rc7+ Rd7 30. Rd2 Rxc7 31. d6+ Kd7 32. dxc7+ Kxc7 $19 { [%mdl 4096] Endspiel } 33. Rd1 Rd8 34. a3 Rxd1+ { Comment } 35. Kxd1 Nxh3 36. Kd2 Nxf2 37. Kc3 Ne4+ 38. Kc2 a5 39. bxa5 bxa5 40. Kc1 h5 41. a4 Nc3 42. Kb2 Nxa4+ 43. Kb3 Nc5+ 44. Kc2 Kd6 45. Kb2 Kd5 46. Kc2 Kd4 47. Kb1 Kc3 48. Ka1 Kb3 49. Kb1 Nd3 50. Ka1 Nf2 51. Kb1 Nd1 52. Kc1 Ne3 53. Kb1 h4 54. Kc1 h3 55. Kb1 h2 56. Ka1 h1=N 57. Kb1 Nf2 58. Kc1 Nd3+ 59. Kb1 Nd1 60. Ka1 Nb4 61. Kb1 Nc3+ 62. Kc1 Nba2+ 63. Kd2 Nb1+ 64. Kd3 Nb4+ 65. Ke4 Nc6 66. Kd3 g4 67. Ke3 a4 68. Kf2 a3 69. Kg1 a2 70. Kf2 a1=B 71. Kg3 e4 72. Kf4 g3 73. Kxe4 g2 74. Kf5 g1=B 75. Kg4 Ne5+ 76. Kg3 Nd2 77. Kf4 Bh2+ 78. Ke3 Kc3 79. Ke2 Bf4 80. Kf2 Nd3+ 81. Ke2 Bb2 82. Kd1 Nf2+ 83. Ke1 Bg3 84. Ke2 Bc1 85. Ke3 Nf1+ 86. Kf3 Kd4 87. Ke2 f6 88. Ke1 Ne3 89. Ke2 Ke4 90. Ke1 Nd3+ 91. Ke2 Nf4# { Final game comment } 1-0"""
    
    def _count_moves(self, pgn_text: str) -> int:
        """Count moves in a PGN string."""
        game = chess.pgn.read_game(StringIO(pgn_text))
        if game is None:
            return -1
        return sum(1 for _ in game.mainline())
    
    def _test_filter_then_remove(self, filter_kwargs: dict, removal_func, removal_name: str, test_name: str):
        """Test filtering (show/hide) followed by a removal operation.
        
        Args:
            filter_kwargs: Keyword arguments for filter_pgn_for_display
            removal_func: Function to apply after filtering
            removal_name: Name of the removal operation
            test_name: Descriptive name for this test
        """
        pgn = self.TEST_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Original PGN should be parseable")
        
        # Step 1: Apply filtering (show/hide)
        filtered_pgn = PgnFormatterService.filter_pgn_for_display(pgn, **filter_kwargs)
        moves_after_filter = self._count_moves(filtered_pgn)
        self.assertEqual(
            original_moves, moves_after_filter,
            f"Move count should be preserved after filtering in test: {test_name}"
        )
        
        # Step 2: Apply removal operation
        final_pgn = removal_func(filtered_pgn)
        final_moves = self._count_moves(final_pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved after {removal_name} in test: {test_name} "
            f"(original: {original_moves}, final: {final_moves})"
        )
        
        return final_pgn, final_moves
    
    def test_hide_comments_then_remove_variations(self):
        """Test: Hide comments via filter, then permanently remove variations."""
        filter_kwargs = {
            'show_comments': False,
            'show_metadata': True,
            'show_variations': True,
            'show_annotations': True,
            'show_results': True,
            'show_non_standard_tags': False
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_variations,
            "removing variations",
            "hide comments then remove variations"
        )
    
    def test_hide_variations_then_remove_comments(self):
        """Test: Hide variations via filter, then permanently remove comments."""
        filter_kwargs = {
            'show_variations': False,
            'show_metadata': True,
            'show_comments': True,
            'show_annotations': True,
            'show_results': True,
            'show_non_standard_tags': False
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_comments,
            "removing comments",
            "hide variations then remove comments"
        )
    
    def test_hide_annotations_then_remove_comments(self):
        """Test: Hide annotations via filter, then permanently remove comments."""
        filter_kwargs = {
            'show_annotations': False,
            'show_metadata': True,
            'show_comments': True,
            'show_variations': True,
            'show_results': True,
            'show_non_standard_tags': False
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_comments,
            "removing comments",
            "hide annotations then remove comments"
        )
    
    def test_hide_non_standard_tags_then_remove_comments(self):
        """Test: Hide non-standard tags via filter, then permanently remove comments."""
        filter_kwargs = {
            'show_non_standard_tags': False,
            'show_metadata': True,
            'show_comments': True,
            'show_variations': True,
            'show_annotations': True,
            'show_results': True
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_comments,
            "removing comments",
            "hide non-standard tags then remove comments"
        )
    
    def test_hide_comments_then_remove_annotations(self):
        """Test: Hide comments via filter, then permanently remove annotations."""
        filter_kwargs = {
            'show_comments': False,
            'show_metadata': True,
            'show_variations': True,
            'show_annotations': True,
            'show_results': True,
            'show_non_standard_tags': False
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_annotations,
            "removing annotations",
            "hide comments then remove annotations"
        )
    
    def test_hide_all_then_remove_variations(self):
        """Test: Hide all optional elements via filter, then permanently remove variations."""
        filter_kwargs = {
            'show_metadata': False,
            'show_comments': False,
            'show_variations': False,
            'show_annotations': False,
            'show_results': False,
            'show_non_standard_tags': False
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_variations,
            "removing variations",
            "hide all then remove variations"
        )
    
    def test_show_all_then_remove_non_standard_tags(self):
        """Test: Show all via filter, then permanently remove non-standard tags."""
        filter_kwargs = {
            'show_metadata': True,
            'show_comments': True,
            'show_variations': True,
            'show_annotations': True,
            'show_results': True,
            'show_non_standard_tags': True
        }
        final_pgn, final_moves = self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_non_standard_tags,
            "removing non-standard tags",
            "show all then remove non-standard tags"
        )
        # Verify non-standard tags are removed
        self.assertNotIn('[%evp', final_pgn)
        self.assertNotIn('[%eval', final_pgn)
        self.assertNotIn('[%mdl', final_pgn)
    
    def test_hide_comments_and_variations_then_remove_annotations(self):
        """Test: Hide comments and variations via filter, then permanently remove annotations."""
        filter_kwargs = {
            'show_comments': False,
            'show_variations': False,
            'show_metadata': True,
            'show_annotations': True,
            'show_results': True,
            'show_non_standard_tags': False
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_annotations,
            "removing annotations",
            "hide comments and variations then remove annotations"
        )
    
    def test_hide_non_standard_tags_then_remove_variations(self):
        """Test: Hide non-standard tags via filter, then permanently remove variations."""
        filter_kwargs = {
            'show_non_standard_tags': False,
            'show_metadata': True,
            'show_comments': True,
            'show_variations': True,
            'show_annotations': True,
            'show_results': True
        }
        self._test_filter_then_remove(
            filter_kwargs,
            PgnFormatterService._remove_variations,
            "removing variations",
            "hide non-standard tags then remove variations"
        )
    
    def test_remove_then_filter_chain(self):
        """Test: Apply removal, then filter, then another removal."""
        pgn = self.TEST_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Original PGN should be parseable")
        
        # Step 1: Remove non-standard tags
        pgn = PgnFormatterService._remove_non_standard_tags(pgn)
        moves_after_remove1 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_remove1, "Move count preserved after removing non-standard tags")
        
        # Step 2: Filter (hide comments)
        pgn = PgnFormatterService.filter_pgn_for_display(
            pgn,
            show_comments=False,
            show_metadata=True,
            show_variations=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=False
        )
        moves_after_filter = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_filter, "Move count preserved after filtering")
        
        # Step 3: Remove variations
        pgn = PgnFormatterService._remove_variations(pgn)
        final_moves = self._count_moves(pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved after chain "
            f"(original: {original_moves}, final: {final_moves})"
        )
        
        # Verify removals
        self.assertNotIn('[%evp', pgn)
        self.assertNotIn('[%eval', pgn)
        self.assertNotIn('{', pgn)
        self.assertNotIn('}', pgn)
        self.assertNotIn('(', pgn)
        self.assertNotIn(')', pgn)
    
    def test_filter_then_remove_chain(self):
        """Test: Filter, then remove, then filter again, then remove again."""
        pgn = self.TEST_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Original PGN should be parseable")
        
        # Step 1: Filter (hide non-standard tags)
        pgn = PgnFormatterService.filter_pgn_for_display(
            pgn,
            show_non_standard_tags=False,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=True,
            show_results=True
        )
        moves_after_filter1 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_filter1, "Move count preserved after first filter")
        
        # Step 2: Remove comments
        pgn = PgnFormatterService._remove_comments(pgn)
        moves_after_remove1 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_remove1, "Move count preserved after removing comments")
        
        # Step 3: Filter again (hide variations)
        pgn = PgnFormatterService.filter_pgn_for_display(
            pgn,
            show_variations=False,
            show_metadata=True,
            show_comments=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=False
        )
        moves_after_filter2 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_filter2, "Move count preserved after second filter")
        
        # Step 4: Remove variations
        pgn = PgnFormatterService._remove_variations(pgn)
        final_moves = self._count_moves(pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved after chain "
            f"(original: {original_moves}, final: {final_moves})"
        )
        
        # Verify removals
        self.assertNotIn('{', pgn)
        self.assertNotIn('}', pgn)
        self.assertNotIn('(', pgn)
        self.assertNotIn(')', pgn)
    
    def test_complex_combination(self):
        """Test: Complex combination of filter and remove operations."""
        pgn = self.TEST_PGN
        original_moves = self._count_moves(pgn)
        self.assertGreater(original_moves, 0, "Original PGN should be parseable")
        
        # Step 1: Filter - hide non-standard tags and results
        pgn = PgnFormatterService.filter_pgn_for_display(
            pgn,
            show_non_standard_tags=False,
            show_results=False,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=True
        )
        moves_after_filter1 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_filter1, "Move count preserved after first filter")
        
        # Step 2: Remove non-standard tags (should be no-op since already hidden)
        pgn = PgnFormatterService._remove_non_standard_tags(pgn)
        moves_after_remove1 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_remove1, "Move count preserved after removing non-standard tags")
        
        # Step 3: Filter - hide annotations
        pgn = PgnFormatterService.filter_pgn_for_display(
            pgn,
            show_annotations=False,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_results=True,
            show_non_standard_tags=False
        )
        moves_after_filter2 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_filter2, "Move count preserved after second filter")
        
        # Step 4: Remove comments
        pgn = PgnFormatterService._remove_comments(pgn)
        moves_after_remove2 = self._count_moves(pgn)
        self.assertEqual(original_moves, moves_after_remove2, "Move count preserved after removing comments")
        
        # Step 5: Remove variations
        pgn = PgnFormatterService._remove_variations(pgn)
        final_moves = self._count_moves(pgn)
        self.assertEqual(
            original_moves, final_moves,
            f"Move count should be preserved after complex combination "
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
        self.assertIsNone(re.search(r'[!?]{1,2}', pgn), "Annotations should be removed")
        self.assertIsNone(re.search(r'\$\d+', pgn), "NAGs should be removed")
        # Check for standalone results (not in metadata tags)
        # Results are removed from move notation, but may still be in [Result "1-0"] tag
        # So we check that there's no standalone result at the end of moves
        lines = pgn.split('\n')
        move_lines = [line for line in lines if not line.strip().startswith('[')]
        move_text = ' '.join(move_lines)
        self.assertIsNone(re.search(r'\b(1-0|0-1|1/2-1/2)\s*$', move_text), "Standalone results should be removed")


if __name__ == '__main__':
    unittest.main()

