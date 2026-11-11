"""Every player-scoped Chess Log view uses only the selected player's own moves.

Bob (White) vs Alice (Black), with a CLAMP moment on Bob's 2. Nf3 and a 3x3
moment on Alice's 2... Nc6.  With Bob selected, the Narrative Summary prompt,
the charts, the report header counts and the report's Check Logs section use
only BOB-NOTE; with Alice selected, only ALICE-NOTE.  A guard checks that each
view goes through the one shared filter, ``own_moves_paths``.
"""
from __future__ import annotations

import os
import pathlib
import re
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config.config_loader import ConfigLoader
from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService as S
from app.services.chess_log_narrative_service import build_prompt, generate_narrative
from app.services.chess_log_stats_service import aggregate, compute_narrative_counts, get_all_players
from app.utils.chess_log_color_scoping import own_moves_paths

_CONFIG = ConfigLoader().load()
_GET = S.load_resolved_paths

_PGN = (
    '[Event "T"]\n[Site "?"]\n[Date "{date}"]\n[Round "?"]\n'
    '[White "Bob"]\n[Black "Alice"]\n[Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)
BOB_PK = "0.0.0"        # 2. Nf3 — White (Bob) just moved
ALICE_PK = "0.0.0.0"    # 2... Nc6 — Black (Alice) just moved


def _game(date="2026.11.01", bob=True, alice=True):
    game = GameData(game_number=1, pgn=_PGN.format(date=date), white="Bob", black="Alice",
                    date=date, has_chess_log_tags=True)
    tags = {}
    if bob:
        tags[BOB_PK] = [S.make_entry("CLAMP", "L", "BOB-NOTE loose rook", is_shallow=True)]
    if alice:
        tags[ALICE_PK] = [S.make_entry("3x3", "Why1", "ALICE-NOTE wanted to develop", is_shallow=True),
                          S.make_entry("3x3", "Why4", "ALICE-NOTE count attackers")]
    assert S.store_tags(game, tags, {})
    return game


def _prompt(games, player):
    return build_prompt(games, player=player, config=_CONFIG, get_tags_for_game=_GET)


class TestOwnMovesFilter(unittest.TestCase):

    def test_white_player_keeps_white_moves(self):
        game = _game()
        self.assertEqual(list(own_moves_paths(game, _GET(game), "bob")), [BOB_PK])

    def test_black_player_keeps_black_moves(self):
        game = _game()
        self.assertEqual(list(own_moves_paths(game, _GET(game), "alice")), [ALICE_PK])

    def test_no_player_keeps_everything(self):
        game = _game()
        self.assertEqual(set(own_moves_paths(game, _GET(game), "")), {BOB_PK, ALICE_PK})

    def test_player_not_in_game_gets_nothing(self):
        game = _game()
        self.assertEqual(own_moves_paths(game, _GET(game), "carol"), {})

    def test_player_on_both_sides_keeps_everything(self):
        game = _game()
        game.black = "Bob"
        self.assertEqual(set(own_moves_paths(game, _GET(game), "bob")), {BOB_PK, ALICE_PK})


class TestNarrativePrompt(unittest.TestCase):

    def test_bob_prompt_has_only_bob_note(self):
        prompt = _prompt([_game()], "Bob")
        self.assertIn("BOB-NOTE", prompt)
        self.assertNotIn("ALICE-NOTE", prompt)

    def test_alice_prompt_has_only_alice_note(self):
        prompt = _prompt([_game()], "Alice")
        self.assertIn("ALICE-NOTE", prompt)
        self.assertNotIn("BOB-NOTE", prompt)

    def test_bob_counts_are_bobs_clamp_only(self):
        prompt = _prompt([_game()], "Bob")
        counts = prompt.split("## Category counts by preset (over time)", 1)[1]
        self.assertIn("### CLAMP", counts)
        self.assertIn("L 100%", counts)
        self.assertNotIn("## Why-note structure — 3x3", prompt)

    def test_alice_counts_exclude_bobs_clamp(self):
        prompt = _prompt([_game()], "Alice")
        self.assertNotIn("### CLAMP", prompt)
        self.assertNotIn("## Glossary — CLAMP", prompt)
        self.assertIn("## Why-note structure — 3x3", prompt)

    def test_whole_game_notes_still_included(self):
        from app.services.notes_storage_service import NotesStorageService
        game = _game()
        self.assertTrue(NotesStorageService.store_notes(game, "GAME-NOTE whole game", config=_CONFIG))
        game.has_notes = True
        for player in ("Bob", "Alice"):
            self.assertIn("GAME-NOTE", _prompt([game], player))

    @patch("app.services.chess_log_narrative_service.AIService")
    def test_only_opponent_logged_means_no_data(self, MockAIService):
        result = generate_narrative([_game(bob=False)], provider="anthropic", model="m", api_key="k",
                                    base_url_override=None, player="Bob", config=_CONFIG,
                                    get_tags_for_game=_GET)
        self.assertFalse(result.success)
        self.assertEqual(result.text, "No Chess Log data found to summarise.")
        MockAIService.return_value.send_message.assert_not_called()


class TestCharts(unittest.TestCase):

    def test_bob_chart_has_bobs_l(self):
        result = aggregate([_game()], player="Bob", get_tags_for_game=_GET)
        self.assertEqual({p: [b.counts for b in s.bins] for p, s in result.series.items()},
                         {"CLAMP": [{"L": 1}]})
        self.assertFalse(result.has_3x3)

    def test_alice_chart_has_no_clamp(self):
        result = aggregate([_game()], player="Alice", get_tags_for_game=_GET)
        self.assertEqual(result.series, {})
        self.assertTrue(result.has_3x3)

    def test_undated_count_is_own_moves_only(self):
        result = aggregate([_game(date="????.??.??")], player="Alice", get_tags_for_game=_GET)
        self.assertEqual(result.n_undated_clamp_cct, 0)


class TestReportHeaderAgreesWithBody(unittest.TestCase):
    """The report header counts, its charts and its Check Logs section use the same moments."""

    def _report(self, player):
        from app.controllers.chess_log_charts_controller import ChessLogChartsController
        from app.controllers.chess_log_controller import ChessLogController
        game = _game()
        owner = ChessLogController(config={}, game_controller=MagicMock(), database_controller=None)
        ctrl = ChessLogChartsController({}, MagicMock())
        ctrl.set_chess_log_controller(owner)
        ctrl._current_player = player
        with patch.object(ctrl, "_resolve_games", return_value=[game]):
            flagged = ctrl.get_check_log_moments()
        header = compute_narrative_counts([game], player, "both", owner.get_tags_for_game)
        charts = aggregate([game], player=player, get_tags_for_game=owner.get_tags_for_game)
        return header, charts, flagged

    def test_bob(self):
        (n, g, m, s, has_3x3), charts, flagged = self._report("Bob")
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 1, False))
        self.assertEqual(sum(b.total for sr in charts.series.values() for b in sr.bins), m)
        self.assertEqual(charts.has_3x3, has_3x3)
        self.assertEqual([(f.path_key, f.preset) for f in flagged], [(BOB_PK, "CLAMP")])
        self.assertEqual(len(flagged), s)

    def test_alice(self):
        (n, g, m, s, has_3x3), charts, flagged = self._report("Alice")
        self.assertEqual((n, g, m, s, has_3x3), (1, 1, 1, 1, True))
        self.assertEqual(charts.series, {})   # her one moment is 3x3, which is not charted
        self.assertEqual(charts.has_3x3, has_3x3)
        self.assertEqual([(f.path_key, f.preset) for f in flagged], [(ALICE_PK, "3x3")])
        self.assertEqual(len(flagged), s)


class TestPlayerList(unittest.TestCase):

    def test_each_player_credited_for_own_moves(self):
        games = [_game(), _game()]
        self.assertEqual(get_all_players(games, get_tags_for_game=_GET), [("Alice", 2), ("Bob", 2)])

    def test_opponent_moments_do_not_list_a_player(self):
        games = [_game(alice=False), _game(alice=False)]
        self.assertEqual(get_all_players(games, get_tags_for_game=_GET), [("Bob", 2)])


class TestGuardSharedFilter(unittest.TestCase):
    """Every player-scoped view goes through own_moves_paths; none keeps its own copy."""

    def _empty_filter(self):
        calls = []

        def stub(game, paths_data, player_cf):
            calls.append(player_cf)
            return {}
        return stub, calls

    def test_views_use_shared_filter(self):
        game = _game()
        cases = [
            ("app.services.chess_log_stats_service.own_moves_paths",
             lambda: aggregate([game], player="Bob", get_tags_for_game=_GET).series, {}),
            ("app.services.chess_log_stats_service.own_moves_paths",
             lambda: compute_narrative_counts([game], "Bob", "both", _GET)[2], 0),
            ("app.services.chess_log_stats_service.own_moves_paths",
             lambda: get_all_players([game, game], get_tags_for_game=_GET), []),
            ("app.services.chess_log_narrative_service.own_moves_paths",
             lambda: "NOTE" in _prompt([game], "Bob"), False),
        ]
        for target, run, empty in cases:
            stub, calls = self._empty_filter()
            with self.subTest(target=target), patch(target, side_effect=stub):
                self.assertEqual(run(), empty)
                self.assertTrue(calls, f"{target} was not called")

    def test_check_log_moments_use_shared_filter(self):
        from app.controllers.chess_log_charts_controller import ChessLogChartsController
        from app.controllers.chess_log_controller import ChessLogController
        game = _game()
        ctrl = ChessLogChartsController({}, MagicMock())
        ctrl.set_chess_log_controller(
            ChessLogController(config={}, game_controller=MagicMock(), database_controller=None))
        ctrl._current_player = "Bob"
        stub, calls = self._empty_filter()
        with patch.object(ctrl, "_resolve_games", return_value=[game]), \
                patch("app.controllers.chess_log_charts_controller.own_moves_paths", side_effect=stub):
            self.assertEqual(ctrl.get_check_log_moments(), [])
        self.assertTrue(calls)

    def test_no_view_reads_the_side_of_a_path_key_itself(self):
        app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
        users = [
            str(p.relative_to(app_dir.parent))
            for p in app_dir.rglob("*.py")
            if p.name != "chess_log_color_scoping.py"
            and re.search(r"\bcolor_from_path_key\b", p.read_text(encoding="utf-8"))
        ]
        self.assertEqual(users, [], "use own_moves_paths instead of color_from_path_key")


if __name__ == "__main__":
    unittest.main()
