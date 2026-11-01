"""Tests for DetailChessLogChartsView.

Requires a working Qt platform (CI: QT_QPA_PLATFORM=offscreen).
Uses stub controller so no live data is needed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

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


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)

    from app.views.detail_chess_log_charts_view import DetailChessLogChartsView, _SOURCE_LABELS
    from app.services.chess_log_stats_service import (
        ChessLogCategoryBin,
        ChessLogPresetSeries,
    )
    from PyQt6.QtWidgets import QComboBox, QSpinBox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stub_controller(ai_configured: bool = False, models=None, timeout: int = 60) -> MagicMock:
    ctrl = MagicMock()
    ctrl.is_ai_configured.return_value = ai_configured
    ctrl.get_available_models.return_value = models or []
    ctrl.get_default_narrative_model.return_value = (models[0] if models else None)
    ctrl.get_narrative_timeout_seconds.return_value = timeout
    ctrl.get_narrative_model_override.return_value = None
    ctrl.get_last_narrative_result.return_value = ("", [], None)
    ctrl.get_last_shallow_result.return_value = (None, None, None)
    # Simulate signal attributes so connect() calls succeed
    for sig in (
        "charts_updated", "charts_unavailable", "charts_skipped", "charts_loading",
        "players_ready", "player_selection_cleared", "narrative_ready", "narrative_failed",
        "shallow_ready", "shallow_failed", "shallow_partial",
        "ai_configured_changed", "ai_model_changed", "results_invalidated",
    ):
        mock_signal = MagicMock()
        mock_signal.connect = MagicMock()
        mock_signal.disconnect = MagicMock()
        setattr(ctrl, sig, mock_signal)
    return ctrl


def _make_series(preset: str, cats: list[str], n_bins: int = 1) -> ChessLogPresetSeries:
    bins = [
        ChessLogCategoryBin(
            time_pct=50.0,
            total=len(cats),
            lab0="2025-01",
            lab1="2025-06",
            counts={c: 1 for c in cats},
        )
    ] * n_bins
    return ChessLogPresetSeries(preset=preset, categories=cats, bins=bins)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewLayout(unittest.TestCase):

    def test_has_single_outer_scroll_area(self):
        from PyQt6.QtWidgets import QScrollArea
        view = DetailChessLogChartsView(config={})
        self.assertTrue(hasattr(view, "_scroll_area"))
        self.assertIsInstance(view._scroll_area, QScrollArea)
        self.assertTrue(view._scroll_area.widgetResizable())

    def test_no_inner_chart_scroll_attribute(self):
        view = DetailChessLogChartsView(config={})
        self.assertFalse(hasattr(view, "_chart_scroll"))


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewPlaceholder(unittest.TestCase):

    def _make_view(self, ai=False) -> DetailChessLogChartsView:
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=ai))
        return view

    def test_placeholder_visible_on_startup(self):
        view = self._make_view()
        self.assertFalse(view._placeholder.isHidden())

    def test_charts_container_hidden_on_startup(self):
        view = self._make_view()
        self.assertTrue(view._charts_container.isHidden())

    def test_charts_unavailable_shows_placeholder(self):
        view = self._make_view()
        view._on_charts_unavailable("no_source")
        self.assertFalse(view._placeholder.isHidden())
        self.assertTrue(view._charts_container.isHidden())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewNarrativePanel(unittest.TestCase):

    def test_generate_button_disabled_when_unconfigured(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=False))
        self.assertFalse(view._generate_btn.isEnabled())

    def test_ai_hint_visible_when_unconfigured(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=False))
        self.assertFalse(view._ai_hint.isHidden())

    def test_generate_button_enabled_when_configured(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=True))
        self.assertTrue(view._generate_btn.isEnabled())

    def test_ai_hint_hidden_when_configured(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=True))
        self.assertFalse(view._ai_hint.isVisible())

    def test_ai_hint_is_rich_text(self):
        from PyQt6.QtCore import Qt
        view = DetailChessLogChartsView(config={})
        self.assertEqual(view._ai_hint.textFormat(), Qt.TextFormat.RichText)

    def test_ai_hint_contains_anchor_when_unconfigured(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=False))
        self.assertIn('<a href=', view._ai_hint.text())
        self.assertIn('ai-model-settings', view._ai_hint.text())

    def test_ai_hint_link_click_reaches_main_window(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=False))
        fake_window = MagicMock()
        with patch.object(view, "window", return_value=fake_window):
            view._on_ai_hint_link_clicked("ai-model-settings")
        fake_window._show_ai_model_settings.assert_called_once()

    def test_narrative_ready_sets_text(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=True))
        view._on_narrative_ready("Great patterns found.", [], None)
        self.assertIn("Great patterns", view._narrative_edit.toPlainText())

    def test_narrative_ready_with_flags_shows_flagged_box(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=True))
        view._on_narrative_ready("Narrative.", ["shallow note 1"], None)
        self.assertFalse(view._flagged_box.isHidden())

    def test_narrative_ready_no_flags_hides_flagged_box(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=True))
        view._on_narrative_ready("Narrative.", [], None)
        self.assertTrue(view._flagged_box.isHidden())

    def test_narrative_failed_sets_error_text(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=True))
        view._on_narrative_failed("Connection refused")
        self.assertIn("Connection refused", view._narrative_edit.toPlainText())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewCharts(unittest.TestCase):

    def test_charts_updated_creates_one_widget_per_preset(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        data = {
            "CLAMP": _make_series("CLAMP", ["C", "L"]),
            "CCT": _make_series("CCT", ["Checks"]),
        }
        view._on_charts_updated(data)
        self.assertEqual(len(view._chart_widgets), 2)

    def test_charts_updated_hides_placeholder(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        data = {"CLAMP": _make_series("CLAMP", ["C"])}
        view._on_charts_updated(data)
        self.assertTrue(view._placeholder.isHidden())
        self.assertFalse(view._charts_container.isHidden())

    def test_charts_updated_with_empty_dict_shows_placeholder(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_charts_updated({})
        self.assertFalse(view._placeholder.isHidden())

    def test_second_update_replaces_first(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_charts_updated({"CLAMP": _make_series("CLAMP", ["C"])})
        view._on_charts_updated({"CCT": _make_series("CCT", ["Checks"])})
        self.assertEqual(len(view._chart_widgets), 1)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewClearOnLoading(unittest.TestCase):

    def _make_view(self) -> DetailChessLogChartsView:
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        return view

    def test_on_charts_loading_clears_chart_widgets(self):
        view = self._make_view()
        view._on_charts_updated({"CLAMP": _make_series("CLAMP", ["C"])})
        self.assertEqual(len(view._chart_widgets), 1)
        view._on_charts_loading()
        self.assertEqual(len(view._chart_widgets), 0)

    def test_on_charts_loading_hides_placeholder_and_container(self):
        view = self._make_view()
        view._on_charts_loading()
        self.assertFalse(view._placeholder.isVisible())
        self.assertFalse(view._charts_container.isVisible())

    def test_no_loading_label_attribute(self):
        view = self._make_view()
        self.assertFalse(hasattr(view, "_loading_label"))


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewFlaggedLabel(unittest.TestCase):

    def test_flagged_label_is_selectable(self):
        from PyQt6.QtCore import Qt
        view = DetailChessLogChartsView(config={})
        flags = view._flagged_label.textInteractionFlags()
        self.assertTrue(flags & Qt.TextInteractionFlag.TextSelectableByMouse)
        self.assertTrue(flags & Qt.TextInteractionFlag.TextSelectableByKeyboard)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewSelector(unittest.TestCase):

    def test_combo_boxes_use_triangle_only_click_mechanism(self):
        """Both combos must be editable with a read-only QLineEdit.

        This is the same mechanism Player Stats uses: setEditable(True) causes Qt
        to split the widget into a text area (QLineEdit) and a triangle button.
        setReadOnly(True) on the embedded QLineEdit means clicking the text area
        does nothing — only the triangle button opens the dropdown.
        """
        view = DetailChessLogChartsView(config={})
        for attr in ("_source_combo", "_player_combo"):
            combo = getattr(view, attr)
            self.assertTrue(combo.isEditable(), f"{attr} must be editable (triangle-only)")
            le = combo.lineEdit()
            self.assertIsNotNone(le, f"{attr} must have an embedded QLineEdit")
            self.assertTrue(le.isReadOnly(), f"{attr} QLineEdit must be read-only")

    def test_source_combo_has_five_options(self):
        view = DetailChessLogChartsView(config={})
        self.assertEqual(view._source_combo.count(), len(_SOURCE_LABELS))

    def test_player_combo_starts_empty_and_unselected(self):
        view = DetailChessLogChartsView(config={})
        self.assertEqual(view._player_combo.count(), 0)
        self.assertEqual(view._player_combo.currentIndex(), -1)

    def test_players_ready_populates_player_combo(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([("Alice", 5), ("Bob", 3)])
        self.assertEqual(view._player_combo.count(), 2)

    def test_players_ready_with_no_prior_selection_stays_unselected(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([("Alice", 5), ("Bob", 3)])
        self.assertEqual(view._player_combo.currentIndex(), -1)

    def test_players_ready_preserves_current_selection_when_made(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([("Alice", 5), ("Bob", 3)])
        view._player_combo.setCurrentIndex(0)  # Alice selected; itemData = "Alice"
        view._on_players_ready([("Alice", 5), ("Bob", 3), ("Carlos", 2)])
        # Raw name preserved via itemData, even though display text includes count suffix
        self.assertEqual(view._player_combo.itemData(view._player_combo.currentIndex()), "Alice")

    def test_display_text_includes_tagged_count(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([("Alice", 7)])
        self.assertIn("7 logged", view._player_combo.itemText(0))

    def test_item_data_is_raw_name(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([("Alice", 7)])
        self.assertEqual(view._player_combo.itemData(0), "Alice")

    def test_reset_player_selection_sets_index_minus_one(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([("Alice", 5), ("Bob", 3)])
        view._player_combo.setCurrentIndex(0)
        view._reset_player_selection()
        self.assertEqual(view._player_combo.currentIndex(), -1)

    def test_reset_player_selection_clears_last_shallow_keys_and_narrative(self):
        """DB switch and player-change both call _reset_player_selection;
        it must clear _last_shallow_keys and _last_narrative so stale data
        from the previous database is never shown against the new one."""
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        # Simulate having stale shallow-key results from a previous library
        view._last_shallow_keys = frozenset([(5, "0.0", "CLAMP")])
        view._last_narrative = "Prior narrative text"
        view._reset_player_selection()
        self.assertIsNone(view._last_shallow_keys)
        self.assertEqual(view._last_narrative, "")

    def test_players_ready_with_empty_list_shows_no_players_placeholder(self):
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        view._on_players_ready([])
        self.assertEqual(view._player_combo.count(), 0)
        self.assertIn("No players", view._placeholder.text())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewNarrativeControls(unittest.TestCase):
    """Tests for the model/timeout/tokens/checkbox controls added in Items 4 and 6."""

    def _make_view(self, ai: bool = False, models=None, timeout: int = 60) -> "DetailChessLogChartsView":
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller(ai_configured=ai, models=models, timeout=timeout))
        return view

    def test_no_flag_btn_attribute(self):
        view = self._make_view()
        self.assertFalse(hasattr(view, "_flag_btn"))

    # --- Check Logs button ---

    def test_show_shallow_btn_exists(self):
        from PyQt6.QtWidgets import QPushButton
        view = self._make_view()
        self.assertTrue(hasattr(view, "_show_shallow_btn"))
        self.assertIsInstance(view._show_shallow_btn, QPushButton)

    def test_show_shallow_btn_text_is_check_logs(self):
        view = self._make_view()
        self.assertEqual(view._show_shallow_btn.text(), "Check Logs")

    def test_show_shallow_btn_disabled_when_unconfigured(self):
        view = self._make_view(ai=False)
        self.assertFalse(view._show_shallow_btn.isEnabled())

    def test_show_shallow_btn_disabled_when_configured_but_no_source_or_player(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        # source combo starts at index 0 ("None"), no player selected
        self.assertFalse(view._show_shallow_btn.isEnabled())

    def test_show_shallow_btn_disabled_when_source_selected_but_no_player(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._source_combo.setCurrentIndex(1)  # "Active Database"
        self.assertFalse(view._show_shallow_btn.isEnabled())

    def test_show_shallow_btn_disabled_when_player_selected_but_no_source(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._player_combo.addItem("Alice (3 tagged)", "Alice")
        view._player_combo.setCurrentIndex(0)
        # source still at index 0 ("None")
        self.assertFalse(view._show_shallow_btn.isEnabled())

    def test_show_shallow_btn_enabled_when_source_and_player_selected(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._source_combo.setCurrentIndex(1)  # "Active Database"
        view._player_combo.addItem("Alice (3 tagged)", "Alice")
        view._player_combo.setCurrentIndex(0)
        self.assertTrue(view._show_shallow_btn.isEnabled())

    # --- Shallow hint label ---

    def test_shallow_hint_exists(self):
        view = self._make_view()
        self.assertTrue(hasattr(view, "_shallow_hint"))

    def test_shallow_hint_text_when_no_ai(self):
        view = self._make_view(ai=False)
        self.assertIn("AI provider", view._shallow_hint.text())

    def test_shallow_hint_text_when_ai_but_no_source(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        # source at index 0 ("None")
        self.assertIn("Data Source", view._shallow_hint.text())

    def test_shallow_hint_text_when_source_but_no_player(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._source_combo.setCurrentIndex(1)
        self.assertIn("player", view._shallow_hint.text())

    def test_shallow_hint_cleared_when_all_ready(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._source_combo.setCurrentIndex(1)
        view._player_combo.addItem("Alice (3 tagged)", "Alice")
        view._player_combo.setCurrentIndex(0)
        self.assertEqual("", view._shallow_hint.text())

    # --- Model combo ---

    def test_model_combo_exists(self):
        view = self._make_view()
        self.assertTrue(hasattr(view, "_model_combo"))
        self.assertIsInstance(view._model_combo, QComboBox)

    def test_model_combo_disabled_when_unconfigured(self):
        view = self._make_view(ai=False)
        self.assertFalse(view._model_combo.isEnabled())

    def test_model_combo_enabled_when_configured(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        self.assertTrue(view._model_combo.isEnabled())

    def test_model_combo_populated_from_controller(self):
        view = self._make_view(ai=True, models=["gpt-4o", "gpt-4-turbo"])
        self.assertEqual(view._model_combo.count(), 2)
        self.assertEqual(view._model_combo.itemText(0), "gpt-4o")
        self.assertEqual(view._model_combo.itemText(1), "gpt-4-turbo")

    def test_model_combo_selects_default_model(self):
        # Build the controller with gpt-4o as the default before constructing the view
        # so the initial _refresh_ai_state call selects it (no prior selection to preserve).
        ctrl = _make_stub_controller(ai_configured=True, models=["gpt-3.5-turbo", "gpt-4o"])
        ctrl.get_default_narrative_model.return_value = "gpt-4o"
        view = DetailChessLogChartsView(config={})
        view.set_controller(ctrl)
        self.assertEqual(view._model_combo.currentText(), "gpt-4o")

    def test_model_combo_change_calls_controller(self):
        view = self._make_view(ai=True, models=["gpt-4o", "gpt-4-turbo"])
        view._controller.set_narrative_model_override = MagicMock()
        view._model_combo.setCurrentIndex(1)
        view._controller.set_narrative_model_override.assert_called_with("gpt-4-turbo")

    def test_refresh_ai_state_prefers_narrative_override_over_default(self):
        """When the current combo text is absent from the new model list (e.g. after a
        DB switch that resets the combo) and the controller has a persisted override,
        _refresh_ai_state must select the override rather than the default model."""
        ctrl = _make_stub_controller(
            ai_configured=True,
            models=["claude-opus-4-7", "claude-sonnet-4-6"],
        )
        ctrl.get_default_narrative_model.return_value = "claude-sonnet-4-6"
        ctrl.get_narrative_model_override.return_value = "claude-opus-4-7"
        view = DetailChessLogChartsView(config={})
        # Clear the combo so currentText() returns "" (simulates a freshly cleared combo)
        view._model_combo.clear()
        view.set_controller(ctrl)
        self.assertEqual(view._model_combo.currentText(), "claude-opus-4-7")

    def test_refresh_ai_state_falls_back_to_default_when_override_absent(self):
        """When the override model is not in the available list, _refresh_ai_state
        must fall back to the default model rather than silently landing on index 0."""
        ctrl = _make_stub_controller(
            ai_configured=True,
            models=["claude-sonnet-4-6", "claude-haiku-4-5"],
        )
        ctrl.get_default_narrative_model.return_value = "claude-sonnet-4-6"
        ctrl.get_narrative_model_override.return_value = "claude-opus-4-7"  # not in list
        view = DetailChessLogChartsView(config={})
        view._model_combo.clear()
        view.set_controller(ctrl)
        self.assertEqual(view._model_combo.currentText(), "claude-sonnet-4-6")

    # --- Timeout spinner (Item 4) ---

    def test_timeout_spin_exists(self):
        view = self._make_view()
        self.assertTrue(hasattr(view, "_timeout_spin"))
        self.assertIsInstance(view._timeout_spin, QSpinBox)

    def test_timeout_spin_disabled_when_unconfigured(self):
        view = self._make_view(ai=False)
        self.assertFalse(view._timeout_spin.isEnabled())

    def test_timeout_spin_initialized_from_controller(self):
        view = self._make_view(ai=True, models=["gpt-4o"], timeout=120)
        self.assertEqual(view._timeout_spin.value(), 120)

    def test_timeout_spin_change_calls_controller(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._controller.set_narrative_timeout_seconds = MagicMock()
        view._timeout_spin.setValue(90)
        view._controller.set_narrative_timeout_seconds.assert_called_with(90)

    def test_timeout_spin_range(self):
        view = self._make_view()
        self.assertEqual(view._timeout_spin.minimum(), 10)
        self.assertEqual(view._timeout_spin.maximum(), 600)

    # --- Tokens spinner (Item 4) ---

    def test_tokens_spin_exists(self):
        view = self._make_view()
        self.assertTrue(hasattr(view, "_tokens_spin"))
        self.assertIsInstance(view._tokens_spin, QSpinBox)

    def test_tokens_spin_disabled_when_unconfigured(self):
        view = self._make_view(ai=False)
        self.assertFalse(view._tokens_spin.isEnabled())

    def test_tokens_spin_default_value(self):
        view = self._make_view()
        self.assertEqual(view._tokens_spin.value(), 12000)

    def test_tokens_spin_range(self):
        view = self._make_view()
        self.assertEqual(view._tokens_spin.minimum(), 256)
        self.assertEqual(view._tokens_spin.maximum(), 99999)

    def test_tokens_spin_change_calls_controller(self):
        view = self._make_view(ai=True, models=["gpt-4o"])
        view._controller.set_narrative_token_limit = MagicMock()
        view._tokens_spin.setValue(4000)
        view._controller.set_narrative_token_limit.assert_called_with(4000)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewTheme(unittest.TestCase):
    """Verify that color config flows through to the widget stylesheet and spinner."""

    def _make_config(self, bg, text, input_bg, border, hint, spinner) -> dict:
        return {
            "ui": {
                "panels": {
                    "detail": {
                        "chess_log_charts": {
                            "colors": {
                                "background": bg,
                                "text": text,
                                "input_background": input_bg,
                                "border": border,
                                "hint_text": hint,
                                "spinner_color": spinner,
                            }
                        }
                    }
                }
            }
        }

    def test_background_color_applied_to_stylesheet(self):
        cfg = self._make_config(
            bg=[1, 2, 3], text=[200, 200, 200], input_bg=[50, 50, 50],
            border=[80, 80, 80], hint=[120, 120, 120], spinner=[100, 100, 100],
        )
        view = DetailChessLogChartsView(config=cfg)
        ss = view.styleSheet()
        self.assertIn("rgb(1,2,3)", ss)

    def test_hint_text_color_applied_to_stylesheet(self):
        cfg = self._make_config(
            bg=[30, 30, 35], text=[200, 200, 200], input_bg=[50, 50, 50],
            border=[80, 80, 80], hint=[9, 8, 7], spinner=[100, 100, 100],
        )
        view = DetailChessLogChartsView(config=cfg)
        ss = view._ai_hint.styleSheet()
        self.assertIn("rgb(9,8,7)", ss)

    def test_spinner_color_from_config(self):
        from PyQt6.QtGui import QColor
        cfg = self._make_config(
            bg=[30, 30, 35], text=[200, 200, 200], input_bg=[50, 50, 50],
            border=[80, 80, 80], hint=[120, 120, 120], spinner=[11, 22, 33],
        )
        view = DetailChessLogChartsView(config=cfg)
        expected = QColor(11, 22, 33)
        self.assertEqual(view._shallow_spinner._color, expected)

    def test_default_fallback_spinner_color(self):
        from PyQt6.QtGui import QColor
        view = DetailChessLogChartsView(config={})
        self.assertEqual(view._shallow_spinner._color, QColor(180, 180, 200))


@unittest.skipUnless(_QT_AVAILABLE, "Qt platform plugin unavailable")
class TestNarrativeSanitizationOnScreen(unittest.TestCase):
    """sanitize_narrative_markdown is applied before setMarkdown so the
    on-screen QTextEdit receives clean text, not just the PDF path."""

    def _make_view(self) -> "DetailChessLogChartsView":
        return DetailChessLogChartsView(config={})

    def test_thematic_break_sanitized_before_set_markdown(self):
        from unittest.mock import patch
        from app.services.chess_log_narrative_service import sanitize_narrative_markdown

        view = self._make_view()
        narrative = "## Section\n\n---\n\nSome prose."
        calls: list[str] = []

        original_set_markdown = view._narrative_edit.setMarkdown

        def _capture(text: str) -> None:
            calls.append(text)
            original_set_markdown(text)

        view._narrative_edit.setMarkdown = _capture
        view._on_narrative_ready(narrative, [], None)

        self.assertEqual(len(calls), 1)
        self.assertNotIn("---", calls[0].splitlines(), "bare --- should be stripped before setMarkdown")

    def test_empty_cell_row_sanitized_before_set_markdown(self):
        table = (
            "| Skill | Observed Issue | Strategic Impact |\n"
            "| --- | --- | --- |\n"
            "| Calculation | Missed tactic |  |\n"
            "| King Safety | Castle delay | King exposed |\n"
        )
        narrative = f"## Tactical Breakdown\n\n{table}"
        view = self._make_view()
        calls: list[str] = []

        original_set_markdown = view._narrative_edit.setMarkdown

        def _capture(text: str) -> None:
            calls.append(text)
            original_set_markdown(text)

        view._narrative_edit.setMarkdown = _capture
        view._on_narrative_ready(narrative, [], None)

        self.assertEqual(len(calls), 1)
        self.assertNotIn("Missed tactic", calls[0], "row with empty Strategic Impact should be stripped")
        self.assertIn("King exposed", calls[0], "fully-populated rows should be preserved")


# ---------------------------------------------------------------------------
# Test 19: PDF export path excludes orphan entries
# ---------------------------------------------------------------------------
# These imports are unconditional — ChessLogController and friends are pure
# Python and do not require a Qt application to instantiate.

from app.controllers.chess_log_controller import ChessLogController
from app.models.database_model import GameData as _GameData
from app.services.chess_log_storage_service import ChessLogStorageService as _CLS


def _make_ctrl_for_pdf_test(game) -> ChessLogController:
    """Return a minimal ChessLogController with *game* loaded in the multi-cache
    path (NOT as the active game), mimicking what the view's PDF export sees."""
    from unittest.mock import MagicMock
    gm = MagicMock()
    gm.active_game = None          # game is inactive — forces multi-cache path
    gm.get_active_path.return_value = ()
    gm.active_game_changed = MagicMock()
    gm.active_game_changed.connect = MagicMock()
    gm.metadata_updated = MagicMock()
    gm.metadata_updated.emit = MagicMock()
    gc = MagicMock()
    gc.get_game_model.return_value = gm
    return ChessLogController({}, gc)


class TestPdfExportOrphanExclusion(unittest.TestCase):
    """Test 19: get_tags_for_game (the call the PDF export loop makes) must
    exclude orphan path_keys so only resolvable rows reach the snapshot list."""

    def test_pdf_export_path_excludes_orphan_entries(self):
        """PDF export iterates chess_log_ctrl.get_tags_for_game(game).
        With one resolvable and one orphan entry, only the resolvable path_key
        must appear in the returned dict, so exactly one snapshot row is built."""
        _PGN = (
            '[Event "Test"]\n[Site "?"]\n[Date "2025.06.01"]\n'
            '[Round "?"]\n[White "Alice"]\n[Black "Bob"]\n[Result "*"]\n\n'
            '1. e4 e5 2. Nf3 *\n'
        )
        game = _GameData(game_number=1, pgn=_PGN, white="Alice", black="Bob", date="2025.06.01")
        _CLS.store_tags(game, {
            "0":     [_CLS.make_entry("CLAMP", "C", "real note")],
            "99999": [_CLS.make_entry("CLAMP", "M", "ghost note")],   # orphan
        })

        ctrl = _make_ctrl_for_pdf_test(game)

        # Call the exact method the view's PDF export uses (inactive game path).
        tags = ctrl.get_tags_for_game(game)

        self.assertIn("0", tags,      "resolvable path_key must appear in result")
        self.assertNotIn("99999", tags, "orphan path_key must be excluded")

        # Simulate the shallow_rows loop from _export_pdf_report (lines 831-851):
        # only entries whose key is in _last_shallow_keys contribute a row.
        _last_shallow_keys = {
            (game.game_number, "0",     "CLAMP"),
            (game.game_number, "99999", "CLAMP"),
        }
        rows_built = 0
        for path_key, all_entries in tags.items():
            if not all_entries:
                continue
            by_preset: dict = {}
            for e in all_entries:
                by_preset.setdefault(e.get("preset", ""), []).append(e)
            for preset in by_preset:
                k = (game.game_number, path_key, preset)
                if k in _last_shallow_keys:
                    rows_built += 1

        self.assertEqual(rows_built, 1, "exactly one snapshot row must be built; orphan must not add a row")


@unittest.skipUnless(_QT_AVAILABLE, "Qt unavailable")
class TestExportPdfReportNarrativeMetadata(unittest.TestCase):
    """15b: _export_pdf_report passes narrative metadata from get_last_narrative_metadata()
    to export_charts_report; does NOT pass shallow model label as model_label."""

    def _make_view(self) -> "DetailChessLogChartsView":
        return DetailChessLogChartsView(config={})

    def test_export_pdf_report_passes_narrative_metadata_when_narrative_present(self):
        """When narrative is present, get_last_narrative_metadata() is called and
        its values reach export_charts_report as model_label/generated_at/counts."""
        from unittest.mock import patch, call
        from app.services.chess_log_pdf_service import ChessLogPDFService

        view = self._make_view()
        ctrl = _make_stub_controller(ai_configured=True, models=["m1"])
        ctrl.get_last_narrative_result.return_value = ("Some narrative", [], None)
        ctrl.get_last_shallow_result.return_value = (None, None, None)
        ctrl.get_last_narrative_metadata.return_value = (
            "2026-06-01 12:00",      # generated_at
            "Anthropic claude-x",    # model_label
            10, 7, 18, 14, False,    # n, g, m, s, has_3x3
        )
        ctrl.get_current_source_filenames.return_value = ["DB.pgn"]
        view.set_controller(ctrl)
        # Manually set last narrative so the method sees it
        view._last_narrative = "Some narrative"

        captured: dict = {}

        def _fake_export(_svc, path, player_name, source_label, chart_pixmaps, narrative_text,
                         shallow_rows, *, model_label="", generated_at="",
                         n_games=0, g_games=0, m_moments=0, s_flagged=0, has_3x3=False):
            captured.update(
                model_label=model_label, generated_at=generated_at,
                n_games=n_games, g_games=g_games, m_moments=m_moments,
                s_flagged=s_flagged, has_3x3=has_3x3,
            )
            return True

        with patch.object(ChessLogPDFService, "export_charts_report", _fake_export), \
             patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                   return_value=("/tmp/test.pdf", "PDF Files (*.pdf)")):
            view._export_pdf_report()

        self.assertEqual(captured.get("generated_at"), "2026-06-01 12:00")
        self.assertEqual(captured.get("model_label"), "Anthropic claude-x")
        self.assertEqual(captured.get("n_games"), 10)
        self.assertEqual(captured.get("g_games"), 7)
        self.assertEqual(captured.get("m_moments"), 18)
        self.assertEqual(captured.get("s_flagged"), 14)
        self.assertFalse(captured.get("has_3x3"))

    def test_export_pdf_report_passes_empty_metadata_when_no_narrative(self):
        """When no narrative, counts/generated_at/model_label are all empty/zero."""
        from unittest.mock import patch
        from app.services.chess_log_pdf_service import ChessLogPDFService

        view = self._make_view()
        ctrl = _make_stub_controller(ai_configured=True, models=["m1"])
        ctrl.get_last_narrative_result.return_value = ("", [], None)
        ctrl.get_last_shallow_result.return_value = (None, None, None)
        ctrl.get_current_source_filenames.return_value = []
        view.set_controller(ctrl)
        view._last_narrative = ""

        captured: dict = {}

        def _fake_export(_svc, path, player_name, source_label, chart_pixmaps, narrative_text,
                         shallow_rows, *, model_label="", generated_at="",
                         n_games=0, g_games=0, m_moments=0, s_flagged=0, has_3x3=False):
            captured.update(
                model_label=model_label, generated_at=generated_at,
                n_games=n_games, g_games=g_games, m_moments=m_moments,
                s_flagged=s_flagged, has_3x3=has_3x3,
            )
            return True

        with patch.object(ChessLogPDFService, "export_charts_report", _fake_export), \
             patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                   return_value=("/tmp/test.pdf", "PDF Files (*.pdf)")):
            view._export_pdf_report()

        self.assertEqual(captured.get("model_label"), "")
        self.assertEqual(captured.get("generated_at"), "")
        self.assertEqual(captured.get("n_games"), 0)
        self.assertEqual(captured.get("g_games"), 0)
        self.assertEqual(captured.get("m_moments"), 0)
        self.assertEqual(captured.get("s_flagged"), 0)
        self.assertFalse(captured.get("has_3x3"))
        ctrl.get_last_narrative_metadata.assert_not_called()


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewSkipNote(unittest.TestCase):
    """_skip_note shown after charts_updated(n>0); hidden otherwise."""

    def _make_view(self) -> "DetailChessLogChartsView":
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        return view

    def test_skip_note_hidden_on_startup(self):
        view = self._make_view()
        self.assertTrue(view._skip_note.isHidden())

    def test_skip_note_shown_when_n_positive(self):
        view = self._make_view()
        view._on_charts_skipped(4)
        self.assertFalse(view._skip_note.isHidden())

    def test_skip_note_hidden_when_n_zero(self):
        view = self._make_view()
        view._on_charts_skipped(4)
        view._on_charts_skipped(0)
        self.assertTrue(view._skip_note.isHidden())

    def test_skip_note_text_singular(self):
        view = self._make_view()
        view._on_charts_skipped(1)
        self.assertEqual(view._skip_note.text(), "1 game not charted: no date.")

    def test_skip_note_text_plural(self):
        view = self._make_view()
        view._on_charts_skipped(4)
        self.assertEqual(view._skip_note.text(), "4 games not charted: no date.")

    def test_skip_note_cleared_by_clear_charts(self):
        view = self._make_view()
        view._on_charts_skipped(3)
        view._clear_charts()
        self.assertTrue(view._skip_note.isHidden())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestDetailChessLogChartsViewUndatedMessages(unittest.TestCase):
    """_on_charts_unavailable handles no_dated_clamp_cct:N:B reason strings."""

    def _make_view(self) -> "DetailChessLogChartsView":
        view = DetailChessLogChartsView(config={})
        view.set_controller(_make_stub_controller())
        return view

    def test_no_dated_clamp_cct_shows_placeholder(self):
        view = self._make_view()
        view._on_charts_unavailable("no_dated_clamp_cct:4:0")
        self.assertFalse(view._placeholder.isHidden())
        self.assertTrue(view._charts_container.isHidden())

    def test_no_dated_clamp_cct_singular_exact_string(self):
        view = self._make_view()
        view._on_charts_unavailable("no_dated_clamp_cct:1:0")
        self.assertEqual(
            view._placeholder.text(),
            "No chart data for this selection.\n"
            "1 game with CLAMP/CCT moments has no date, and charts need dated games.",
        )

    def test_no_dated_clamp_cct_plural_exact_string(self):
        view = self._make_view()
        view._on_charts_unavailable("no_dated_clamp_cct:4:0")
        self.assertEqual(
            view._placeholder.text(),
            "No chart data for this selection.\n"
            "4 games with CLAMP/CCT moments have no date, and charts need dated games.",
        )

    def test_no_dated_clamp_cct_with_3x3_exact_string(self):
        view = self._make_view()
        view._on_charts_unavailable("no_dated_clamp_cct:4:1")
        self.assertEqual(
            view._placeholder.text(),
            "No chart data for this selection.\n"
            "4 games with CLAMP/CCT moments have no date, and charts need dated games.\n"
            "3x3 moments are not shown in charts — use Generate Narrative Summary below.",
        )

    def test_no_dated_clamp_cct_singular_with_3x3_exact_string(self):
        view = self._make_view()
        view._on_charts_unavailable("no_dated_clamp_cct:1:1")
        self.assertEqual(
            view._placeholder.text(),
            "No chart data for this selection.\n"
            "1 game with CLAMP/CCT moments has no date, and charts need dated games.\n"
            "3x3 moments are not shown in charts — use Generate Narrative Summary below.",
        )

    def test_no_dated_clamp_cct_skip_note_hidden(self):
        view = self._make_view()
        view._on_charts_unavailable("no_dated_clamp_cct:4:0")
        self.assertTrue(view._skip_note.isHidden())


if __name__ == "__main__":
    unittest.main()
