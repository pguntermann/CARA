import html
import unittest

from app.services.notes_formatter_service import NotesFormatterService


LINK_STYLE = "color: rgb(100,150,255); text-decoration: underline; font-weight: bold;"
BOLD_STYLE = "font-weight: bold;"


def _format(plain: str, notation_to_ply: dict[str, int]) -> str:
    return NotesFormatterService.plain_to_html_with_move_links(
        plain=plain,
        notation_to_ply=notation_to_ply,
        link_style=LINK_STYLE,
        bold_style=BOLD_STYLE,
    )


def _assert_link(assertions: unittest.TestCase, formatted_html: str, display: str, href_lookup: str) -> None:
    expected = (
        f'<a href="move:{html.escape(href_lookup)}" style="{LINK_STYLE}">'
        f"{html.escape(display)}</a>"
    )
    assertions.assertIn(expected, formatted_html)


class TestNotesFormatterService(unittest.TestCase):
    def test_paired_moves_both_linked(self) -> None:
        plain = "1. e4 e5 is good"
        notation_to_ply = {"1. e4": 1, "1... e5": 2}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "1. e4", "1. e4")
        _assert_link(self, formatted, "e5", "1... e5")

    def test_paired_moves_black_not_in_map_is_bold(self) -> None:
        plain = "1. e4 e5 is good"
        notation_to_ply = {"1. e4": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "1. e4", "1. e4")
        self.assertIn(f'<span style="{BOLD_STYLE}">{html.escape("e5")}</span>', formatted)

    def test_explicit_black_move(self) -> None:
        plain = "13... Rb7 is interesting"
        notation_to_ply = {"13... Rb7": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "13... Rb7", "13... Rb7")

    def test_castling_short_with_check(self) -> None:
        plain = "4. O-O+ is safe"
        notation_to_ply = {"4. O-O+": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "4. O-O+", "4. O-O+")

    def test_castling_long_with_checkmate(self) -> None:
        plain = "4. O-O-O# was winning"
        notation_to_ply = {"4. O-O-O#": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "4. O-O-O#", "4. O-O-O#")

    def test_piece_capture(self) -> None:
        plain = "6. Bxc3 was strong"
        notation_to_ply = {"6. Bxc3": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "6. Bxc3", "6. Bxc3")

    def test_piece_disambiguation_file(self) -> None:
        plain = "7. Nbd2 is accurate"
        notation_to_ply = {"7. Nbd2": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "7. Nbd2", "7. Nbd2")

    def test_piece_disambiguation_rank(self) -> None:
        plain = "7. R1e1 is interesting"
        notation_to_ply = {"7. R1e1": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "7. R1e1", "7. R1e1")

    def test_pawn_promotion_with_check(self) -> None:
        plain = "8. d8=Q+ was decisive"
        notation_to_ply = {"8. d8=Q+": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "8. d8=Q+", "8. d8=Q+")

    def test_black_after_white_without_ellipsis(self) -> None:
        # Common shorthand: "8. h3 Bxc3" (black move directly after white move)
        plain = "8. h3 Bxc3 was a tactical shot"
        notation_to_ply = {"8. h3": 1, "8... Bxc3": 2}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "8. h3", "8. h3")
        _assert_link(self, formatted, "Bxc3", "8... Bxc3")

    def test_move_without_space_after_dot(self) -> None:
        plain = "13.b4 is a tactical shot"
        notation_to_ply = {"13.b4": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "13.b4", "13.b4")

    def test_suffix_delimiter_does_not_get_included(self) -> None:
        plain = "a nice move would have been 1. e3! it"
        notation_to_ply = {"1. e3": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "1. e3", "1. e3")
        # Ensure the exclamation is outside the highlighted token.
        self.assertIn("</a>!", formatted)
        self.assertNotIn("1. e3!</a>", formatted)

    def test_trailing_comma_is_not_included(self) -> None:
        plain = "Nach 4. f4, sah es gut aus"
        notation_to_ply = {"4. f4": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "4. f4", "4. f4")
        self.assertIn("</a>,", formatted)
        self.assertNotIn("4. f4,</a>", formatted)

    def test_no_false_positive_in_word_prefix(self) -> None:
        plain = "After h1. The key point is clear"
        formatted = _format(plain, notation_to_ply={})
        self.assertNotIn('<a href="move:', formatted)
        self.assertNotIn(f'<span style="{BOLD_STYLE}">', formatted)

    def test_no_false_positive_on_decimal(self) -> None:
        plain = "losing about 5.7 centipawns"
        formatted = _format(plain, notation_to_ply={})
        self.assertNotIn('<a href="move:', formatted)
        self.assertNotIn(f'<span style="{BOLD_STYLE}">', formatted)

    def test_multiple_occurrences_in_one_text(self) -> None:
        plain = "1. e4 e5 and later 1. e4"
        # Note: notation_to_ply keys are notation strings -> ply index.
        notation_to_ply = {"1. e4": 1, "1... e5": 2}
        formatted = _format(plain, notation_to_ply)

        escaped = html.escape("1. e4")
        anchor_e4 = (
            f'<a href="move:{escaped}" style="{LINK_STYLE}">'
            f"{escaped}</a>"
        )
        self.assertEqual(formatted.count(anchor_e4), 2)

        _assert_link(self, formatted, "e5", "1... e5")

    def test_tricky_punctuation_delimiters(self) -> None:
        # Semicolon/period/punctuation should delimit tokens without including them.
        plain = "1. e4 e5; 2. Nf3 Nc6"
        notation_to_ply = {"1. e4": 1, "1... e5": 2, "2. Nf3": 3, "2... Nc6": 4}
        formatted = _format(plain, notation_to_ply)

        _assert_link(self, formatted, "1. e4", "1. e4")
        _assert_link(self, formatted, "e5", "1... e5")
        _assert_link(self, formatted, "2. Nf3", "2. Nf3")
        _assert_link(self, formatted, "Nc6", "2... Nc6")

    def test_inline_markdown_italic_does_not_break_move_links(self) -> None:
        plain = "1. e4 *nice* move"
        notation_to_ply = {"1. e4": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "1. e4", "1. e4")
        self.assertIn('font-style:italic', formatted)
        self.assertIn("nice", formatted)

    def test_inline_markdown_inline_code_does_not_break_move_links(self) -> None:
        plain = "1. e4 `note` move"
        notation_to_ply = {"1. e4": 1}
        formatted = _format(plain, notation_to_ply)
        _assert_link(self, formatted, "1. e4", "1. e4")
        self.assertIn("<code>note</code>", formatted)

    def test_heading_is_rendered(self) -> None:
        plain = "## Heading Test"
        formatted = _format(plain, notation_to_ply={})
        self.assertIn('id="heading-test"', formatted)
        self.assertIn("Heading Test", formatted)
        # Heading renders as bold text in notes renderer (not necessarily a block tag).
        self.assertIn("font-weight:bold", formatted)

    def test_bold_across_line_breaks(self) -> None:
        plain = "**test**\nmore"
        formatted = _format(plain, notation_to_ply={})
        self.assertIn('font-weight:bold', formatted)
        self.assertIn("test", formatted)
        self.assertIn("more", formatted)

    def test_mixed_paired_and_explicit_black_in_one_paragraph(self) -> None:
        # Paired: "9. a4 a5," (black implied by immediate SAN)
        # Explicit: "9... Nf6" (black with ellipsis)
        plain = "8. h3 Bxc3 is tactical. 9. a4 a5, 9... Nf6 next."
        notation_to_ply = {
            "8. h3": 1,
            "8... Bxc3": 2,
            "9. a4": 3,
            "9... a5": 4,
            "9... Nf6": 5,
        }
        formatted = _format(plain, notation_to_ply)

        _assert_link(self, formatted, "8. h3", "8. h3")
        _assert_link(self, formatted, "Bxc3", "8... Bxc3")
        _assert_link(self, formatted, "9. a4", "9. a4")
        _assert_link(self, formatted, "a5", "9... a5")
        _assert_link(self, formatted, "9... Nf6", "9... Nf6")

    def test_get_notes_format_spans_supports_italic(self) -> None:
        plain = "1. e4 *nice* move"
        spans = NotesFormatterService.get_notes_format_spans(plain, {"1. e4": 1})

        # Move token should still be detected
        self.assertTrue(any(s.kind == "move_link" for s in spans))

        italic_spans = [s for s in spans if s.kind == "italic"]
        self.assertEqual(len(italic_spans), 1)
        italic = italic_spans[0]
        self.assertEqual(plain[italic.start:italic.end], "nice")

    def test_get_notes_format_spans_supports_bold_italic(self) -> None:
        plain = "***boldanditalic***"
        spans = NotesFormatterService.get_notes_format_spans(plain, {})
        bold_italic_spans = [s for s in spans if s.kind == "bold_italic"]
        self.assertEqual(len(bold_italic_spans), 1)
        span = bold_italic_spans[0]
        self.assertEqual(plain[span.start:span.end], "boldanditalic")

    def test_get_notes_format_spans_supports_inline_code(self) -> None:
        plain = "This is `note` in plain text."
        spans = NotesFormatterService.get_notes_format_spans(plain, {})
        code_spans = [s for s in spans if s.kind == "inline_code"]
        self.assertEqual(len(code_spans), 1)
        span = code_spans[0]
        self.assertEqual(plain[span.start:span.end], "note")

    def test_get_notes_format_spans_supports_strikethrough(self) -> None:
        plain = "This is ~~bad~~ in plain text."
        spans = NotesFormatterService.get_notes_format_spans(plain, {})
        strike_spans = [s for s in spans if s.kind == "strike"]
        self.assertEqual(len(strike_spans), 1)
        span = strike_spans[0]
        self.assertEqual(plain[span.start:span.end], "bad")

    def test_get_notes_format_spans_supports_blockquote(self) -> None:
        plain = "> quoted content"
        spans = NotesFormatterService.get_notes_format_spans(plain, {})
        quote_spans = [s for s in spans if s.kind == "blockquote"]
        self.assertEqual(len(quote_spans), 1)
        span = quote_spans[0]
        self.assertEqual(plain[span.start:span.end], "quoted content")

    def test_get_notes_format_spans_overlap_bold_italic_and_strike(self) -> None:
        plain = "***~~bad~~***"
        spans = NotesFormatterService.get_notes_format_spans(plain, {})

        strike_spans = [s for s in spans if s.kind == "strike"]
        self.assertEqual(len(strike_spans), 1)
        self.assertEqual(plain[strike_spans[0].start : strike_spans[0].end], "bad")

        hidden_tilde_spans = [s for s in spans if s.kind == "hidden" and plain[s.start:s.end] == "~~"]
        # We expect hidden spans for both opening and closing "~~".
        self.assertGreaterEqual(len(hidden_tilde_spans), 2)

    def test_apply_toolbar_action_strike_toggle(self) -> None:
        plain = "This is bad"
        start = plain.index("bad")
        end = start + len("bad")

        new_plain, ns, ne = NotesFormatterService.apply_toolbar_action(
            kind="strike",
            plain=plain,
            start=start,
            end=end,
        )
        self.assertEqual(new_plain, "This is ~~bad~~")
        self.assertEqual(new_plain[ns:ne], "bad")

        new_plain2, ns2, ne2 = NotesFormatterService.apply_toolbar_action(
            kind="strike",
            plain=new_plain,
            start=ns,
            end=ne,
        )
        self.assertEqual(new_plain2, plain)
        self.assertEqual(new_plain2[ns2:ne2], "bad")

    def test_apply_toolbar_action_strike_inside_bold_italic(self) -> None:
        plain = "***bad***"
        start = plain.index("bad")
        end = start + len("bad")

        new_plain, ns, ne = NotesFormatterService.apply_toolbar_action(
            kind="strike",
            plain=plain,
            start=start,
            end=end,
        )
        self.assertEqual(new_plain, "***~~bad~~***")
        self.assertEqual(new_plain[ns:ne], "bad")

        new_plain2, ns2, ne2 = NotesFormatterService.apply_toolbar_action(
            kind="strike",
            plain=new_plain,
            start=ns,
            end=ne,
        )
        self.assertEqual(new_plain2, plain)
        self.assertEqual(new_plain2[ns2:ne2], "bad")

    def test_apply_toolbar_action_heading_replaces_level(self) -> None:
        plain = "### Hello"
        start = plain.index("Hello")
        end = start + len("Hello")

        new_plain, ns, ne = NotesFormatterService.apply_toolbar_action(
            kind="h2",
            plain=plain,
            start=start,
            end=end,
        )
        self.assertEqual(new_plain, "## Hello")
        self.assertEqual(new_plain[ns:ne], "Hello")

    def test_apply_toolbar_action_blockquote_replaces_or_inserts(self) -> None:
        plain = "> Hello"
        start = plain.index("Hello")
        end = start + len("Hello")

        new_plain, ns, ne = NotesFormatterService.apply_toolbar_action(
            kind="blockquote",
            plain=plain,
            start=start,
            end=end,
        )
        # Re-applying should toggle off (remove the '> ' prefix).
        self.assertEqual(new_plain, "Hello")
        self.assertEqual(new_plain[ns:ne], "Hello")

        plain2 = "Hello"
        s2 = plain2.index("Hello")
        e2 = s2 + len("Hello")
        new_plain2, ns2, ne2 = NotesFormatterService.apply_toolbar_action(
            kind="blockquote",
            plain=plain2,
            start=s2,
            end=e2,
        )
        self.assertEqual(new_plain2, "> Hello")
        self.assertEqual(new_plain2[ns2:ne2], "Hello")

    def test_selection_intersects_heading_line(self) -> None:
        plain = "# Heading"
        start = plain.index("Heading")
        end = start + len("Heading")
        self.assertTrue(NotesFormatterService.selection_intersects_heading_line(plain, start, end))
        # Selection touching the '#' marker itself should also count as intersecting.
        self.assertTrue(NotesFormatterService.selection_intersects_heading_line(plain, 0, 1))


if __name__ == "__main__":
    unittest.main()

