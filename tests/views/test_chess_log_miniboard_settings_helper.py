"""Chess Log mini-board settings are read in one place (C6)."""

import pathlib
import unittest
from unittest.mock import MagicMock, patch

from app.utils.miniature_board_arrows import (
    CHESS_LOG_BEST_ALTERNATIVE,
    CHESS_LOG_PLAYED,
    default_miniature_board_arrows,
)
from app.utils.miniature_board_scales import CHESS_LOG, default_miniature_board_scales
from app.views.dialogs._tag_row_helpers import chess_log_miniboard_settings

_SVC = "app.services.user_settings_service.UserSettingsService.get_instance"
_DIALOGS = pathlib.Path(__file__).resolve().parents[2] / "app" / "views" / "dialogs"


def _owner_defaults():
    return (
        default_miniature_board_scales()[CHESS_LOG],
        default_miniature_board_arrows()[CHESS_LOG_PLAYED],
        default_miniature_board_arrows()[CHESS_LOG_BEST_ALTERNATIVE],
    )


class TestChessLogMiniboardSettings(unittest.TestCase):
    def test_reads_configured_values(self):
        svc = MagicMock()
        svc.get_miniature_boards.return_value = {CHESS_LOG: 1.75}
        svc.get_miniature_board_arrows.return_value = {
            CHESS_LOG_PLAYED: False,
            CHESS_LOG_BEST_ALTERNATIVE: True,
        }
        with patch(_SVC, return_value=svc):
            self.assertEqual(chess_log_miniboard_settings(), (1.75, False, True))

    def test_missing_settings_equal_owner_defaults(self):
        svc = MagicMock()
        svc.get_miniature_boards.return_value = {}
        svc.get_miniature_board_arrows.return_value = {}
        with patch(_SVC, return_value=svc):
            self.assertEqual(chess_log_miniboard_settings(), _owner_defaults())

    def test_unavailable_service_equals_owner_defaults(self):
        with patch(_SVC, side_effect=RuntimeError("no settings")):
            self.assertEqual(chess_log_miniboard_settings(), _owner_defaults())

    def test_both_dialogs_get_the_same_values_from_the_helper(self):
        for mod in ("show_tags_dialog", "show_shallow_tags_dialog"):
            src = (_DIALOGS / f"{mod}.py").read_text(encoding="utf-8")
            self.assertIn("chess_log_miniboard_settings()", src, mod)
            self.assertNotIn("get_miniature_boards", src, mod)
            self.assertNotIn("get_miniature_board_arrows", src, mod)

    def test_no_literal_default_scale_in_dialogs_or_helper(self):
        for name in ("show_tags_dialog.py", "show_shallow_tags_dialog.py", "_tag_row_helpers.py"):
            self.assertNotIn("1.25", (_DIALOGS / name).read_text(encoding="utf-8"), name)


class TestTagRowWidgetDefaultScale(unittest.TestCase):
    def test_scale_factor_default_is_the_owners_default(self):
        import inspect

        from app.views.dialogs.show_tags_dialog import _TagRowWidget

        self.assertIsNone(
            inspect.signature(_TagRowWidget.__init__).parameters["scale_factor"].default
        )


if __name__ == "__main__":
    unittest.main()
