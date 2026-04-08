"""Unit tests for PgnService (PGN normalization and export helpers)."""

import unittest

from app.services.pgn_service import PgnService


class TestPgnServiceNormalizeMovesFixedWidth(unittest.TestCase):
    """Tests for _normalize_moves_with_fixed_width (save / export line wrapping)."""

    def test_preserves_space_before_move_number_after_wrap(self) -> None:
        """Regression: early line break must not drop the space before N. (e.g. Ne7 9.)."""
        moves = (
            "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 "
            "7. O-O Nc6 8. d5 Ne7 9. b4 {Fischer out of book} a5 10. b5"
        )
        out = PgnService._normalize_moves_with_fixed_width(moves, 80)
        self.assertNotIn("Ne79.", out)
        collapsed = out.replace("\n", " ")
        self.assertIn("Ne7 9. b4", collapsed)

    def test_preserves_space_before_single_digit_move_number_narrow_width(self) -> None:
        """Same bug class at a smaller width: separator before 5. must remain."""
        moves = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O"
        out = PgnService._normalize_moves_with_fixed_width(moves, 40)
        self.assertNotRegex(out, r"Nf65\.")
        self.assertRegex(out.replace("\n", " "), r"Nf6 5\.\s+O-O")

    def test_short_movetext_single_line_unchanged(self) -> None:
        moves = "1. e4 e5 2. Nf3 Nc6 *"
        out = PgnService._normalize_moves_with_fixed_width(moves, 80)
        self.assertEqual(out, moves)

    def test_collapses_existing_newlines_then_wraps(self) -> None:
        moves = "1. e4 e5\n2. Nf3 Nc6\n3. Bb5 a6"
        out = PgnService._normalize_moves_with_fixed_width(moves, 20)
        self.assertNotIn("\n\n", out)
        collapsed = out.replace("\n", " ")
        self.assertRegex(collapsed, r"1\.\s+e4\s+e5\s+2\.\s+Nf3")

    def test_each_output_line_respects_fixed_width(self) -> None:
        moves = (
            "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 "
            "7. O-O Nc6 8. d5 Ne7 9. b4 {x} a5 10. b5"
        )
        width = 80
        out = PgnService._normalize_moves_with_fixed_width(moves, width)
        for line in out.splitlines():
            self.assertLessEqual(len(line), width, msg=f"line too long: {line!r}")


class TestPgnServiceNormalizePgnLineBreaks(unittest.TestCase):
    """Tests for _normalize_pgn_line_breaks (headers + moves section)."""

    def test_fixed_width_false_flattens_moves_to_one_line(self) -> None:
        pgn = '[Event "x"]\n\n1. e4\ne5\n2. Nf3 *\n'
        out = PgnService._normalize_pgn_line_breaks(pgn, use_fixed_width=False, fixed_width=80)
        self.assertIn("\n\n", out)
        head, moves = out.split("\n\n", 1)
        self.assertIn('[Event "x"]', head)
        self.assertNotIn("\n", moves.strip())

    def test_fixed_width_true_preserves_move_number_spacing_in_moves(self) -> None:
        pgn = (
            '[Event "T"]\n\n'
            "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 "
            "7. O-O Nc6 8. d5 Ne7 9. b4 {c} a5 10. b5 *\n"
        )
        out = PgnService._normalize_pgn_line_breaks(pgn, use_fixed_width=True, fixed_width=80)
        self.assertNotIn("Ne79.", out)
        moves = out.split("\n\n", 1)[1]
        self.assertIn("Ne7 9. b4", moves.replace("\n", " "))

    def test_returns_unchanged_when_no_moves_section_separator(self) -> None:
        single = '[Event "only headers"]\n[Site "?"]\n'
        out = PgnService._normalize_pgn_line_breaks(
            single, use_fixed_width=True, fixed_width=80
        )
        self.assertEqual(out, single)


if __name__ == "__main__":
    unittest.main()
