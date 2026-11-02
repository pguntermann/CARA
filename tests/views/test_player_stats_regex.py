"""Player Stats name pattern: checkbox, validation, and editor parenting."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLabel

from app.config.config_loader import ConfigLoader
from app.controllers.player_stats_controller import PlayerStatsController
from app.services.regex_editor_service import RegexEditorValues
from app.views.detail_player_stats_view import DetailPlayerStatsView
from app.views.widgets.regex_syntax import regex_token_colors


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Panel(QObject):
    active_database_changed = pyqtSignal()
    database_added = pyqtSignal()
    database_removed = pyqtSignal()

    def get_all_database_models(self):
        return []


class _DatabaseController:
    def __init__(self) -> None:
        self._panel = _Panel()

    def get_active_database(self):
        return None

    def get_panel_model(self):
        return self._panel


class _Selection:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.player = None
        self.regex = False

    def set_player_selection(self, name, *, name_is_regex: bool = False) -> None:
        self.calls.append((name, name_is_regex))
        self.player = name
        self.regex = bool(name_is_regex) and name is not None

    def get_current_player(self):
        return self.player

    def player_selection_is_regex(self) -> bool:
        return self.regex

    def get_source_selection(self) -> int:
        return 1


class TestPlayerStatsRegexSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt = _app()
        cls.config = ConfigLoader().load()

    def test_invalid_pattern_is_not_scheduled(self) -> None:
        controller = PlayerStatsController(self.config, _DatabaseController())
        scheduled: list[bool] = []
        controller._schedule_stats_recalculation = lambda *args, **kwargs: scheduled.append(True)
        controller.set_player_selection("[", name_is_regex=True)
        self.assertIsNone(controller.get_current_player())
        self.assertFalse(controller.player_selection_is_regex())
        self.assertEqual(scheduled, [])
        controller.set_player_selection(r"Carlsen", name_is_regex=True)
        self.assertEqual(controller.get_current_player(), "Carlsen")
        self.assertTrue(controller.player_selection_is_regex())
        self.assertEqual(scheduled, [True])
        controller.set_player_selection("Carlsen")
        self.assertFalse(controller.player_selection_is_regex())

    def test_checkbox_applies_on_enter_and_keeps_regex_across_dropdown_refresh(self) -> None:
        view = DetailPlayerStatsView(self.config)
        selection = _Selection()
        view._stats_controller = selection
        view.source_combo.blockSignals(True)
        view.source_combo.setCurrentIndex(1)
        view.source_combo.blockSignals(False)
        view.show()
        _app().processEvents()

        self.assertFalse(view.player_regex_check.isChecked())
        self.assertTrue(view.player_combo.isVisible())
        self.assertFalse(view.player_regex_input.isVisible())

        view.player_regex_check.setChecked(True)
        _app().processEvents()
        self.assertFalse(view.player_combo.isVisible())
        self.assertTrue(view.player_regex_input.isVisible())
        self.assertTrue(view._player_stats_activity_label.isVisible())
        self.assertEqual(view._player_stats_activity_label.text(), "Enter a regular expression.")
        self.assertEqual(selection.calls[-1], (None, False))

        view.player_regex_input.setText(r"\d+")
        view.player_regex_input.returnPressed.emit()
        self.assertEqual(selection.calls[-1], (r"\d+", True))
        _app().processEvents()
        colors = regex_token_colors(self.config)
        painted = view.player_regex_input.token_color_at(0)
        assert painted is not None
        self.assertEqual(
            (painted.red(), painted.green(), painted.blue()),
            (colors["escape"].red(), colors["escape"].green(), colors["escape"].blue()),
        )

        selection.player = r"Car.*"
        selection.regex = True
        view._on_players_ready([])
        self.assertEqual(selection.player, r"Car.*")
        view._on_players_ready([("Someone", 4, 3)])
        self.assertEqual(selection.player, r"Car.*")
        self.assertEqual(view.player_combo.currentIndex(), -1)

        view.player_regex_check.setChecked(False)
        self.assertEqual(selection.calls[-1], (None, False))
        self.assertTrue(view.player_combo.isVisible())
        view.close()

    def test_no_match_removes_the_previous_statistics(self) -> None:
        view = DetailPlayerStatsView(self.config)
        leftover = QLabel("previous statistics", view)
        view.content_layout.addWidget(leftover)
        view.current_stats = object()

        view._handle_stats_unavailable("player_not_found")

        shown = []
        for i in range(view.content_layout.count()):
            item = view.content_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is not None and hasattr(widget, "text"):
                shown.append(widget.text())
        self.assertNotIn("previous statistics", shown)
        self.assertIsNone(view.current_stats)
        self.assertFalse(view.disabled_placeholder.isHidden())
        self.assertEqual(
            view.disabled_placeholder.text(),
            "Player not found in selected database(s)",
        )
        view.close()

    def test_theme_rebuild_keeps_regex_checkable_when_a_source_is_selected(self) -> None:
        controller = PlayerStatsController(self.config, _DatabaseController())
        controller._source_selection = 1
        view = DetailPlayerStatsView(self.config, stats_controller=controller)
        self.assertEqual(view.source_combo.currentIndex(), 1)
        self.assertTrue(view.player_regex_check.isEnabled())
        self.assertTrue(view.player_regex_input.isEnabled())
        controller._source_selection = 0
        view.close()

    def test_regex_stays_inactive_while_no_data_source_is_selected(self) -> None:
        view = DetailPlayerStatsView(self.config)
        self.assertFalse(view.player_regex_check.isEnabled())
        self.assertFalse(view.player_regex_input.isEnabled())
        self.assertEqual(view.disabled_placeholder.text(), view.placeholder_text_no_source)

        view.player_regex_check.setChecked(True)
        view.player_regex_input.setText(r"^Carlsen,")
        view.player_regex_input.returnPressed.emit()
        self.assertEqual(view.disabled_placeholder.text(), view.placeholder_text_no_source)
        self.assertFalse(view._player_stats_activity_label.isVisible())

        view.source_combo.setCurrentIndex(1)
        view._on_source_selection_changed(1)
        self.assertTrue(view.player_regex_check.isEnabled())
        self.assertTrue(view.player_regex_input.isEnabled())

        view.source_combo.setCurrentIndex(0)
        view._on_source_selection_changed(0)
        self.assertFalse(view.player_regex_check.isEnabled())
        self.assertFalse(view.player_regex_input.isEnabled())
        self.assertEqual(view.disabled_placeholder.text(), view.placeholder_text_no_source)
        view.close()

    def test_editor_is_parented_to_the_window(self) -> None:
        view = DetailPlayerStatsView(self.config)
        view.source_combo.blockSignals(True)
        view.source_combo.setCurrentIndex(1)
        view.source_combo.blockSignals(False)
        view._sync_player_regex_enabled()
        view.player_regex_check.setChecked(True)
        captured: dict = {}

        def _edit(*args, **kwargs):
            captured["parent"] = kwargs.get("parent")
            return RegexEditorValues(pattern="Kasparov", replacement="")

        with patch("app.views.detail_player_stats_view.edit_regex", _edit):
            view._open_player_regex_editor()
        self.assertIs(captured["parent"], view.window())
        self.assertEqual(view.player_regex_input.text(), "Kasparov")
        view.close()
