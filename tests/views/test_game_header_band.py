"""Tests for the shared Chess Log game-header band (make_game_header) and its use
in ShowTagsDialog and ShowShallowTagsDialog.

Requires a working Qt platform plugin (CI uses QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

_PGN_1 = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 *\n"
)
_PGN_2 = (
    '[Event "T"][Site "?"][Date "2026.02.01"]'
    '[Round "?"][White "X"][Black "Y"][Result "1-0"]\n\n'
    "1. d4 d5 2. c4 e6 *\n"
)
_THEMES = ["style_default.config.json", "style_light.config.json", "style_scholar.config.json"]


def _theme_config(style_ref: str) -> dict:
    from app.config.config_loader import ConfigLoader
    return ConfigLoader().load_with_style_override(style_ref)


def _luminance(rgb) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@requires_qt
class TestMakeGameHeader(unittest.TestCase):
    def test_colors_come_from_each_theme_config(self):
        from app.views.dialogs._tag_row_helpers import make_game_header
        for style in _THEMES:
            with self.subTest(style=style):
                cfg = _theme_config(style)
                gh = cfg["ui"]["dialogs"]["moment"]["game_header"]
                w = make_game_header(cfg, "A - B 1-0", True)
                ss = w.band.styleSheet()
                self.assertIn("rgb({},{},{})".format(*gh["background_color"]), ss)
                self.assertIn("rgb({},{},{})".format(*gh["text_color"]), ss)

    def test_default_theme_is_the_approved_blue_and_white(self):
        gh = _theme_config("style_default.config.json")["ui"]["dialogs"]["moment"]["game_header"]
        self.assertEqual(list(gh["background_color"]), [47, 79, 122])
        self.assertEqual(list(gh["text_color"]), [255, 255, 255])

    def test_contrast_at_least_4_5_in_every_theme(self):
        for style in _THEMES:
            with self.subTest(style=style):
                gh = _theme_config(style)["ui"]["dialogs"]["moment"]["game_header"]
                self.assertGreaterEqual(
                    _contrast(gh["background_color"], gh["text_color"]), 4.5
                )

    def test_first_header_has_no_top_spacing_later_get_30(self):
        from app.views.dialogs._tag_row_helpers import make_game_header
        cfg = _theme_config("style_default.config.json")
        first = make_game_header(cfg, "t", True)
        later = make_game_header(cfg, "t", False)
        self.assertEqual(first.layout().contentsMargins().top(), 0)
        self.assertEqual(later.layout().contentsMargins().top(), 30)
        self.assertEqual(later.layout().contentsMargins().bottom(), 0)

    def test_style_has_bold_padding_and_no_border(self):
        from app.views.dialogs._tag_row_helpers import make_game_header
        w = make_game_header(_theme_config("style_default.config.json"), "t", False)
        ss = w.band.styleSheet()
        self.assertIn("font-weight: bold", ss)
        self.assertIn("padding: 7px 16px", ss)
        self.assertIn("border: none", ss)
        self.assertNotIn("1px solid", ss)

    def test_text_is_passed_through(self):
        from app.views.dialogs._tag_row_helpers import make_game_header
        w = make_game_header({}, "Alice - Bob 1-0 (2026.01.01 - 3 moves)", True)
        self.assertEqual(w.band.text(), "Alice - Bob 1-0 (2026.01.01 - 3 moves)")


def _bands(dlg):
    from PyQt6.QtWidgets import QLabel
    return [w for w in dlg.findChildren(QLabel) if w.objectName() == "game_header_band"]


def _gap(band) -> int:
    return band.parentWidget().layout().contentsMargins().top()


@requires_qt
class TestDialogsUseHeaderBand(unittest.TestCase):
    def test_show_tags_dialog_two_games(self):
        from app.models.database_model import GameData
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        g1 = GameData(game_number=1, pgn=_PGN_1)
        g2 = GameData(game_number=2, pgn=_PGN_2)
        tags = {1: {"0": [S.make_entry("CLAMP", "C", "")]}, 2: {"0": [S.make_entry("CLAMP", "C", "")]}}
        ctrl = MagicMock()
        ctrl.get_tags_for_game.side_effect = lambda g: tags.get(g.game_number, {})
        ctrl.game_has_any_tags.return_value = True
        cfg = _theme_config("style_default.config.json")
        dlg = ShowTagsDialog(cfg, [g1, g2], ctrl)
        bands = _bands(dlg)
        self.assertEqual(len(bands), 2)
        self.assertEqual([_gap(b) for b in bands], [0, 30])

    def test_show_shallow_tags_dialog_two_games(self):
        from app.models.database_model import GameData
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        g1 = GameData(game_number=1, pgn=_PGN_1)
        g2 = GameData(game_number=2, pgn=_PGN_2)
        tags = {1: {"0": [S.make_entry("CLAMP", "C", "I blundered")]}, 2: {"0": [S.make_entry("CLAMP", "C", "I blundered")]}}
        from tests.views.test_show_shallow_tags_dialog import _make_controller
        ctrl = _make_controller(tags)
        keys = {(g1, "0", "CLAMP", ""), (g2, "0", "CLAMP", "")}
        cfg = _theme_config("style_default.config.json")
        dlg = ShowShallowTagsDialog(
            config=cfg, games=[g1, g2], controller=ctrl,
            shallow_keys=keys, saved_mode=True,
        )
        bands = _bands(dlg)
        self.assertEqual(len(bands), 2)
        self.assertEqual([_gap(b) for b in bands], [0, 30])


if __name__ == "__main__":
    unittest.main()
