"""Comprehensive unit tests for PGN filtering functionality.

This test suite validates all combinations of showing/hiding PGN elements
(metadata, comments, variations, annotations, results, non-standard tags)
to ensure the filtering logic is reliable and doesn't modify metadata tags.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import re
import unittest
from app.services.pgn_formatter_service import PgnFormatterService


class TestPgnFiltering(unittest.TestCase):
    """Comprehensive test suite for PGN filtering."""

    # Comprehensive PGN with all elements including the bug case
    TEST_PGN = """[Event "Career"] [Site "null"] [Date "2025.10.25"] [Round "1"] [White "Stockfish 1100"] [Black "Test Player"] [Result "0-1"] [Annotator "Taktische Analyse 7.0"] [ECO "B22"] [WhiteElo "1100"] [BlackElo "1100"] [WhiteFideId "-1"] [PlyCount "182"] [Beauty "4813202940955"] [GameId "2236926816628761"] [EventDate "2025.??.??"] [MyCustomTag "Hi"] { [%evp 9,181,-95,-86] } 1. e4! c5? 2. c3 Nf6 3. Qc2 e5 { This is a comment } 4. d3 Nc6 (4... d5 { Variation comment } 5. h3 d5) 5. h3 d5 6. Nf3 { [#] B22: Sizilianisch (c3). } 6... d4 ({ VorgÃ¤nger: }6... h6 7. Be2 Be7 8. Nbd2 9. Nf1 c4 10. dxc4 dxe4 11. N3d2 Bf5 12. Ne3 Bh7 { 0-1 Emodi,G (2214)-Orgovan,S (2174) HUN-chT2 Maroczy 1314 Hungary 2013 (10) }) 7. Bg5 { [%eval -106,29] [%wdl 1,444,555] } (7. Nbd2 { [%eval -63,29] [%wdl 3,786,211] }) 7... h6 8. Bh4 { Schwarz steht besser. } 8... g5! { [%eval -89,26] [%wdl 1,595,404] } (8... Be6 { [%eval -135,21] [%wdl 0,222,778] }9. Be2 Bd6 ) 9. cxd4 { [%eval -386,23] [%wdl 0,0,1000][%mdl 8192] [#] } (9. Bg3 { [%eval -89,26] [%wdl 1,595,404] ist der einzige Weg fÃ¼r Weiss.. }) 9... Nxd4 { [%eval -94,24] [%wdl 1,557,442] } (9... gxh4 { [%eval -386,23] [%wdl 0,0,1000] }10. d5 Nd4 11. Nxd4 cxd4 ) 10. Qc3 { [%eval -539,22] [%wdl 0,0,1000][%mdl 8192] } (10. Nxd4 { [%eval -94,24] [%wdl 1,557,442] war die entscheidende Verteidigung. }10... Qxd4 10... gxh4 11. Nf3 10... cxd4 11. Bg3 11. Bg3 ) 10... Nxf3+ 11. Ke2 { [%eval -778,22] [%wdl 0,0,1000] } (11. gxf3 { [%eval -475,26] [%wdl 0,0,1000] }11... gxh4 12. Be2 ) 11... Nxh4 12. Qa3 c4 13. Qc3 Qd4 14. Ke1 Qxc3+ 15. Nxc3 Ng6 16. dxc4 Be6 17. Rc1 Bxc4 18. Bxc4 b6 19. Ke2 O-O-O 20. Rhd1 Bd6 21. b3 Nf4+ 22. Ke1 Nxg2+ 23. Kd2 Bb4+ 24. Bd5 Bxc3+ 25. Rxc3+ Kd7 26. b4 Nxd5 27. exd5 Nf4 28. Ke1 Ke7 29. Rc7+ Rd7 30. Rd2 Rxc7 31. d6+ Kd7 { [#] (c1+) } 32. dxc7+ Kxc7 { [%mdl 4096] Endspiel KTS-KT } 33. Rd1 Rd8 { (xd1+) } 34. a3 Rxd1+ { Schwarz setzt Matt. } 35. Kxd1 Nxh3 36. Kd2 Nxf2 { KS-KBB } 37. Kc3 Ne4+ 38. Kc2 a5 39. bxa5 bxa5 { KS-KB } 40. Kc1 h5 41. a4 Nc3 42. Kb2 Nxa4+ 43. Kb3 Nc5+ 44. Kc2 Kd6 45. Kb2 Kd5 46. Kc2 Kd4 47. Kb1 Kc3 48. Ka1 Kb3 49. Kb1 Nd3 50. Ka1 Nf2 51. Kb1 Nd1 52. Kc1 Ne3 53. Kb1 h4 54. Kc1 h3 55. Kb1 h2 { [%cal Rh2h1] } 56. Ka1 h1=N 57. Kb1 Nf2 58. Kc1 Nd3+ 59. Kb1 Nd1 60. Ka1 Nb4 61. Kb1 Nc3+ 62. Kc1 Nba2+ 63. Kd2 Nb1+ 64. Kd3 Nb4+ 65. Ke4 Nc6 66. Kd3 g4 67. Ke3 a4 68. Kf2 a3 69. Kg1 a2 70. Kf2 a1=B 71. Kg3 e4 72. Kf4 g3 73. Kxe4 g2 74. Kf5 g1=B 75. Kg4 Ne5+ 76. Kg3 Nd2 77. Kf4 Bh2+ 78. Ke3 Kc3 79. Ke2 Bf4 80. Kf2 Nd3+ 81. Ke2 Bb2 82. Kd1 Nf2+ 83. Ke1 Bg3 84. Ke2 Bc1 85. Ke3 Nf1+ 86. Kf3 Kd4 87. Ke2 f6 88. Ke1 Ne3 89. Ke2 Ke4 90. Ke1 Nd3+ 91. Ke2 Nf4# { Schwarz nahm nach der ErÃ¶ffnung die ZÃ¼gel in die Hand. Gewichteter Fehlerwert: WeiÃŸ=0.99/Schwarz=0.66 Verlustzug: WeiÃŸ=2 --- Gewinn verpasst: --- Schwarz=1 Fehler: WeiÃŸ=2 Schwarz=1 Ungenau: --- Schwarz=1 OK: --- Schwarz=3 } 0-1"""

    def _assert_metadata_preserved(self, filtered_text: str, original_text: str, message: str = ""):
        """Assert that metadata tags are preserved exactly."""
        metadata_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
        original_metadata = {}
        for match in metadata_pattern.finditer(original_text):
            key, value = match.group(1), match.group(2)
            original_metadata[key] = value
        filtered_metadata = {}
        for match in metadata_pattern.finditer(filtered_text):
            key, value = match.group(1), match.group(2)
            filtered_metadata[key] = value
        for key, original_value in original_metadata.items():
            self.assertIn(key, filtered_metadata, f"{message}: Metadata tag [{key} \"...\"] missing in filtered text")
            self.assertEqual(
                filtered_metadata[key], original_value,
                f"{message}: Metadata tag [{key}] was modified"
            )

    def test_all_shown(self):
        """Test with all elements shown."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "All shown: EventDate metadata")
        self.assertIn('{ [%evp', filtered, "All shown: Comments with non-standard tags")
        self.assertIn('e4!', filtered, "All shown: Annotations")
        self.assertIn('c5?', filtered, "All shown: Annotations")
        self.assertIn('(4... d5', filtered, "All shown: Variations")
        self.assertIn('0-1', filtered, "All shown: Results")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "All shown")

    def test_all_hidden(self):
        """Test with all elements hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=False,
            show_comments=False,
            show_variations=False,
            show_annotations=False,
            show_results=False,
            show_non_standard_tags=False
        )
        lines = filtered.split('\n')
        metadata_only_lines = [line for line in lines if line.strip().startswith('[') and line.strip().endswith(']')]
        self.assertEqual(len(metadata_only_lines), 0, "All hidden: No metadata-only lines")
        self.assertNotIn('{', filtered, "All hidden: No comments")
        metadata_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
        move_notation = metadata_pattern.sub('', filtered)
        self.assertNotIn('!', move_notation, "All hidden: No annotations in moves")
        self.assertNotIn('e4!', move_notation, "All hidden: No annotations in moves")
        self.assertNotIn('c5?', move_notation, "All hidden: No annotations in moves")
        self.assertNotIn('(', filtered, "All hidden: No variations")
        result_in_moves = re.search(r'\b(1-0|0-1|1/2-1/2|\*)\b', move_notation)
        self.assertIsNone(result_in_moves, "All hidden: No results in move notation")
        self.assertIn('1. e4', filtered, "All hidden: Moves preserved")

    def test_metadata_hidden(self):
        """Test with metadata hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=False,
            show_comments=True,
            show_variations=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=True
        )
        lines = filtered.split('\n')
        metadata_only_lines = [line for line in lines if line.strip().startswith('[') and line.strip().endswith(']')]
        self.assertEqual(len(metadata_only_lines), 0, "Metadata hidden: No metadata-only lines")
        self.assertIn('{ [%evp', filtered, "Metadata hidden: Comments preserved")
        self.assertIn('e4!', filtered, "Metadata hidden: Annotations preserved")

    def test_comments_hidden(self):
        """Test with comments hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=False,
            show_variations=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Comments hidden: Metadata preserved")
        self.assertNotIn('{ [%evp', filtered, "Comments hidden: No comments")
        self.assertIn('e4!', filtered, "Comments hidden: Annotations preserved")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Comments hidden")

    def test_variations_hidden(self):
        """Test with variations hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=True,
            show_variations=False,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Variations hidden: Metadata preserved")
        self.assertNotIn('(4... d5', filtered, "Variations hidden: No variations")
        self.assertIn('{ [%evp', filtered, "Variations hidden: Comments preserved")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Variations hidden")

    def test_annotations_hidden(self):
        """Test with annotations hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=False,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Annotations hidden: Metadata preserved")
        self.assertNotIn('e4!', filtered, "Annotations hidden: No annotations in moves")
        self.assertNotIn('c5?', filtered, "Annotations hidden: No annotations in moves")
        self.assertIn('1. e4 c5', filtered, "Annotations hidden: Moves preserved")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Annotations hidden")

    def test_results_hidden(self):
        """Test with results hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=True,
            show_results=False,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Results hidden: Metadata preserved")
        metadata_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
        move_notation = filtered
        for match in list(metadata_pattern.finditer(move_notation))[::-1]:
            move_notation = move_notation[:match.start()] + move_notation[match.end():]
        result_in_moves = re.search(r'\b(1-0|0-1|1/2-1/2|\*)\b', move_notation)
        self.assertIsNone(result_in_moves, "Results hidden: No results in move notation")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Results hidden")

    def test_non_standard_tags_hidden(self):
        """Test with non-standard tags hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=False
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Non-standard tags hidden: Metadata preserved")
        self.assertNotIn('[%evp', filtered, "Non-standard tags hidden: No [%evp]")
        self.assertNotIn('[%eval', filtered, "Non-standard tags hidden: No [%eval]")
        self.assertNotIn('[%wdl', filtered, "Non-standard tags hidden: No [%wdl]")
        self.assertNotIn('[%mdl', filtered, "Non-standard tags hidden: No [%mdl]")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Non-standard tags hidden")

    def test_comments_and_annotations_hidden(self):
        """Test with comments and annotations hidden (critical bug case)."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=False,
            show_variations=True,
            show_annotations=False,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Comments+Annotations hidden: EventDate with ?? preserved")
        self.assertNotIn('{', filtered, "Comments+Annotations hidden: No comments")
        self.assertNotIn('e4!', filtered, "Comments+Annotations hidden: No annotations")
        self.assertNotIn('c5?', filtered, "Comments+Annotations hidden: No annotations")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Comments+Annotations hidden")

    def test_metadata_shown_annotations_hidden(self):
        """Test with metadata shown but annotations hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=True,
            show_variations=True,
            show_annotations=False,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Metadata shown, annotations hidden: EventDate preserved")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Metadata shown, annotations hidden")

    def test_metadata_shown_comments_hidden(self):
        """Test with metadata shown but comments hidden."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=False,
            show_variations=True,
            show_annotations=True,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Metadata shown, comments hidden: EventDate preserved")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Metadata shown, comments hidden")

    def test_metadata_shown_comments_and_annotations_hidden(self):
        """Test with metadata shown but comments and annotations hidden (main bug case)."""
        filtered = PgnFormatterService.filter_pgn_for_display(
            self.TEST_PGN,
            show_metadata=True,
            show_comments=False,
            show_variations=True,
            show_annotations=False,
            show_results=True,
            show_non_standard_tags=True
        )
        self.assertIn('[EventDate "2025.??.??"]', filtered, "Metadata shown, comments+annotations hidden: EventDate with ?? preserved")
        self._assert_metadata_preserved(filtered, self.TEST_PGN, "Metadata shown, comments+annotations hidden")

    def test_systematic_combinations(self):
        """Test systematic combinations of flags."""
        test_cases = [
            (True, False, True, False, True, False, "Alternating pattern"),
            (False, True, False, True, False, True, "Alternating pattern (inverted)"),
            (True, True, True, False, False, False, "First half True"),
            (False, False, False, True, True, True, "Second half True"),
            (True, False, False, False, False, False, "Only metadata"),
            (False, True, False, False, False, False, "Only comments"),
            (False, False, True, False, False, False, "Only variations"),
            (False, False, False, True, False, False, "Only annotations"),
            (False, False, False, False, True, False, "Only results"),
            (False, False, False, False, False, True, "Only non-standard tags"),
            (False, True, True, True, True, True, "All but metadata"),
            (True, False, True, True, True, True, "All but comments"),
            (True, True, False, True, True, True, "All but variations"),
            (True, True, True, False, True, True, "All but annotations"),
            (True, True, True, True, False, True, "All but results"),
            (True, True, True, True, True, False, "All but non-standard tags"),
        ]
        for show_metadata, show_comments, show_variations, show_annotations, show_results, show_non_standard_tags, description in test_cases:
            with self.subTest(description=description):
                filtered = PgnFormatterService.filter_pgn_for_display(
                    self.TEST_PGN,
                    show_metadata=show_metadata,
                    show_comments=show_comments,
                    show_variations=show_variations,
                    show_annotations=show_annotations,
                    show_results=show_results,
                    show_non_standard_tags=show_non_standard_tags
                )
                if show_metadata:
                    self._assert_metadata_preserved(filtered, self.TEST_PGN, f"Systematic: {description}")
                if not show_comments:
                    self.assertNotIn('{ [%evp', filtered, f"Systematic: {description} - Comments hidden")
                if not show_annotations:
                    if show_metadata:
                        self.assertIn('[EventDate "2025.??.??"]', filtered, f"Systematic: {description} - EventDate preserved")
                    self.assertNotIn('e4!', filtered, f"Systematic: {description} - Annotations removed from moves")
                if not show_variations:
                    self.assertNotIn('(4... d5', filtered, f"Systematic: {description} - Variations hidden")
                if not show_results:
                    metadata_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
                    move_notation = filtered
                    for match in list(metadata_pattern.finditer(move_notation))[::-1]:
                        move_notation = move_notation[:match.start()] + move_notation[match.end():]
                    result_in_moves = re.search(r'\b(1-0|0-1|1/2-1/2|\*)\b', move_notation)
                    self.assertIsNone(result_in_moves, f"Systematic: {description} - Results hidden from moves")


if __name__ == "__main__":
    unittest.main()
