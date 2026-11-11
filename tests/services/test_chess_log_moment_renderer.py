"""Unit tests for the shared moment renderer (#93)."""

from __future__ import annotations

import html as html_lib
import re
import unittest
from unittest.mock import MagicMock

from app.models.database_model import GameData
from app.services.chess_log_moment_renderer import ChessLogMomentRenderer, MomentRef
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS as Q

_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"][Round "?"]'
    '[White "Alice"][Black "Bob"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 *\n"
)
WHITE_PK = "0.0.0"   # 2. Nf3
BLACK_PK = "0.0.0.0"  # 2… Nc6
PATH_KEY_RE = re.compile(r"\d+(?:\.\d+){2,}")


def _game(pgn=_PGN):
    return GameData(game_number=1, pgn=pgn, white="Alice", black="Bob", result="*")


def _e(preset, cat, why, **extra):
    d = {"preset": preset, "cat": cat, "why": why}
    d.update(extra)
    return d


def _render(tags, preset, pk, game=None):
    game = game or _game()
    ctrl = MagicMock()
    ctrl.get_tags_for_game.side_effect = lambda g: tags if g is game else {}
    out = ChessLogMomentRenderer(ctrl, {}).render([MomentRef(game, pk, preset)])
    return out


def _html_text(fragment: str) -> str:
    """Visible text of an HTML fragment, one line per block."""
    t = re.sub(r"</p>|<br>|</h3>|<hr>", "\n", fragment)
    t = re.sub(r"<[^>]+>", "", t)
    return html_lib.unescape(t).replace("\xa0", " ")


def _norm(text: str) -> str:
    return " ".join(text.split())


class TestMoveLabel(unittest.TestCase):
    def test_white_move_uses_dot(self):
        out = _render({WHITE_PK: [_e("CLAMP", "C", "n")]}, "CLAMP", WHITE_PK)
        self.assertIn("2. Nf3", out.plain)
        self.assertNotIn("2… Nf3", out.plain)

    def test_black_move_uses_ellipsis(self):
        out = _render({BLACK_PK: [_e("CLAMP", "C", "n")]}, "CLAMP", BLACK_PK)
        self.assertIn("2… Nc6", out.plain)

    def test_path_key_never_shown_for_located_move(self):
        out = _render({BLACK_PK: [_e("CLAMP", "C", "n")]}, "CLAMP", BLACK_PK)
        self.assertNotRegex(out.plain, PATH_KEY_RE)
        self.assertNotRegex(_html_text(out.html), PATH_KEY_RE)

    def test_unlocatable_move_falls_back_without_path_key(self):
        out = _render({"0.0.0.0.0.0": [_e("CLAMP", "C", "n")]}, "CLAMP", "0.0.0.0.0.0")
        self.assertIn("Unknown move", out.plain)
        self.assertNotRegex(out.plain, PATH_KEY_RE)
        self.assertNotRegex(_html_text(out.html), PATH_KEY_RE)

    def test_game_without_pgn_falls_back_without_path_key(self):
        game = _game(pgn="")
        out = _render({WHITE_PK: [_e("3x3", "Why1", "a")]}, "3x3", WHITE_PK, game=game)
        self.assertNotRegex(out.plain, PATH_KEY_RE)

    def test_game_header_shown_once_per_game(self):
        game = _game()
        tags = {WHITE_PK: [_e("CLAMP", "C", "a")], BLACK_PK: [_e("CLAMP", "L", "b")]}
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = tags
        out = ChessLogMomentRenderer(ctrl, {}).render(
            [MomentRef(game, WHITE_PK, "CLAMP"), MomentRef(game, BLACK_PK, "CLAMP")]
        )
        self.assertEqual(out.plain.count("Alice - Bob"), 1)


class TestMarkersClamp(unittest.TestCase):
    def test_shallow_marker_after_note(self):
        out = _render({WHITE_PK: [_e("CLAMP", "C", "open the h-file", is_shallow=True)]}, "CLAMP", WHITE_PK)
        self.assertIn("open the h-file [Shallow]", out.plain)

    def test_vague_marker_after_note(self):
        out = _render({WHITE_PK: [_e("CLAMP", "C", "be careful", is_vague=True)]}, "CLAMP", WHITE_PK)
        self.assertIn("be careful [Vague]", out.plain)

    def test_both_markers_in_order(self):
        out = _render(
            {WHITE_PK: [_e("CLAMP", "C", "stuff", is_shallow=True, is_vague=True)]}, "CLAMP", WHITE_PK
        )
        self.assertIn("stuff [Shallow] [Vague]", out.plain)

    def test_ignored_chip_is_unmarked(self):
        out = _render(
            {WHITE_PK: [_e("CLAMP", "C", "stuff", is_shallow=True, ignore_shallow=True)]}, "CLAMP", WHITE_PK
        )
        self.assertIn("stuff", out.plain)
        self.assertNotIn("[Shallow]", out.plain)
        self.assertNotIn("9a4400", out.html)

    def test_ignore_is_dropped_when_text_changed_since(self):
        # Same staleness rule as the dialogs: Ignore only counts for the text it was set on.
        entry = _e(
            "CLAMP", "C", "edited text", is_shallow=True, ignore_shallow=True,
            ignore_text_hash=ChessLogStorageService.compute_check_hash("old text"),
        )
        out = _render({WHITE_PK: [entry]}, "CLAMP", WHITE_PK)
        self.assertIn("[Shallow]", out.plain)

    def test_unsaved_verdict_is_unmarked(self):
        # The renderer takes no classifier keys: an entry without a saved flag is unmarked.
        out = _render({WHITE_PK: [_e("CLAMP", "C", "stuff")]}, "CLAMP", WHITE_PK)
        self.assertNotIn("[", out.plain)

    def test_other_presets_at_same_path_are_not_rendered(self):
        out = _render(
            {WHITE_PK: [_e("CLAMP", "C", "clamp note"), _e("CCT", "Checks", "cct note")]},
            "CLAMP", WHITE_PK,
        )
        self.assertIn("clamp note", out.plain)
        self.assertNotIn("cct note", out.plain)

    def test_cct_moment(self):
        out = _render({WHITE_PK: [_e("CCT", "Checks", "cct note", is_vague=True)]}, "CCT", WHITE_PK)
        self.assertIn("cct note [Vague]", out.plain)


class TestMarkers3x3(unittest.TestCase):
    TAGS = {
        BLACK_PK: [
            _e("3x3", "Why1", "I wanted to open the h-file", is_shallow=True),
            _e("3x3", "Why2", "fine"),
            _e("3x3", "Why3", "Nf3", is_shallow=True, ignore_shallow=True),
            _e("3x3", "Why4", "Be more careful", is_vague=True),
        ]
    }

    def test_every_answer_listed_in_order_with_markers_after(self):
        lines = _render(self.TAGS, "3x3", BLACK_PK).plain.splitlines()
        body = [ln.strip() for ln in lines[2:]]
        self.assertEqual(body, [
            f"{Q['Why1']} I wanted to open the h-file [Shallow]",
            f"{Q['Why2']} fine",
            f"{Q['Why3']} Nf3",                      # Ignored: unmarked
            f"{Q['Why4']} Be more careful [Vague]",
        ])

    def test_no_why_n_labels(self):
        self.assertNotRegex(_render(self.TAGS, "3x3", BLACK_PK).plain, r"Why\d")

    def test_black_move_header(self):
        self.assertIn("2… Nc6", _render(self.TAGS, "3x3", BLACK_PK).plain)

    def test_both_markers_on_one_answer(self):
        tags = {WHITE_PK: [_e("3x3", "Why4", "x", is_shallow=True, is_vague=True)]}
        self.assertIn(f"{Q['Why4']} x [Shallow] [Vague]", _render(tags, "3x3", WHITE_PK).plain)

    def test_blank_answer_listed_without_marker(self):
        tags = {WHITE_PK: [_e("3x3", "Why1", "a"), _e("3x3", "Why2", "", is_shallow=True)]}
        plain = _render(tags, "3x3", WHITE_PK).plain
        self.assertIn(f"  {Q['Why2']}\n", plain + "\n")     # question, nothing after it
        self.assertIn(f"  {Q['Why3']}\n", plain + "\n")
        self.assertNotIn("[", plain)


class TestPlyOrder(unittest.TestCase):
    def test_moments_listed_in_ply_order_within_a_game(self):
        game = _game()
        late, early, mid = "0.0.0.0", "0", "0.0.0"
        tags = {late: [_e("CLAMP", "C", "late")], early: [_e("CLAMP", "C", "early")],
                mid: [_e("CLAMP", "C", "mid")]}
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = tags
        out = ChessLogMomentRenderer(ctrl, {}).render([MomentRef(game, pk, "CLAMP") for pk in (late, early, mid)])
        self.assertEqual([w for w in re.findall(r"early|mid|late", out.plain)], ["early", "mid", "late"])
        self.assertEqual([w for w in re.findall(r"early|mid|late", out.html)], ["early", "mid", "late"])

    def test_games_keep_first_appearance_order(self):
        g1, g2 = _game(), _game()
        g1.white, g2.white = "First", "Second"
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = {WHITE_PK: [_e("CLAMP", "C", "n")], "0": [_e("CLAMP", "C", "n")]}
        out = ChessLogMomentRenderer(ctrl, {}).render([
            MomentRef(g1, WHITE_PK, "CLAMP"), MomentRef(g2, "0", "CLAMP"), MomentRef(g1, "0", "CLAMP"),
        ])
        self.assertLess(out.plain.index("First"), out.plain.index("Second"))
        self.assertEqual(out.plain.count("First"), 1)


class TestEntriesFor(unittest.TestCase):
    def test_entries_for_replaces_controller_entries(self):
        game = _game()
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = {WHITE_PK: [_e("CLAMP", "C", "saved text")]}
        ref = MomentRef(game, WHITE_PK, "CLAMP")
        out = ChessLogMomentRenderer(ctrl, {}).render(
            [ref], entries_for=lambda r: [_e("CLAMP", "C", "pending text", is_shallow=True)]
        )
        self.assertIn("pending text [Shallow]", out.plain)
        self.assertNotIn("saved text", out.plain)
        ctrl.get_tags_for_game.assert_not_called()


class TestHtmlMatchesText(unittest.TestCase):
    def _same(self, tags, preset, pk):
        out = _render(tags, preset, pk)
        # The HTML draws the marker as a chip (label only); the text brackets it.
        plain_marks_as_labels = out.plain.replace("[Shallow]", "Shallow").replace("[Vague]", "Vague")
        self.assertEqual(_norm(_html_text(out.html)), _norm(plain_marks_as_labels))
        return out

    def test_3x3(self):
        out = self._same(TestMarkers3x3.TAGS, "3x3", BLACK_PK)
        self.assertIn("9a4400", out.html)   # Shallow chip
        self.assertIn("1d4ed8", out.html)   # Vague chip

    def test_clamp(self):
        out = self._same(
            {WHITE_PK: [_e("CLAMP", "C", "stuff & <things>", is_shallow=True, is_vague=True)]},
            "CLAMP", WHITE_PK,
        )
        self.assertIn("&lt;things&gt;", out.html)

    def test_cct(self):
        self._same({WHITE_PK: [_e("CCT", "Checks", "note", is_vague=True)]}, "CCT", WHITE_PK)

    def test_blank_3x3_answers(self):
        self._same({WHITE_PK: [_e("3x3", "Why1", "a")]}, "3x3", WHITE_PK)

    def test_chip_follows_answer_text_in_html(self):
        out = _render({WHITE_PK: [_e("3x3", "Why1", "answer text", is_shallow=True)]}, "3x3", WHITE_PK)
        self.assertLess(out.html.index("answer text"), out.html.index("9a4400"))


class TestRendererIsReadOnly(unittest.TestCase):
    def test_reads_through_controller_and_does_not_mutate_entries(self):
        entry = _e("CLAMP", "C", "n", is_shallow=True)
        before = dict(entry)
        game = _game()
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = {WHITE_PK: [entry]}
        ChessLogMomentRenderer(ctrl, {}).render([MomentRef(game, WHITE_PK, "CLAMP")])
        self.assertEqual(entry, before)
        ctrl.get_tags_for_game.assert_called_with(game)
        self.assertEqual([c[0] for c in ctrl.method_calls], ["get_tags_for_game"])

    def test_empty_refs_render_empty(self):
        out = ChessLogMomentRenderer(MagicMock(), {}).render([])
        self.assertEqual((out.plain, out.html), ("", ""))


if __name__ == "__main__":
    unittest.main()
