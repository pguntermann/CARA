"""#97: the Chess Log PGN tags are handled like the other CARA tags.

Philipp-approved exception: CARAChessLog* is filtered from the PGN pane and from
the PGN AI Summary sends, and is not cached in header_values.  Chess Log itself
reads game.pgn headers, so the stored tags must survive all of that.
"""

import io
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import chess.pgn

from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService
from app.services.pgn_formatter_service import PgnFormatterService
from app.services.pgn_service import PgnService
from app.utils.game_data_header_sync import game_data_updates_for_header_tag

BASE_PGN = (
    '[Event "T"]\n[Site "?"]\n[Date "2024.01.01"]\n[White "A"]\n[Black "B"]\n'
    '[Result "*"]\n\n1. e4 e5 2. Nf3 *\n'
)
CL_TAGS = ("CARAChessLog", "CARAChessLogInfo", "CARAChessLogChecksum")
PATHS = {"0": [ChessLogStorageService.make_entry("CLAMP", "C", "missed a check")]}


def _game_with_moments() -> GameData:
    game = GameData(game_number=1, pgn=BASE_PGN)
    assert ChessLogStorageService.store_tags(game, PATHS)
    for tag in CL_TAGS:
        assert f"[{tag} " in game.pgn
    return game


def _extract(pgn: str) -> dict:
    """Worker-side parse of one game (parse_pgn_text's process pool is not needed here)."""
    return PgnService._extract_game_data(
        chess.pgn.read_game(io.StringIO(pgn)), pgn
    )


def _display(pgn: str) -> str:
    return PgnFormatterService.filter_pgn_for_display(
        pgn, show_metadata=True, show_comments=True, show_variations=True,
        show_annotations=True, show_results=True, show_non_standard_tags=True,
    )


class TestPgnPaneHidesChessLogTags(unittest.TestCase):
    def test_header_tags_on_shows_none_of_the_chess_log_tags(self):
        out = _display(_game_with_moments().pgn)
        for tag in CL_TAGS:
            self.assertNotIn(tag, out)

    def test_other_headers_unchanged(self):
        out = _display(_game_with_moments().pgn)
        for line in ('[Event "T"]', '[Site "?"]', '[Date "2024.01.01"]',
                     '[White "A"]', '[Black "B"]', '[Result "*"]'):
            self.assertIn(line, out)
        self.assertIn("1. e4", out)

    def test_same_output_as_game_without_chess_log_tags(self):
        game = _game_with_moments()
        with_tags = _display(game.pgn)
        ChessLogStorageService.clear_tags(game)
        self.assertNotIn("CARAChessLog", game.pgn)
        # Removing a trailing tag also eats the blank line before the moves; that is
        # the existing behaviour for every CARA tag, so compare ignoring blank lines.
        keep = lambda t: [ln for ln in t.splitlines() if ln.strip()]
        self.assertEqual(keep(with_tags), keep(_display(game.pgn)))

    def test_all_cara_tag_families_filtered_together(self):
        pgn = _game_with_moments().pgn.replace(
            '[Result "*"]', '[Result "*"]\n[CARANotes "abc"]\n[CARAGameTags "x;y"]'
        )
        out = PgnFormatterService.remove_cara_tags(pgn)
        self.assertNotIn("CARA", out)
        self.assertIn('[Event "T"]', out)


class TestAiSummaryPgnHasNoChessLogTags(unittest.TestCase):
    def test_position_info_pgn_has_no_chess_log_tags(self):
        from app.controllers.ai_chat_controller import AIChatController

        game = _game_with_moments()
        game_model = MagicMock()
        game_model.active_game = game
        game_model.get_active_move_ply.return_value = -1
        game_ctrl = MagicMock()
        game_ctrl.get_game_model.return_value = game_model
        with patch("app.controllers.ai_chat_controller.UserSettingsService"), \
                patch("app.controllers.ai_chat_controller.AIService"):
            ctrl = AIChatController(
                config={}, game_controller=game_ctrl, app_controller=MagicMock()
            )
        _fen, pgn, _ply = ctrl._get_position_info()
        for tag in CL_TAGS:
            self.assertNotIn(tag, pgn)
        self.assertIn('[Event "T"]', pgn)
        self.assertIn("1. e4", pgn)


class TestStoredGameKeepsChessLogTags(unittest.TestCase):
    def test_moments_load_after_formatter_runs(self):
        game = _game_with_moments()
        before = game.pgn
        _display(game.pgn)
        PgnFormatterService.remove_cara_tags(game.pgn)
        self.assertEqual(game.pgn, before)
        loaded = ChessLogStorageService.load_tags(game)
        self.assertEqual(loaded["0"][0]["why"], "missed a check")

    def test_save_reload_round_trip_keeps_moments(self):
        game = _game_with_moments()
        _display(game.pgn)
        reloaded = GameData(game_number=2, pgn=game.pgn)
        self.assertTrue(ChessLogStorageService.has_moments(chess.pgn.read_game(
            io.StringIO(reloaded.pgn)).headers))
        loaded = ChessLogStorageService.load_tags(reloaded)
        self.assertEqual(loaded["0"][0]["cat"], "C")

    def test_parse_pgn_text_keeps_tags_and_flag(self):
        game = _game_with_moments()
        parsed = _extract(game.pgn)
        self.assertTrue(parsed["has_chess_log_tags"])
        for tag in CL_TAGS:
            self.assertIn(f"[{tag} ", parsed["pgn"])


class TestChessLogPayloadNotCachedInHeaderValues(unittest.TestCase):
    def test_parse_skips_payload_but_keeps_other_headers(self):
        values = _extract(_game_with_moments().pgn)["header_values"]
        self.assertNotIn("CARAChessLog", values)
        self.assertEqual(values.get("Event"), "T")

    def test_header_edit_does_not_patch_header_values_for_payload(self):
        u = game_data_updates_for_header_tag("CARAChessLog", "payload")
        self.assertNotIn("_header_values", u)


if __name__ == "__main__":
    unittest.main()
