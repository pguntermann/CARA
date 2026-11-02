"""Tests for Chess Log Charts registration in detail-panel Show/Hide (#49).

Covers:
- Registry: chess_log_charts unit presence, label, tab_title, menu_title
- default_detail_panel_visibility() includes chess_log_charts as True
- normalize_detail_panel_visibility() treats missing key as True
- user_settings.json.template contains chess_log_charts: true
- Qt: _apply_unit_submenus hides/shows submenu and separator
- Qt: _view_action_for_unit returns chess_log_charts action
- Qt: _switch_detail_tab_by_id("chess_log_charts") works even when an earlier tab is hidden
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Qt availability probe
# ---------------------------------------------------------------------------

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


_QT_AVAILABLE = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")

if _QT_AVAILABLE:
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QApplication, QMenu, QTabWidget
    _app = QApplication.instance() or QApplication(sys.argv[:1])


# ---------------------------------------------------------------------------
# Repository root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Pure-Python registry tests
# ---------------------------------------------------------------------------

class TestChessLogChartsRegistration(unittest.TestCase):
    """chess_log_charts is present in the registry with correct fields."""

    def setUp(self):
        from app.services.detail_panel_visibility import DETAIL_PANEL_VISIBILITY_UNITS
        self.units = {u.id: u for u in DETAIL_PANEL_VISIBILITY_UNITS}

    def test_unit_registered(self):
        self.assertIn("chess_log_charts", self.units)

    def test_label(self):
        self.assertEqual(self.units["chess_log_charts"].label, "Chess Log")

    def test_tab_title(self):
        self.assertEqual(self.units["chess_log_charts"].tab_title, "Chess Log")

    def test_menu_title_is_none(self):
        # Top-level Chess Log menu stays visible even when the tab is hidden.
        self.assertIsNone(self.units["chess_log_charts"].menu_title)

    def test_notes_comes_before_chess_log_charts(self):
        from app.services.detail_panel_visibility import DETAIL_PANEL_VISIBILITY_UNITS
        ids = [u.id for u in DETAIL_PANEL_VISIBILITY_UNITS]
        self.assertLess(ids.index("notes"), ids.index("chess_log_charts"))


class TestDefaultVisibility(unittest.TestCase):
    """default_detail_panel_visibility includes chess_log_charts as True."""

    def test_chess_log_charts_in_defaults(self):
        from app.services.detail_panel_visibility import default_detail_panel_visibility
        defaults = default_detail_panel_visibility()
        self.assertIn("chess_log_charts", defaults)
        self.assertTrue(defaults["chess_log_charts"])


class TestNormalizeVisibility(unittest.TestCase):
    """normalize_detail_panel_visibility treats missing chess_log_charts as True."""

    def test_empty_dict_gives_true(self):
        from app.services.detail_panel_visibility import normalize_detail_panel_visibility
        result = normalize_detail_panel_visibility({})
        self.assertTrue(result.get("chess_log_charts", False))

    def test_pre_issue49_map_gives_true(self):
        # A settings dict saved before #49 lacks the key; it should default to visible.
        from app.services.detail_panel_visibility import normalize_detail_panel_visibility
        pre_issue49 = {
            "moves_list": True,
            "metadata": True,
            "manual_analysis": True,
            "opening_explorer": True,
            "game_summary": True,
            "player_stats": True,
            "annotations": True,
            "ai_summary": True,
            "notes": True,
        }
        result = normalize_detail_panel_visibility(pre_issue49)
        self.assertTrue(result.get("chess_log_charts", False))

    def test_explicit_false_is_respected(self):
        from app.services.detail_panel_visibility import normalize_detail_panel_visibility
        result = normalize_detail_panel_visibility({"chess_log_charts": False})
        self.assertFalse(result["chess_log_charts"])

    def test_explicit_true_is_respected(self):
        from app.services.detail_panel_visibility import normalize_detail_panel_visibility
        result = normalize_detail_panel_visibility({"chess_log_charts": True})
        self.assertTrue(result["chess_log_charts"])


# ---------------------------------------------------------------------------
# Template test
# ---------------------------------------------------------------------------

class TestSettingsTemplate(unittest.TestCase):
    """user_settings.json.template contains chess_log_charts: true."""

    def test_template_contains_chess_log_charts(self):
        template_path = _REPO_ROOT / "user_settings.json.template"
        self.assertTrue(template_path.exists(), f"Template not found: {template_path}")
        with open(template_path, encoding="utf-8") as f:
            data = json.load(f)
        visibility = data.get("detail_panel_visibility", {})
        self.assertIn("chess_log_charts", visibility)
        self.assertTrue(visibility["chess_log_charts"])


# ---------------------------------------------------------------------------
# Qt tests: _apply_unit_submenus, _view_action_for_unit, _switch_detail_tab_by_id
# ---------------------------------------------------------------------------

if _QT_AVAILABLE:
    import types

    def _make_minimal_mw():
        """Build a minimal stub with the attributes _apply_unit_submenus needs."""
        from app.main_window import MainWindow

        # Bind methods onto a plain namespace object to avoid a full MainWindow init.
        mw = types.SimpleNamespace()

        # Bind the relevant methods from MainWindow.
        mw._apply_unit_submenus = MainWindow._apply_unit_submenus.__get__(mw, type(mw))
        mw._view_action_for_unit = MainWindow._view_action_for_unit.__get__(mw, type(mw))
        mw._switch_detail_tab = MainWindow._switch_detail_tab.__get__(mw, type(mw))
        mw._switch_detail_tab_by_id = MainWindow._switch_detail_tab_by_id.__get__(mw, type(mw))
        mw._find_detail_tab_index = MainWindow._find_detail_tab_index.__get__(mw, type(mw))
        mw._get_detail_panel_visibility = lambda: {
            u.id: True
            for u in __import__(
                "app.services.detail_panel_visibility",
                fromlist=["DETAIL_PANEL_VISIBILITY_UNITS"],
            ).DETAIL_PANEL_VISIBILITY_UNITS
        }

        # Tab widget with 10 tabs matching the real detail_panel order.
        tab_widget = QTabWidget()
        for title in [
            "Moves List", "PGN header tags", "Manual Analysis", "Opening Explorer",
            "Game Summary", "Player Stats", "Annotations", "AI Summary", "Notes", "Chess Log",
        ]:
            tab_widget.addTab(__import__("PyQt6.QtWidgets", fromlist=["QWidget"]).QWidget(), title)

        detail_panel = types.SimpleNamespace()
        detail_panel.tab_widget = tab_widget
        mw.detail_panel = detail_panel

        # F-key actions.
        mw.view_chess_log_charts_action = QAction("Chess Log")
        mw.view_chess_log_charts_action.setEnabled(True)

        # Submenu and separator — keep parent_menu alive on mw to prevent GC.
        parent_menu = QMenu()
        mw._chess_log_parent_menu = parent_menu
        mw._chess_log_charts_settings_separator = parent_menu.addSeparator()
        submenu = parent_menu.addMenu("Time series settings")
        mw.chess_log_charts_settings_menu = submenu

        return mw

    @requires_qt
    class TestApplyUnitSubmenus(unittest.TestCase):
        """_apply_unit_submenus hides/shows the submenu and separator."""

        def setUp(self):
            self.mw = _make_minimal_mw()

        def test_hide_hides_submenu_action(self):
            self.mw._apply_unit_submenus("chess_log_charts", False)
            self.assertFalse(self.mw.chess_log_charts_settings_menu.menuAction().isVisible())

        def test_hide_hides_separator(self):
            self.mw._apply_unit_submenus("chess_log_charts", False)
            self.assertFalse(self.mw._chess_log_charts_settings_separator.isVisible())

        def test_show_shows_submenu_action(self):
            self.mw._apply_unit_submenus("chess_log_charts", False)
            self.mw._apply_unit_submenus("chess_log_charts", True)
            self.assertTrue(self.mw.chess_log_charts_settings_menu.menuAction().isVisible())

        def test_show_shows_separator(self):
            self.mw._apply_unit_submenus("chess_log_charts", False)
            self.mw._apply_unit_submenus("chess_log_charts", True)
            self.assertTrue(self.mw._chess_log_charts_settings_separator.isVisible())

        def test_other_unit_does_not_affect_submenu(self):
            self.mw._apply_unit_submenus("notes", False)
            # Submenu should remain visible — notes doesn't own it.
            self.assertTrue(self.mw.chess_log_charts_settings_menu.menuAction().isVisible())

    @requires_qt
    class TestViewActionForUnit(unittest.TestCase):
        """_view_action_for_unit returns chess_log_charts action."""

        def setUp(self):
            self.mw = _make_minimal_mw()

        def test_returns_chess_log_charts_action(self):
            action = self.mw._view_action_for_unit("chess_log_charts")
            self.assertIs(action, self.mw.view_chess_log_charts_action)

        def test_unknown_unit_returns_none(self):
            action = self.mw._view_action_for_unit("nonexistent_unit")
            self.assertIsNone(action)

    @requires_qt
    class TestSwitchDetailTabById(unittest.TestCase):
        """_switch_detail_tab_by_id('chess_log_charts') navigates to Chess Log."""

        def setUp(self):
            self.mw = _make_minimal_mw()

        def test_switches_to_chess_log_tab(self):
            # Start on Moves List (index 0).
            self.mw.detail_panel.tab_widget.setCurrentIndex(0)
            result = self.mw._switch_detail_tab_by_id("chess_log_charts")
            self.assertTrue(result)
            self.assertEqual(self.mw.detail_panel.tab_widget.currentIndex(), 9)

        def test_index_independent_of_earlier_hidden_tab(self):
            # Hide Opening Explorer (index 3) — physical indexes don't shift.
            self.mw.detail_panel.tab_widget.setTabVisible(3, False)
            result = self.mw._switch_detail_tab_by_id("chess_log_charts")
            self.assertTrue(result)
            self.assertEqual(self.mw.detail_panel.tab_widget.currentIndex(), 9)

        def test_no_switch_when_tab_is_hidden(self):
            # Mark Chess Log hidden in visibility so _switch_detail_tab_by_id refuses.
            self.mw._get_detail_panel_visibility = lambda: {"chess_log_charts": False}
            self.mw.detail_panel.tab_widget.setCurrentIndex(0)
            result = self.mw._switch_detail_tab_by_id("chess_log_charts")
            self.assertFalse(result)
            self.assertEqual(self.mw.detail_panel.tab_widget.currentIndex(), 0)


# ---------------------------------------------------------------------------
# Real-menu fixture and integration tests
# ---------------------------------------------------------------------------

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import QMainWindow, QWidget

    def _make_mw_real_menus():
        """Build a QMainWindow with the real Chess Log menu and bound MainWindow methods.

        Returns ``(mw, visibility_dict)`` where ``visibility_dict`` is the mutable
        dict returned by ``mw._get_detail_panel_visibility()``.  Mutate it, then call
        ``mw._apply_detail_panel_visibility()`` to drive the assertions.
        """
        import tempfile
        from app.main_window import MainWindow
        from app.services.detail_panel_visibility import DETAIL_PANEL_VISIBILITY_UNITS
        from app.services.user_settings_service import UserSettingsService
        from app.views.menus.chess_log_menu import setup_chess_log_menu

        # Ensure the UserSettingsService singleton is live (setup_chess_log_menu needs it).
        if UserSettingsService._instance is None:
            tmp_path = Path(tempfile.mktemp(suffix=".json"))
            svc = UserSettingsService(settings_path=tmp_path)
            svc.load()
            UserSettingsService._instance = svc

        # Real QMainWindow so menuBar() and QAction parents work correctly.
        mw = QMainWindow()

        # Handler stubs required by setup_chess_log_menu.
        mw._apply_menu_styling = lambda menu: None
        mw._show_chess_log_settings = lambda: None
        mw._clear_chess_log_for_current_game = lambda: None
        mw._save_chess_log_for_current_game = lambda: None
        mw._save_chess_logs_for_all_games = lambda: None
        mw._show_chess_logs_for_all_games = lambda: None
        mw._show_saved_shallow_logs = lambda: None
        mw._on_highlight_chess_log_moves_toggled = lambda checked=False: None
        # set_menubar_themable_action_icon reads mw.config for icon tinting; empty
        # dict is fine — menu_icon_tint_rgb falls back to (200, 200, 200).
        mw.config = {}

        # Build the real Chess Log menu.  This sets _chess_log_charts_settings_separator,
        # chess_log_charts_settings_menu, chess_log_settings_action, clear_chess_log_action,
        # save_chess_log_action, save_all_chess_logs_action, show_all_chess_logs_action,
        # show_saved_shallow_logs_action, and highlight_chess_log_moves_action on mw.
        setup_chess_log_menu(mw, mw.menuBar())

        # F-key action (View menu would normally create this).
        mw.view_chess_log_charts_action = QAction("Chess Log", mw)
        mw.view_chess_log_charts_action.setEnabled(True)

        # Tab widget — 10 tabs in the real detail-panel order.
        tab_widget = QTabWidget()
        for title in [
            "Moves List", "PGN header tags", "Manual Analysis", "Opening Explorer",
            "Game Summary", "Player Stats", "Annotations", "AI Summary", "Notes", "Chess Log",
        ]:
            tab_widget.addTab(QWidget(), title)

        detail_panel = types.SimpleNamespace()
        detail_panel.tab_widget = tab_widget
        mw.detail_panel = detail_panel

        # Per-unit checkable actions for the Show/Hide submenu.
        mw._detail_panel_visibility_actions = {}
        for u in DETAIL_PANEL_VISIBILITY_UNITS:
            a = QAction(u.label, mw)
            a.setCheckable(True)
            a.setChecked(True)
            mw._detail_panel_visibility_actions[u.id] = a

        # Mutable visibility dict; tests mutate this to drive _apply_detail_panel_visibility.
        visibility_dict = {u.id: True for u in DETAIL_PANEL_VISIBILITY_UNITS}
        mw._get_detail_panel_visibility = lambda: visibility_dict

        # Bind the real MainWindow methods so they run against this QMainWindow instance.
        for method_name in (
            "_apply_unit_submenus",
            "_view_action_for_unit",
            "_switch_detail_tab",
            "_switch_detail_tab_by_id",
            "_find_detail_tab_index",
            "_menubar_action_for_title",
            "_apply_detail_panel_visibility",
            "_ensure_visible_detail_tab",
        ):
            setattr(mw, method_name, types.MethodType(getattr(MainWindow, method_name), mw))

        return mw, visibility_dict


    @requires_qt
    class TestChessLogShowHideWithRealMenu(unittest.TestCase):
        """Integration tests using the real setup_chess_log_menu and bound MainWindow methods."""

        def setUp(self):
            self.mw, self.vis = _make_mw_real_menus()

        def _hide(self):
            """Set chess_log_charts hidden and apply."""
            self.vis["chess_log_charts"] = False
            self.mw._apply_detail_panel_visibility()

        def _show(self):
            """Set chess_log_charts visible and apply."""
            self.vis["chess_log_charts"] = True
            self.mw._apply_detail_panel_visibility()

        # --- hide tests ---

        def test_tab_hidden_after_apply_hide(self):
            self._hide()
            self.assertFalse(self.mw.detail_panel.tab_widget.isTabVisible(9))

        def test_f10_disabled_after_apply_hide(self):
            self._hide()
            self.assertFalse(self.mw.view_chess_log_charts_action.isEnabled())

        def test_f10_switch_fails_when_hidden(self):
            self.mw.detail_panel.tab_widget.setCurrentIndex(0)
            self._hide()
            result = self.mw._switch_detail_tab_by_id("chess_log_charts")
            self.assertFalse(result)
            self.assertEqual(self.mw.detail_panel.tab_widget.currentIndex(), 0)

        def test_chess_log_menu_visible_when_hidden(self):
            self._hide()
            action = self.mw._menubar_action_for_title("Chess Log")
            self.assertIsNotNone(action)
            self.assertTrue(action.isVisible())

        def test_chess_log_logging_actions_visible_when_hidden(self):
            self._hide()
            self.assertTrue(self.mw.chess_log_settings_action.isVisible())
            self.assertTrue(self.mw.clear_chess_log_action.isVisible())
            self.assertTrue(self.mw.save_chess_log_action.isVisible())
            self.assertTrue(self.mw.show_all_chess_logs_action.isVisible())
            self.assertTrue(self.mw.highlight_chess_log_moves_action.isVisible())

        # --- show-again tests ---

        def test_tab_visible_after_apply_show(self):
            self._hide()
            self._show()
            self.assertTrue(self.mw.detail_panel.tab_widget.isTabVisible(9))

        def test_f10_enabled_after_apply_show(self):
            self._hide()
            self._show()
            self.assertTrue(self.mw.view_chess_log_charts_action.isEnabled())

        def test_f10_switches_to_chess_log_after_show(self):
            self._hide()
            self._show()
            self.mw.detail_panel.tab_widget.setCurrentIndex(0)
            result = self.mw._switch_detail_tab_by_id("chess_log_charts")
            self.assertTrue(result)
            self.assertEqual(self.mw.detail_panel.tab_widget.currentIndex(), 9)

        # --- real-menu submenu/separator tests ---

        def test_submenu_hidden_after_apply_hide(self):
            self._hide()
            self.assertFalse(self.mw.chess_log_charts_settings_menu.menuAction().isVisible())

        def test_separator_hidden_after_apply_hide(self):
            self._hide()
            self.assertFalse(self.mw._chess_log_charts_settings_separator.isVisible())

        def test_submenu_visible_after_apply_show(self):
            self._hide()
            self._show()
            self.assertTrue(self.mw.chess_log_charts_settings_menu.menuAction().isVisible())

        def test_separator_visible_after_apply_show(self):
            self._hide()
            self._show()
            self.assertTrue(self.mw._chess_log_charts_settings_separator.isVisible())


# ---------------------------------------------------------------------------
# Persistence test (no Qt needed — pure settings service)
# ---------------------------------------------------------------------------

class TestChessLogChartsPersistence(unittest.TestCase):
    """Hiding chess_log_charts is preserved through save/reload."""

    def _temp_settings_path(self):
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp())
        return tmp_dir, tmp_dir / "test_settings.json"

    def test_persist_hidden_across_reload(self):
        from app.services.user_settings_service import UserSettingsService

        tmp_dir, tmp_path = self._temp_settings_path()
        try:
            # Save "hidden" to the temp file (file does not exist yet — load() handles that).
            svc = UserSettingsService(settings_path=tmp_path)
            svc.load()
            svc.update_detail_panel_visibility("chess_log_charts", False)
            svc.save()

            # Reload from the same file.
            svc2 = UserSettingsService(settings_path=tmp_path)
            svc2.load()
            visibility = svc2.get_model().get_detail_panel_visibility()
            self.assertFalse(
                visibility.get("chess_log_charts", True),
                "chess_log_charts should still be hidden after reload",
            )
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_persist_visible_across_reload(self):
        from app.services.user_settings_service import UserSettingsService

        tmp_dir, tmp_path = self._temp_settings_path()
        try:
            svc = UserSettingsService(settings_path=tmp_path)
            svc.load()
            svc.update_detail_panel_visibility("chess_log_charts", False)
            svc.update_detail_panel_visibility("chess_log_charts", True)
            svc.save()

            svc2 = UserSettingsService(settings_path=tmp_path)
            svc2.load()
            visibility = svc2.get_model().get_detail_panel_visibility()
            self.assertTrue(
                visibility.get("chess_log_charts", False),
                "chess_log_charts should be visible after re-enabling and reload",
            )
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
