"""Tests for ChessLogHTMLService and module-level helpers.

No Qt required — all generators are pure Python.
"""

from __future__ import annotations

import unittest

from app.models.chess_log_snapshot import TagRowSnapshot
from app.services.chess_log_html_service import (
    ChessLogHTMLService,
    _gfm_table_to_html,
    _narrative_body_html,
    _split_narrative_blocks,
    _encode_text,
)
from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
from app.utils.markdown_to_html import markdown_to_html


_CONFIG = {}


def _svc(config=None):
    return ChessLogHTMLService(config or _CONFIG)


def _clamp_snap(move_label="1. e4", cats=("C",), why="a note", is_shallow=False):
    entries = [{"preset": "CLAMP", "cat": c, "why": (why if c == cats[0] else "")} for c in cats]
    return TagRowSnapshot(
        move_label=move_label,
        preset="CLAMP",
        entries=entries,
        fen=None,
        played_move=None,
        show_ignore=False,
        is_shallow=is_shallow,
    )


def _3x3_snap(move_label="3. Bb5", answers=None, shallow_cats=frozenset(), vague_cats=frozenset()):
    if answers is None:
        answers = {"Why1": "ans1", "Why2": "ans2", "Why3": "ans3", "Why4": "lesson"}
    entries = [{"preset": "3x3", "cat": k, "why": v} for k, v in answers.items()]
    return TagRowSnapshot(
        move_label=move_label,
        preset="3x3",
        entries=entries,
        fen=None,
        played_move=None,
        show_ignore=False,
        shallow_cats=shallow_cats,
        vague_cats=vague_cats,
    )


def _groups(snaps, header="White - Black * (2026.01.01 - 40 moves)"):
    return [{"header": header, "rows": list(snaps)}]


# ---------------------------------------------------------------------------
# 1–4: HTML escaping
# ---------------------------------------------------------------------------

class TestEscaping(unittest.TestCase):
    def test_lt_gt_amp_escaped_in_clamp_note(self):
        snap = _clamp_snap(why="<b>A & B</b>")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("&lt;b&gt;A &amp; B&lt;/b&gt;", h)

    def test_lt_gt_amp_escaped_in_move_label(self):
        snap = _clamp_snap(move_label="1. <e4>")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("&lt;e4&gt;", h)

    def test_lt_gt_amp_escaped_in_3x3_answer(self):
        snap = _3x3_snap(answers={"Why1": "A < B & C > D", "Why2": "", "Why3": "", "Why4": ""})
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("A &lt; B &amp; C &gt; D", h)

    def test_lt_gt_amp_escaped_in_game_header(self):
        groups = [{"header": "A & B < C > D 1-0 (2026 - 30 moves)", "rows": [_clamp_snap()]}]
        h = _svc().logged_moments_html(groups)
        self.assertIn("A &amp; B &lt; C &gt; D", h)

    def test_plain_text_flavor_has_no_html_tags_when_no_special_chars(self):
        snap = _clamp_snap(why="a plain note")
        plain = _svc().logged_moments_plain(_groups([snap]))
        self.assertNotIn("<", plain)
        self.assertNotIn(">", plain)

    def test_special_chars_escaped_in_html_literal_in_plain(self):
        snap = _clamp_snap(why="<b>bold</b> & rest")
        html_out = _svc().logged_moments_html(_groups([snap]))
        plain_out = _svc().logged_moments_plain(_groups([snap]))
        self.assertIn("&lt;", html_out)
        self.assertIn("<b>bold</b> & rest", plain_out)

# ---------------------------------------------------------------------------
# 5–6: Figurines and dashes
# ---------------------------------------------------------------------------

class TestFigurinesAndDashes(unittest.TestCase):
    def test_figurines_pass_through_in_note(self):
        snap = _clamp_snap(why="Knight ♘ on f3")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("♘", h)

    def test_en_dash_passes_through(self):
        snap = _clamp_snap(why="moves 10–20")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("–", h)

    def test_em_dash_passes_through(self):
        snap = _clamp_snap(why="idea — but")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("—", h)

# ---------------------------------------------------------------------------
# 7: Blank 3x3 answers
# ---------------------------------------------------------------------------

class TestBlank3x3Answers(unittest.TestCase):
    def test_blank_why2_shows_question_no_answer_paragraph(self):
        snap = _3x3_snap(answers={"Why1": "ans", "Why2": "", "Why3": "ans3", "Why4": "lesson"})
        h = _svc().logged_moments_html(_groups([snap]))
        q2 = THREE_BY_THREE_PROMPTS["Why2"]
        q3 = THREE_BY_THREE_PROMPTS["Why3"]
        self.assertIn(q2, h)
        # Nothing between q2's paragraph and q3's paragraph
        idx_q2 = h.index(q2)
        idx_q3 = h.index(q3)
        between = h[idx_q2:idx_q3]
        self.assertNotIn("ans2", between)

    def test_four_why_question_paragraphs_present(self):
        snap = _3x3_snap(answers={"Why1": "", "Why2": "", "Why3": "", "Why4": ""})
        h = _svc().logged_moments_html(_groups([snap]))
        for key in ("Why1", "Why2", "Why3", "Why4"):
            self.assertIn(THREE_BY_THREE_PROMPTS[key], h)

# ---------------------------------------------------------------------------
# 8: Chips — 3x3 shallow and vague
# ---------------------------------------------------------------------------

class TestChips3x3(unittest.TestCase):
    def test_shallow_chip_on_why2(self):
        snap = _3x3_snap(shallow_cats=frozenset({"Why2"}))
        h = _svc().logged_moments_html(_groups([snap]))
        # Chip should appear; check for the color
        self.assertIn("#9a4400", h)

    def test_vague_chip_on_why4(self):
        snap = _3x3_snap(vague_cats=frozenset({"Why4"}))
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("#1d4ed8", h)

    def test_shallow_chip_only_on_flagged_why(self):
        snap = _3x3_snap(shallow_cats=frozenset({"Why1"}))
        h = _svc().logged_moments_html(_groups([snap]))
        q1 = THREE_BY_THREE_PROMPTS["Why1"]
        q2 = THREE_BY_THREE_PROMPTS["Why2"]
        idx1 = h.index(q1)
        idx2 = h.index(q2)
        # Shallow color appears between q1 and q2
        self.assertIn("#9a4400", h[idx1:idx2])
        # No shallow color after q2 (assuming only Why1 flagged)
        self.assertNotIn("#9a4400", h[idx2:])

    def test_no_chip_when_not_flagged(self):
        snap = _3x3_snap()
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertNotIn("#9a4400", h)
        self.assertNotIn("#1d4ed8", h)

# ---------------------------------------------------------------------------
# 9: Chips — CLAMP/CCT
# ---------------------------------------------------------------------------

class TestChipsCLAMPCCT(unittest.TestCase):
    def test_shallow_chip_on_clamp_row(self):
        snap = _clamp_snap(is_shallow=True)
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("#9a4400", h)

    def test_no_chip_when_not_shallow(self):
        snap = _clamp_snap(is_shallow=False)
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertNotIn("#9a4400", h)
        self.assertNotIn("#1d4ed8", h)

    def test_chip_label_from_config(self):
        config = {"ui": {"dialogs": {"shallow": {"labels": {
            "shallow": {"text": "MyShallow"},
            "vague_lesson": {"text": "MyVague"},
        }}}}}
        snap = _clamp_snap(is_shallow=True)
        h = ChessLogHTMLService(config).logged_moments_html(_groups([snap]))
        self.assertIn("MyShallow", h)

# ---------------------------------------------------------------------------
# 10: Multiple categories CLAMP
# ---------------------------------------------------------------------------

class TestMultipleCategories(unittest.TestCase):
    def test_two_clamp_cats_space_separated(self):
        snap = _clamp_snap(cats=("C", "L"), why="note")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("C L", h)

    def test_cct_full_names(self):
        entries = [
            {"preset": "CCT", "cat": "Checks", "why": "note"},
            {"preset": "CCT", "cat": "Threats", "why": ""},
        ]
        snap = TagRowSnapshot(
            move_label="5. Nf3",
            preset="CCT",
            entries=entries,
            fen=None,
            played_move=None,
            show_ignore=False,
        )
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("Checks", h)
        self.assertIn("Threats", h)

# ---------------------------------------------------------------------------
# 11: Game header and <hr> placement
# ---------------------------------------------------------------------------

class TestGameHeaderAndHr(unittest.TestCase):
    def test_game_header_in_h3(self):
        header = "Alice - Bob 1-0 (2026.01.01 - 30 moves)"
        groups = [{"header": header, "rows": [_clamp_snap()]}]
        h = _svc().logged_moments_html(groups)
        self.assertIn(f"<h3>{header}</h3>", h)

    def test_no_hr_at_start(self):
        # logged_moments_html puts a report-header <hr> before any game group;
        # no additional <hr> should precede the first game's <h3>
        groups = _groups([_clamp_snap()])
        h = _svc().logged_moments_html(groups)
        # Only the report-header <hr> exists (one game → no inter-game <hr>)
        self.assertEqual(h.count("<hr>"), 1)

    def test_no_hr_at_end(self):
        groups = _groups([_clamp_snap()])
        h = _svc().logged_moments_html(groups)
        self.assertFalse(h.rstrip().endswith("<hr>"))

    def test_hr_between_two_games(self):
        g1 = {"header": "G1 header", "rows": [_clamp_snap("1. e4")]}
        g2 = {"header": "G2 header", "rows": [_clamp_snap("2. d4")]}
        h = _svc().logged_moments_html([g1, g2])
        # The inter-game <hr> must appear between the two game headers
        idx_g1 = h.index("G1 header")
        idx_g2 = h.index("G2 header")
        between = h[idx_g1:idx_g2]
        self.assertIn("<hr>", between)

    def test_no_hr_between_moments_same_game(self):
        # Multiple moments in one game: no <hr> after the first <h3>
        snaps = [_clamp_snap("1. e4"), _clamp_snap("3. Bb5")]
        h = _svc().logged_moments_html(_groups(snaps))
        idx_h3 = h.index("<h3>")
        self.assertNotIn("<hr>", h[idx_h3:])

# ---------------------------------------------------------------------------
# 12: CLAMP no-note row
# ---------------------------------------------------------------------------

class TestNoNote(unittest.TestCase):
    def test_empty_note_no_paragraph(self):
        snap = _clamp_snap(why="")
        h = _svc().logged_moments_html(_groups([snap]))
        # Move line present, no second <p> with content after it
        self.assertIn("<strong>1. e4</strong>", h)
        # No <p></p> or <p> with just whitespace after the move
        import re
        paras = re.findall(r"<p>(.*?)</p>", h)
        # The only para should contain the move line itself
        empty = [p for p in paras if not p.strip()]
        self.assertEqual(empty, [])

# ---------------------------------------------------------------------------
# 13: 3x3 question labels
# ---------------------------------------------------------------------------

class TestQuestionLabels(unittest.TestCase):
    def test_all_four_question_texts_present(self):
        snap = _3x3_snap()
        h = _svc().logged_moments_html(_groups([snap]))
        for key in ("Why1", "Why2", "Why3", "Why4"):
            # html.escape with quote=False: apostrophe is preserved as-is
            self.assertIn(THREE_BY_THREE_PROMPTS[key], h)

    def test_questions_in_strong_tags(self):
        snap = _3x3_snap(answers={"Why1": "", "Why2": "", "Why3": "", "Why4": ""})
        h = _svc().logged_moments_html(_groups([snap]))
        q1 = THREE_BY_THREE_PROMPTS["Why1"]
        self.assertIn(f"<strong>{q1}</strong>", h)

# ---------------------------------------------------------------------------
# 14: Narrative HTML — pipe table
# ---------------------------------------------------------------------------

class TestNarrativeTable(unittest.TestCase):
    _NARRATIVE = (
        "## Patterns & Recurrent Themes\n\n"
        "- **Theme A.** Text about theme.\n\n"
        "## Tactical Breakdown\n\n"
        "| Skill | Observed Issue | Strategic Impact |\n"
        "| --- | --- | --- |\n"
        "| Piece Coordination | Knights unprotected | Material loss |\n\n"
        "## Key Takeaways\n\n"
        "**Act now.** Do this thing.\n"
    )

    def test_table_converted_to_html_table(self):
        h = _narrative_body_html(self._NARRATIVE)
        self.assertIn("<table>", h)
        self.assertIn("<th", h)
        self.assertIn("<td>", h)

    def test_headers_become_h3_due_to_offset(self):
        h = _narrative_body_html(self._NARRATIVE)
        self.assertIn("<h3", h)
        self.assertNotIn("<h2", h)

    def test_bullet_list_present(self):
        h = _narrative_body_html(self._NARRATIVE)
        self.assertIn("<ul>", h)
        self.assertIn("<li>", h)

    def test_narrative_order_preserved(self):
        h = _narrative_body_html(self._NARRATIVE)
        idx_ul = h.index("<ul>")
        idx_table = h.index("<table>")
        idx_takeaways = h.rindex("<h3")
        self.assertLess(idx_ul, idx_table)
        self.assertLess(idx_table, idx_takeaways)


# ---------------------------------------------------------------------------
# 15: Newlines in notes
# ---------------------------------------------------------------------------

class TestNewlinesInNotes(unittest.TestCase):
    def test_newline_in_clamp_note_becomes_br(self):
        snap = _clamp_snap(why="line one\nline two")
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("<br>", h)
        self.assertIn("line one", h)
        self.assertIn("line two", h)

    def test_newline_in_3x3_answer_becomes_br(self):
        snap = _3x3_snap(answers={"Why1": "line1\nline2", "Why2": "", "Why3": "", "Why4": ""})
        h = _svc().logged_moments_html(_groups([snap]))
        self.assertIn("<br>", h)

# ---------------------------------------------------------------------------
# 16: Narrative header lines match PDF
# ---------------------------------------------------------------------------

class TestNarrativeHeaderLines(unittest.TestCase):
    def test_narrative_html_header_player_source_counts(self):
        h = _svc().narrative_html(
            "Paul", "62-game CLAMP", "## Heading\n\nBody.",
            n_games=62, g_games=47, m_moments=120, k_unflagged=115,
            generated_at="2026-10-31 14:22",
            model_label="claude-sonnet-4-6",
        )
        self.assertIn("Chess Log — Narrative Summary", h)
        self.assertIn("Player: Paul", h)
        self.assertIn("Source: 62-game CLAMP", h)
        self.assertIn("62 games", h)
        self.assertIn("47 with logged moments", h)
        self.assertIn("120 moments", h)
        self.assertIn("115 not flagged", h)
        self.assertIn("Generated: 2026-10-31 14:22", h)
        self.assertIn("AI model: claude-sonnet-4-6", h)

    def test_check_logs_html_header_source_model_generated(self):
        h = _svc().check_logs_html(
            _groups([_clamp_snap()]),
            source_label="my-library",
            model_label="claude-haiku-4-5",
            generated_at="2026-10-31 10:00",
        )
        self.assertIn("Chess Log — Check Logs", h)
        self.assertIn("Source: my-library", h)
        self.assertIn("AI model: claude-haiku-4-5", h)
        self.assertIn("Generated: 2026-10-31 10:00", h)

    def test_logged_moments_html_title(self):
        h = _svc().logged_moments_html(_groups([_clamp_snap()]))
        self.assertIn("Chess Log — Logged Moments", h)


# ---------------------------------------------------------------------------
# 17 + 18-new: plain-text content
# ---------------------------------------------------------------------------

class TestPlainText(unittest.TestCase):
    def test_plain_text_has_no_html_tags(self):
        snap = _clamp_snap(why="a plain note")
        plain = _svc().logged_moments_plain(_groups([snap]))
        self.assertNotIn("<", plain)
        self.assertNotIn(">", plain)

    def test_html_has_escaped_special_chars_plain_has_literal(self):
        snap = _clamp_snap(why="<bad> & stuff")
        html_out = _svc().logged_moments_html(_groups([snap]))
        plain_out = _svc().logged_moments_plain(_groups([snap]))
        self.assertIn("&lt;", html_out)
        self.assertIn("<bad> & stuff", plain_out)

    def test_check_logs_plain_header_lines(self):
        plain = _svc().check_logs_plain(
            _groups([_clamp_snap()]),
            source_label="src", model_label="m", generated_at="2026-01-01 10:00",
        )
        self.assertIn("Chess Log — Check Logs", plain)
        self.assertIn("Source: src", plain)
        self.assertIn("AI model: m", plain)

    def test_logged_moments_plain_has_game_header(self):
        header = "White - Black 1-0 (2026.01.01 - 30 moves)"
        groups = [{"header": header, "rows": [_clamp_snap()]}]
        plain = _svc().logged_moments_plain(groups)
        self.assertIn(header, plain)

    def test_3x3_plain_has_question_texts(self):
        snap = _3x3_snap()
        plain = _svc().logged_moments_plain(_groups([snap]))
        for key in ("Why1", "Why2", "Why3", "Why4"):
            self.assertIn(THREE_BY_THREE_PROMPTS[key], plain)


# ---------------------------------------------------------------------------
# 19: _split_narrative_blocks
# ---------------------------------------------------------------------------

class TestSplitNarrativeBlocks(unittest.TestCase):
    def test_table_block_identified(self):
        md = "Some text\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nAfter"
        blocks = _split_narrative_blocks(md)
        table_blocks = [b for is_t, b in blocks if is_t]
        self.assertTrue(any("| A | B |" in b for b in table_blocks))

    def test_non_table_blocks_identified(self):
        md = "## Heading\n\n- bullet\n\n| T | A |\n| --- | --- |\n| x | y |"
        blocks = _split_narrative_blocks(md)
        non_table = [b for is_t, b in blocks if not is_t]
        self.assertTrue(any("## Heading" in b for b in non_table))

    def test_order_preserved(self):
        md = "before\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nafter"
        blocks = _split_narrative_blocks(md)
        is_tables = [is_t for is_t, _ in blocks]
        # Expect: [False, True, False]
        self.assertFalse(is_tables[0])
        self.assertTrue(is_tables[1])
        self.assertFalse(is_tables[2])


# ---------------------------------------------------------------------------
# 20: _gfm_table_to_html
# ---------------------------------------------------------------------------

class TestGfmTableToHtml(unittest.TestCase):
    _TABLE = (
        "| Skill | Issue | Impact |\n"
        "| --- | --- | --- |\n"
        "| Calc | Missing forks | Material loss |\n"
    )

    def test_has_table_tag(self):
        h = _gfm_table_to_html(self._TABLE)
        self.assertIn("<table>", h)
        self.assertIn("</table>", h)

    def test_header_cells_as_th(self):
        h = _gfm_table_to_html(self._TABLE)
        self.assertIn("<th", h)
        self.assertIn("Skill", h)
        self.assertIn("Issue", h)
        self.assertIn("Impact", h)

    def test_data_cells_as_td(self):
        h = _gfm_table_to_html(self._TABLE)
        self.assertIn("<td>", h)
        self.assertIn("Missing forks", h)

    def test_cell_content_escaped(self):
        table = "| A | B |\n| --- | --- |\n| <bad> | &amp; |\n"
        h = _gfm_table_to_html(table)
        self.assertIn("&lt;bad&gt;", h)
        # &amp; in source → &amp;amp; in output (double-escaped)
        self.assertIn("&amp;", h)

    def test_bold_in_cell(self):
        table = "| Skill | **bold** |\n| --- | --- |\n| x | y |\n"
        h = _gfm_table_to_html(table)
        self.assertIn("<strong>bold</strong>", h)


# ---------------------------------------------------------------------------
# 21: _encode_text
# ---------------------------------------------------------------------------

class TestEncodeText(unittest.TestCase):
    def test_special_chars_escaped(self):
        result = _encode_text("A < B & C > D")
        self.assertIn("&lt;", result)
        self.assertIn("&amp;", result)
        self.assertIn("&gt;", result)

    def test_newline_becomes_br(self):
        result = _encode_text("line1\nline2")
        self.assertIn("<br>", result)
        self.assertNotIn("\n", result)

    def test_figurine_preserved(self):
        result = _encode_text("Knight ♘")
        self.assertIn("♘", result)


# ---------------------------------------------------------------------------
# 18: game_header_text helper — byte-identical output check
# ---------------------------------------------------------------------------

class TestGameHeaderText(unittest.TestCase):
    """Verify game_header_text() produces the same string as the old inline format."""

    def _old_fmt(self, game) -> str:
        """The original four-liner replaced by game_header_text()."""
        white = str(getattr(game, "white", "") or "").strip() or "Unknown"
        black = str(getattr(game, "black", "") or "").strip() or "Unknown"
        result = str(getattr(game, "result", "") or "").strip() or "*"
        date = str(getattr(game, "date", "") or "").strip() or "????.??.??"
        try:
            moves = int(getattr(game, "moves", 0) or 0)
        except (TypeError, ValueError):
            moves = 0
        return f"{white} - {black} {result} ({date} - {moves} moves)"

    def _game(self, **kw):
        from app.models.database_model import GameData
        return GameData(**kw)

    def test_all_fields_set(self):
        from app.views.dialogs._tag_row_helpers import game_header_text
        g = self._game(game_number=1, white="Kasparov", black="Karpov",
                       result="1-0", date="1985.10.09", moves=42)
        self.assertEqual(game_header_text(g), self._old_fmt(g))

    def test_missing_fields_fallback(self):
        from app.views.dialogs._tag_row_helpers import game_header_text
        g = self._game(game_number=1)
        self.assertEqual(game_header_text(g), self._old_fmt(g))

    def test_missing_fields_output(self):
        from app.views.dialogs._tag_row_helpers import game_header_text
        g = self._game(game_number=1)
        h = game_header_text(g)
        self.assertIn("Unknown - Unknown", h)
        self.assertIn("* (????.??.??", h)

    def test_none_values_treated_as_missing(self):
        from app.views.dialogs._tag_row_helpers import game_header_text
        from app.models.database_model import GameData
        g = GameData(game_number=1, white=None, black=None, result=None, date=None, moves=None)
        self.assertEqual(game_header_text(g), self._old_fmt(g))


if __name__ == "__main__":
    import html  # noqa: F401 (used in TestEscaping.test_blank_why2)
    unittest.main()
