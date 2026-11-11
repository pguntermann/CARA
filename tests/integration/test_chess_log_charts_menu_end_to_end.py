"""End-to-end wiring test: Chess Log Charts menu → controller live-field update.

Simulates the production signal chain:
  menu._on_*_selected(value)
    → UserSettingsService.update_chess_log_charts_settings({key: value})
    → model emits chess_log_charts_changed
    → controller.set_user_settings(svc.get_settings())   [wired as AppController does]
    → controller updates live field

Asserts that after a menu handler call, the controller's live field reflects the
new value.  Qt signals are synchronous in this context, so no debounce wait is
needed — only the live-field update is asserted here, not the aggregation worker.

Requires Qt (offscreen) — all tests are gated on _QT_AVAILABLE.
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


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import QApplication, QMenu
    _app = QApplication.instance() or QApplication(sys.argv)

    from app.controllers.chess_log_charts_controller import ChessLogChartsController
    from app.views.menus.chess_log_charts_menu import ChessLogChartsMenuController
    from app.services.user_settings_service import UserSettingsService


def _reset_settings() -> None:
    UserSettingsService.get_instance().update_chess_log_settings(
        {
            "charts": {
                "target_progression_bins": 16,
                "ordinal_fallback_mode": "quantile",
                "progression_x_axis_mode": "uniform_bins",
                "compress_gap_max_segment_days": 28,
                "progression_line_style": "smooth",
                "progression_line_smooth_strength": 1.0,
            }
        }
    )


def _make_controller() -> "ChessLogChartsController":
    db_ctrl = MagicMock()
    db_ctrl.get_model.return_value = MagicMock()
    db_ctrl.get_model.return_value.dataChanged = MagicMock()
    db_ctrl.get_model.return_value.dataChanged.connect = MagicMock()
    return ChessLogChartsController(config={}, database_controller=db_ctrl)


def _make_menu() -> "ChessLogChartsMenuController":
    return ChessLogChartsMenuController(
        action_parent=_app,
        style_submenu=lambda _m: None,
    )


def _wire_controller(ctrl: "ChessLogChartsController") -> None:
    """Simulate main_window.py wiring: chess_log_charts_changed → ctrl.set_user_settings."""
    svc = UserSettingsService.get_instance()
    svc.get_model().chess_log_charts_changed.connect(
        lambda: ctrl.set_user_settings(svc.get_settings())
    )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsMenuEndToEnd(unittest.TestCase):
    """Menu handler → signal chain → controller live field updates."""

    def setUp(self):
        _reset_settings()
        self._ctrl = _make_controller()
        _wire_controller(self._ctrl)
        menu_ctrl = _make_menu()
        menu_ctrl.attach_to_parent_menu(QMenu())
        self._menu = menu_ctrl

    def tearDown(self):
        svc = UserSettingsService.get_instance()
        try:
            svc.get_model().chess_log_charts_changed.disconnect()
        except Exception:
            pass

    # --- Group A: Binning ---

    def test_select_bins_24_updates_controller_live_field(self):
        self._menu._on_target_bins_selected(24)
        self.assertEqual(self._ctrl.get_target_progression_bins(), 24)

    def test_select_bins_8_updates_controller_live_field(self):
        self._menu._on_target_bins_selected(8)
        self.assertEqual(self._ctrl.get_target_progression_bins(), 8)

    def test_select_binning_mode_equal_width_updates_controller(self):
        self._menu._on_ordinal_mode_selected("equal_width")
        self.assertEqual(self._ctrl.get_ordinal_fallback_mode(), "equal_width")

    def test_select_binning_mode_preserves_other_controller_fields(self):
        self._menu._on_ordinal_mode_selected("equal_width")
        self.assertEqual(self._ctrl.get_target_progression_bins(), 16)
        self.assertEqual(self._ctrl.get_progression_x_axis_mode(), "uniform_bins")

    # --- Group B: X axis ---

    def test_select_x_axis_gap_compressed_updates_controller(self):
        self._menu._on_x_axis_mode_selected("gap_compressed")
        self.assertEqual(self._ctrl.get_progression_x_axis_mode(), "gap_compressed")

    def test_select_x_axis_calendar_updates_controller(self):
        self._menu._on_x_axis_mode_selected("calendar_linear")
        self.assertEqual(self._ctrl.get_progression_x_axis_mode(), "calendar_linear")

    def test_select_gap_segment_14_updates_controller(self):
        self._menu._on_gap_segment_days_selected(14)
        self.assertEqual(self._ctrl.get_compress_gap_max_segment_days(), 14)

    def test_select_x_axis_preserves_bins_in_controller(self):
        self._menu._on_target_bins_selected(24)
        self._menu._on_x_axis_mode_selected("calendar_linear")
        self.assertEqual(self._ctrl.get_target_progression_bins(), 24)
        self.assertEqual(self._ctrl.get_progression_x_axis_mode(), "calendar_linear")

    # --- Group C: Line style ---

    def test_select_straight_line_style_updates_controller(self):
        self._menu._on_line_style_selected("straight")
        self.assertEqual(self._ctrl.get_progression_line_style(), "straight")

    def test_select_smooth_line_style_updates_controller(self):
        self._menu._on_line_style_selected("smooth")
        self.assertEqual(self._ctrl.get_progression_line_style(), "smooth")

    def test_select_strength_2_0_updates_controller(self):
        self._menu._on_smooth_strength_selected(2.0)
        self.assertAlmostEqual(self._ctrl.get_progression_line_smooth_strength(), 2.0)

    def test_select_strength_0_5_updates_controller(self):
        self._menu._on_smooth_strength_selected(0.5)
        self.assertAlmostEqual(self._ctrl.get_progression_line_smooth_strength(), 0.5)

    def test_all_six_settings_round_trip(self):
        """Changing all 6 settings via the menu propagates correctly to the controller."""
        self._menu._on_target_bins_selected(32)
        self._menu._on_ordinal_mode_selected("equal_width")
        self._menu._on_x_axis_mode_selected("gap_compressed")
        self._menu._on_gap_segment_days_selected(14)
        self._menu._on_line_style_selected("straight")
        self._menu._on_smooth_strength_selected(2.0)

        self.assertEqual(self._ctrl.get_target_progression_bins(), 32)
        self.assertEqual(self._ctrl.get_ordinal_fallback_mode(), "equal_width")
        self.assertEqual(self._ctrl.get_progression_x_axis_mode(), "gap_compressed")
        self.assertEqual(self._ctrl.get_compress_gap_max_segment_days(), 14)
        self.assertEqual(self._ctrl.get_progression_line_style(), "straight")
        self.assertAlmostEqual(self._ctrl.get_progression_line_smooth_strength(), 2.0)


if __name__ == "__main__":
    unittest.main()
