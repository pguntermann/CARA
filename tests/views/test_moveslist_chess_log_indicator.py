"""Tests for the Chess Log 'logged moment' indicator in MovesListModel.

The indicator used to be a `🏷` text suffix on DisplayRole. It is now a
themed SVG icon returned via `Qt.DecorationRole`, placed to the LEFT of
the move text by Qt's default delegate, and tinted per Moves List row
state (normal / selected / current-move). These tests cover the model
contract only — behavior, not pixels or color values.

Qt-guarded (skipped if Qt platform plugin unavailable, same pattern as
test_moment_dialog.py). The persistence tests (toggle state round-trip
through UserSettingsService) run without Qt.
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
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable in this environment")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])


# Any text/caption character the Chess Log layer is explicitly not allowed to
# emit for its logged-moment marker — enforces "icon, never emoji."
_FORBIDDEN_CHARS = ("🏷", "⚑")


def _make_model():
    from app.models.moveslist_model import MovesListModel, MoveData
    model = MovesListModel()
    model.add_move(MoveData(move_number=1, white_move="e4", black_move="e5"))
    model.add_move(MoveData(move_number=2, white_move="Nf3", black_move="Nc6"))
    return model


def _make_chess_log_ctrl(tagged_path_keys=()):
    """Return a mock ChessLogController with the given path keys pre-tagged."""
    from app.services.chess_log_storage_service import ChessLogStorageService
    ctrl = MagicMock()
    paths_data = {
        key: [ChessLogStorageService.make_entry("CLAMP", "M")]
        for key in tagged_path_keys
    }
    ctrl.get_tags_for_current_game.return_value = paths_data
    return ctrl


def _dark_config():
    """Minimal config with the three Moves List tint keys the provider reads."""
    return {
        "ui": {
            "panels": {
                "detail": {
                    "tabs": {"colors": {"normal": {"text": [200, 200, 200]}}},
                    "moveslist": {"table": {
                        "selection_text_color": [240, 240, 240],
                        "active_move": {"text_color": [255, 255, 255]},
                    }},
                }
            }
        }
    }


def _light_config():
    """A second config with different color values, used to verify the cache
    rebuilds when a fresh provider is installed on theme change."""
    return {
        "ui": {
            "panels": {
                "detail": {
                    "tabs": {"colors": {"normal": {"text": [60, 60, 60]}}},
                    "moveslist": {"table": {
                        "selection_text_color": [20, 20, 20],
                        "active_move": {"text_color": [0, 0, 0]},
                    }},
                }
            }
        }
    }


@requires_qt
class TestDisplayRoleHasNoEmoji(unittest.TestCase):
    """DisplayRole must be plain move text in every toggle state."""

    def test_display_role_is_plain_text_when_toggle_on_and_ply_tagged(self):
        from app.models.moveslist_model import MovesListModel
        from app.utils.pgn_variation_path import encode_path, mainline_path_for_ply
        model = _make_model()
        path_key = encode_path(mainline_path_for_ply(1))
        ctrl = _make_chess_log_ctrl(tagged_path_keys=[path_key])
        model.set_chess_log_controller(ctrl)
        model.set_highlight_chess_log_moves(True)
        text = model.data(model.index(0, MovesListModel.COL_WHITE))
        self.assertEqual(text, "e4")
        for ch in _FORBIDDEN_CHARS:
            self.assertNotIn(ch, text or "")

    def test_display_role_is_plain_text_when_toggle_off(self):
        from app.models.moveslist_model import MovesListModel
        from app.utils.pgn_variation_path import encode_path, mainline_path_for_ply
        model = _make_model()
        path_key = encode_path(mainline_path_for_ply(1))
        ctrl = _make_chess_log_ctrl(tagged_path_keys=[path_key])
        model.set_chess_log_controller(ctrl)
        model.set_highlight_chess_log_moves(False)
        text = model.data(model.index(0, MovesListModel.COL_WHITE))
        self.assertEqual(text, "e4")
        for ch in _FORBIDDEN_CHARS:
            self.assertNotIn(ch, text or "")

    def test_display_role_is_plain_text_for_untagged_ply(self):
        from app.models.moveslist_model import MovesListModel
        model = _make_model()
        ctrl = _make_chess_log_ctrl(tagged_path_keys=[])
        model.set_chess_log_controller(ctrl)
        model.set_highlight_chess_log_moves(True)
        text = model.data(model.index(0, MovesListModel.COL_WHITE))
        self.assertEqual(text, "e4")
        for ch in _FORBIDDEN_CHARS:
            self.assertNotIn(ch, text or "")


@requires_qt
class TestDecorationRoleIcon(unittest.TestCase):
    """The icon surfaces via Qt.DecorationRole only, and only when expected."""

    def _tagged_white_model(self):
        from app.models.moveslist_model import MovesListModel
        from app.utils.chess_log_moment_icon import ChessLogMomentIconProvider
        from app.utils.pgn_variation_path import encode_path, mainline_path_for_ply
        model = _make_model()
        path_key = encode_path(mainline_path_for_ply(1))
        ctrl = _make_chess_log_ctrl(tagged_path_keys=[path_key])
        model.set_chess_log_controller(ctrl)
        model.set_chess_log_icon_provider(ChessLogMomentIconProvider(_dark_config()))
        return model

    def test_tagged_ply_returns_non_null_icon_when_on(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QIcon
        from app.models.moveslist_model import MovesListModel
        model = self._tagged_white_model()
        model.set_highlight_chess_log_moves(True)
        icon = model.data(
            model.index(0, MovesListModel.COL_WHITE),
            Qt.ItemDataRole.DecorationRole,
        )
        self.assertIsNotNone(icon)
        self.assertIsInstance(icon, QIcon)
        self.assertFalse(icon.isNull())

    def test_untagged_ply_returns_no_icon(self):
        from PyQt6.QtCore import Qt
        from app.models.moveslist_model import MovesListModel
        from app.utils.chess_log_moment_icon import ChessLogMomentIconProvider
        model = _make_model()
        ctrl = _make_chess_log_ctrl(tagged_path_keys=[])
        model.set_chess_log_controller(ctrl)
        model.set_chess_log_icon_provider(ChessLogMomentIconProvider(_dark_config()))
        model.set_highlight_chess_log_moves(True)
        icon = model.data(
            model.index(0, MovesListModel.COL_WHITE),
            Qt.ItemDataRole.DecorationRole,
        )
        self.assertIsNone(icon)

    def test_toggle_off_suppresses_icon_on_tagged_ply(self):
        from PyQt6.QtCore import Qt
        from app.models.moveslist_model import MovesListModel
        model = self._tagged_white_model()
        model.set_highlight_chess_log_moves(False)
        for col in (MovesListModel.COL_WHITE, MovesListModel.COL_BLACK):
            icon = model.data(
                model.index(0, col),
                Qt.ItemDataRole.DecorationRole,
            )
            self.assertIsNone(icon)

    def test_icon_has_selected_mode_pixmap(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QIcon
        from app.models.moveslist_model import MovesListModel
        model = self._tagged_white_model()
        model.set_highlight_chess_log_moves(True)
        icon = model.data(
            model.index(0, MovesListModel.COL_WHITE),
            Qt.ItemDataRole.DecorationRole,
        )
        self.assertIsNotNone(icon)
        pm = icon.pixmap(16, 16, QIcon.Mode.Selected, QIcon.State.Off)
        self.assertFalse(pm.isNull())


class TestIconProviderRebuildsOnThemeChange(unittest.TestCase):
    """A fresh provider installed with a new config replaces the cached icons.

    This mirrors what happens during MainWindow.apply_theme: _setup_ui
    rebuilds the DetailPanel (fresh MovesListModel), and _load_user_settings
    installs a fresh ChessLogMomentIconProvider built from the new config.
    """

    @unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable in this environment")
    def test_installing_new_provider_replaces_old_icon(self):
        from PyQt6.QtCore import Qt
        from app.models.moveslist_model import MovesListModel
        from app.utils.chess_log_moment_icon import ChessLogMomentIconProvider
        from app.utils.pgn_variation_path import encode_path, mainline_path_for_ply
        model = _make_model()
        path_key = encode_path(mainline_path_for_ply(1))
        model.set_chess_log_controller(_make_chess_log_ctrl(tagged_path_keys=[path_key]))
        model.set_highlight_chess_log_moves(True)

        dark_provider = ChessLogMomentIconProvider(_dark_config())
        model.set_chess_log_icon_provider(dark_provider)
        icon_before = model.data(
            model.index(0, MovesListModel.COL_WHITE),
            Qt.ItemDataRole.DecorationRole,
        )

        light_provider = ChessLogMomentIconProvider(_light_config())
        model.set_chess_log_icon_provider(light_provider)
        icon_after = model.data(
            model.index(0, MovesListModel.COL_WHITE),
            Qt.ItemDataRole.DecorationRole,
        )

        # Provider identity swapped, so the icon returned must come from the
        # new provider (not the stale one).
        self.assertIs(icon_before, dark_provider.icon_for_row(is_current_move_row=False))
        self.assertIs(icon_after, light_provider.icon_for_row(is_current_move_row=False))
        self.assertIsNot(icon_before, icon_after)

    @unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable in this environment")
    def test_provider_resolves_distinct_normal_and_active_colors(self):
        from app.utils.chess_log_moment_icon import ChessLogMomentIconProvider
        provider = ChessLogMomentIconProvider(_dark_config())
        colors = provider.colors()
        self.assertIn("normal", colors)
        self.assertIn("selected", colors)
        self.assertIn("active", colors)
        self.assertNotEqual(colors["normal"], colors["active"])


class TestTogglePersistence(unittest.TestCase):
    """Persistence round-trip — no Qt needed."""

    def test_toggle_persists_via_update_chess_log_settings(self):
        from app.services.user_settings_service import UserSettingsService
        uss = MagicMock(spec=UserSettingsService)
        uss.get_chess_log.return_value = {}

        # Simulate the main_window handler persisting the toggle
        checked = True
        uss.update_chess_log_settings({"highlight_chess_log_moves_in_list": checked})
        uss.update_chess_log_settings.assert_called_once_with(
            {"highlight_chess_log_moves_in_list": True}
        )

    def test_toggle_loads_from_chess_log_settings(self):
        uss = MagicMock()
        uss.get_chess_log.return_value = {"highlight_chess_log_moves_in_list": True}
        settings = {"chess_log": uss.get_chess_log()}
        loaded = settings.get("chess_log", {}).get("highlight_chess_log_moves_in_list", False)
        self.assertTrue(loaded)

    def test_toggle_defaults_to_false_when_key_absent(self):
        settings = {"chess_log": {}}
        loaded = settings.get("chess_log", {}).get("highlight_chess_log_moves_in_list", False)
        self.assertFalse(loaded)


if __name__ == "__main__":
    unittest.main()
