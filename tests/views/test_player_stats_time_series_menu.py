"""Characterization tests for PlayerStatsTimeSeriesMenuController (6-item, 3-group menu).

Requires a working Qt platform (CI: QT_QPA_PLATFORM=offscreen).
Uses UserSettingsService directly — same as the production code path.
Mirrors the structure of test_chess_log_charts_menu.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

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

    from app.views.menus.player_stats_time_series_menu import PlayerStatsTimeSeriesMenuController
    from app.services.player_stats_time_series_user import (
        CHOICES_TARGET_PROGRESSION_BINS,
        CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS,
        CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH,
        normalize_player_stats_time_series_settings,
    )
    from app.services.user_settings_service import UserSettingsService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctrl() -> "PlayerStatsTimeSeriesMenuController":
    return PlayerStatsTimeSeriesMenuController(
        action_parent=_app,
        style_submenu=lambda _m: None,
    )


def _reset_ps_settings() -> None:
    UserSettingsService.get_instance().update_player_stats_time_series({
        "target_progression_bins": 16,
        "ordinal_fallback_mode": "quantile",
        "progression_x_axis_mode": "uniform_bins",
        "compress_gap_max_segment_days": 28,
        "progression_line_style": "smooth",
        "progression_line_smooth_strength": 1.0,
    })


def _ts() -> dict:
    return normalize_player_stats_time_series_settings(
        UserSettingsService.get_instance().get_model().get_player_stats_time_series()
    )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestPlayerStatsTimeSeriesMenuStructure(unittest.TestCase):

    def setUp(self):
        _reset_ps_settings()

    def _attached_ctrl(self) -> "PlayerStatsTimeSeriesMenuController":
        ctrl = _make_ctrl()
        ctrl.attach_to_parent_menu(QMenu())
        return ctrl

    def test_top_menu_created(self):
        ctrl = self._attached_ctrl()
        self.assertIsNotNone(ctrl.top_menu)
        self.assertIsInstance(ctrl.top_menu, QMenu)

    def test_bins_actions_count_matches_choices(self):
        ctrl = self._attached_ctrl()
        self.assertEqual(len(ctrl._bins_actions), len(CHOICES_TARGET_PROGRESSION_BINS))

    def test_gap_seg_actions_count_matches_choices(self):
        ctrl = self._attached_ctrl()
        self.assertEqual(len(ctrl._gap_seg_actions), len(CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS))

    def test_strength_actions_count_matches_choices(self):
        ctrl = self._attached_ctrl()
        self.assertEqual(len(ctrl._strength_actions), len(CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH))

    def test_all_x_axis_actions_exist(self):
        ctrl = self._attached_ctrl()
        self.assertIsNotNone(ctrl._x_uniform)
        self.assertIsNotNone(ctrl._x_gap)
        self.assertIsNotNone(ctrl._x_cal)

    def test_all_binning_mode_actions_exist(self):
        ctrl = self._attached_ctrl()
        self.assertIsNotNone(ctrl._mode_quantile)
        self.assertIsNotNone(ctrl._mode_equal)

    def test_all_line_style_actions_exist(self):
        ctrl = self._attached_ctrl()
        self.assertIsNotNone(ctrl._line_smooth)
        self.assertIsNotNone(ctrl._line_straight)

    def test_all_bins_actions_checkable(self):
        ctrl = self._attached_ctrl()
        for act in ctrl._bins_actions.values():
            self.assertTrue(act.isCheckable())

    def test_all_gap_seg_actions_checkable(self):
        ctrl = self._attached_ctrl()
        for act in ctrl._gap_seg_actions.values():
            self.assertTrue(act.isCheckable())

    def test_all_strength_actions_checkable(self):
        ctrl = self._attached_ctrl()
        for act in ctrl._strength_actions.values():
            self.assertTrue(act.isCheckable())

    def test_mode_and_line_and_x_axis_actions_checkable(self):
        ctrl = self._attached_ctrl()
        for act in (ctrl._mode_quantile, ctrl._mode_equal,
                    ctrl._x_uniform, ctrl._x_gap, ctrl._x_cal,
                    ctrl._line_smooth, ctrl._line_straight):
            self.assertTrue(act.isCheckable())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestPlayerStatsTimeSeriesMenuCheckedStateOnBuild(unittest.TestCase):
    """Exactly one item per group checked after attach_to_parent_menu."""

    def setUp(self):
        _reset_ps_settings()

    def _attached_ctrl(self) -> "PlayerStatsTimeSeriesMenuController":
        ctrl = _make_ctrl()
        ctrl.attach_to_parent_menu(QMenu())
        return ctrl

    def test_exactly_one_bins_action_checked(self):
        ctrl = self._attached_ctrl()
        checked = [a for a in ctrl._bins_actions.values() if a.isChecked()]
        self.assertEqual(len(checked), 1)

    def test_default_16_bins_checked(self):
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._bins_actions[16].isChecked())
        for n, a in ctrl._bins_actions.items():
            if n != 16:
                self.assertFalse(a.isChecked())

    def test_default_quantile_checked(self):
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._mode_quantile.isChecked())
        self.assertFalse(ctrl._mode_equal.isChecked())

    def test_default_uniform_x_axis_checked(self):
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._x_uniform.isChecked())
        self.assertFalse(ctrl._x_gap.isChecked())
        self.assertFalse(ctrl._x_cal.isChecked())

    def test_default_28_gap_segment_checked(self):
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._gap_seg_actions[28].isChecked())
        for n, a in ctrl._gap_seg_actions.items():
            if n != 28:
                self.assertFalse(a.isChecked())

    def test_default_smooth_line_checked(self):
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._line_smooth.isChecked())
        self.assertFalse(ctrl._line_straight.isChecked())

    def test_default_1_0_strength_checked(self):
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._strength_actions[1.0].isChecked())
        for x, a in ctrl._strength_actions.items():
            if abs(x - 1.0) > 1e-9:
                self.assertFalse(a.isChecked())

    def test_persisted_24_bins_reflected_on_build(self):
        UserSettingsService.get_instance().update_player_stats_time_series(
            {"target_progression_bins": 24}
        )
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._bins_actions[24].isChecked())
        self.assertFalse(ctrl._bins_actions[16].isChecked())

    def test_persisted_equal_width_mode_reflected_on_build(self):
        UserSettingsService.get_instance().update_player_stats_time_series(
            {"ordinal_fallback_mode": "equal_width"}
        )
        ctrl = self._attached_ctrl()
        self.assertFalse(ctrl._mode_quantile.isChecked())
        self.assertTrue(ctrl._mode_equal.isChecked())

    def test_persisted_calendar_linear_reflected_on_build(self):
        UserSettingsService.get_instance().update_player_stats_time_series(
            {"progression_x_axis_mode": "calendar_linear"}
        )
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._x_cal.isChecked())
        self.assertFalse(ctrl._x_uniform.isChecked())
        self.assertFalse(ctrl._x_gap.isChecked())

    def test_persisted_straight_line_style_reflected_on_build(self):
        UserSettingsService.get_instance().update_player_stats_time_series(
            {"progression_line_style": "straight"}
        )
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._line_straight.isChecked())
        self.assertFalse(ctrl._line_smooth.isChecked())

    def test_persisted_0_5_strength_reflected_on_build(self):
        UserSettingsService.get_instance().update_player_stats_time_series(
            {"progression_line_smooth_strength": 0.5}
        )
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._strength_actions[0.5].isChecked())
        self.assertFalse(ctrl._strength_actions[1.0].isChecked())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestPlayerStatsTimeSeriesMenuActionTriggers(unittest.TestCase):
    """Selecting a value persists to settings and updates the checked state."""

    def setUp(self):
        _reset_ps_settings()

    def _attached_ctrl(self) -> "PlayerStatsTimeSeriesMenuController":
        ctrl = _make_ctrl()
        ctrl.attach_to_parent_menu(QMenu())
        return ctrl

    # --- Group A: Binning ---

    def test_on_target_bins_selected_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_target_bins_selected(8)
        self.assertEqual(_ts()["target_progression_bins"], 8)

    def test_on_target_bins_selected_updates_checked_state(self):
        ctrl = self._attached_ctrl()
        ctrl._on_target_bins_selected(32)
        self.assertTrue(ctrl._bins_actions[32].isChecked())
        for n, a in ctrl._bins_actions.items():
            if n != 32:
                self.assertFalse(a.isChecked())

    def test_on_target_bins_writes_single_key(self):
        ctrl = self._attached_ctrl()
        ctrl._on_target_bins_selected(24)
        ts = _ts()
        self.assertEqual(ts["ordinal_fallback_mode"], "quantile")
        self.assertEqual(ts["progression_x_axis_mode"], "uniform_bins")
        self.assertEqual(ts["compress_gap_max_segment_days"], 28)
        self.assertEqual(ts["progression_line_style"], "smooth")
        self.assertAlmostEqual(ts["progression_line_smooth_strength"], 1.0)

    def test_on_ordinal_mode_selected_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_ordinal_mode_selected("equal_width")
        self.assertEqual(_ts()["ordinal_fallback_mode"], "equal_width")

    def test_on_ordinal_mode_selected_updates_checked_state(self):
        ctrl = self._attached_ctrl()
        ctrl._on_ordinal_mode_selected("equal_width")
        self.assertTrue(ctrl._mode_equal.isChecked())
        self.assertFalse(ctrl._mode_quantile.isChecked())

    def test_on_ordinal_mode_selected_preserves_other_keys(self):
        ctrl = self._attached_ctrl()
        ctrl._on_ordinal_mode_selected("equal_width")
        ts = _ts()
        self.assertEqual(ts["target_progression_bins"], 16)
        self.assertEqual(ts["progression_x_axis_mode"], "uniform_bins")

    # --- Group B: X axis ---

    def test_on_x_axis_mode_selected_gap_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_x_axis_mode_selected("gap_compressed")
        self.assertEqual(_ts()["progression_x_axis_mode"], "gap_compressed")

    def test_on_x_axis_mode_selected_calendar_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_x_axis_mode_selected("calendar_linear")
        self.assertEqual(_ts()["progression_x_axis_mode"], "calendar_linear")

    def test_on_x_axis_mode_selected_updates_checked_state(self):
        ctrl = self._attached_ctrl()
        ctrl._on_x_axis_mode_selected("gap_compressed")
        self.assertFalse(ctrl._x_uniform.isChecked())
        self.assertTrue(ctrl._x_gap.isChecked())
        self.assertFalse(ctrl._x_cal.isChecked())

    def test_on_x_axis_mode_selected_preserves_other_keys(self):
        ctrl = self._attached_ctrl()
        ctrl._on_x_axis_mode_selected("calendar_linear")
        ts = _ts()
        self.assertEqual(ts["target_progression_bins"], 16)
        self.assertEqual(ts["ordinal_fallback_mode"], "quantile")
        self.assertEqual(ts["compress_gap_max_segment_days"], 28)

    def test_on_gap_segment_days_selected_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_gap_segment_days_selected(14)
        self.assertEqual(_ts()["compress_gap_max_segment_days"], 14)

    def test_on_gap_segment_days_selected_updates_checked_state(self):
        ctrl = self._attached_ctrl()
        ctrl._on_gap_segment_days_selected(100)
        self.assertTrue(ctrl._gap_seg_actions[100].isChecked())
        for n, a in ctrl._gap_seg_actions.items():
            if n != 100:
                self.assertFalse(a.isChecked())

    def test_on_gap_segment_days_selected_preserves_other_keys(self):
        ctrl = self._attached_ctrl()
        ctrl._on_gap_segment_days_selected(50)
        ts = _ts()
        self.assertEqual(ts["target_progression_bins"], 16)
        self.assertEqual(ts["progression_x_axis_mode"], "uniform_bins")
        self.assertEqual(ts["progression_line_style"], "smooth")

    # --- Group C: Line style ---

    def test_on_line_style_selected_straight_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_line_style_selected("straight")
        self.assertEqual(_ts()["progression_line_style"], "straight")

    def test_on_line_style_selected_updates_checked_state(self):
        ctrl = self._attached_ctrl()
        ctrl._on_line_style_selected("straight")
        self.assertTrue(ctrl._line_straight.isChecked())
        self.assertFalse(ctrl._line_smooth.isChecked())

    def test_on_line_style_selected_preserves_other_keys(self):
        ctrl = self._attached_ctrl()
        ctrl._on_line_style_selected("straight")
        ts = _ts()
        self.assertEqual(ts["target_progression_bins"], 16)
        self.assertEqual(ts["progression_x_axis_mode"], "uniform_bins")

    def test_on_smooth_strength_selected_persists(self):
        ctrl = self._attached_ctrl()
        ctrl._on_smooth_strength_selected(2.0)
        self.assertAlmostEqual(_ts()["progression_line_smooth_strength"], 2.0)

    def test_on_smooth_strength_selected_updates_checked_state(self):
        ctrl = self._attached_ctrl()
        ctrl._on_smooth_strength_selected(0.5)
        self.assertTrue(ctrl._strength_actions[0.5].isChecked())
        for x, a in ctrl._strength_actions.items():
            if abs(x - 0.5) > 1e-9:
                self.assertFalse(a.isChecked())

    def test_on_smooth_strength_selected_preserves_other_keys(self):
        ctrl = self._attached_ctrl()
        ctrl._on_smooth_strength_selected(1.5)
        ts = _ts()
        self.assertEqual(ts["progression_line_style"], "smooth")
        self.assertEqual(ts["target_progression_bins"], 16)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestPlayerStatsTimeSeriesMenuSyncFromSettings(unittest.TestCase):

    def setUp(self):
        _reset_ps_settings()

    def _attached_ctrl(self) -> "PlayerStatsTimeSeriesMenuController":
        ctrl = _make_ctrl()
        ctrl.attach_to_parent_menu(QMenu())
        return ctrl

    def test_sync_before_actions_built_is_a_no_op(self):
        ctrl = _make_ctrl()
        ctrl.sync_from_settings()  # must not raise

    def test_sync_updates_all_groups_after_external_change(self):
        ctrl = self._attached_ctrl()
        UserSettingsService.get_instance().update_player_stats_time_series({
            "target_progression_bins": 8,
            "ordinal_fallback_mode": "equal_width",
            "progression_x_axis_mode": "calendar_linear",
            "compress_gap_max_segment_days": 14,
            "progression_line_style": "straight",
            "progression_line_smooth_strength": 2.0,
        })
        ctrl.sync_from_settings()
        self.assertTrue(ctrl._bins_actions[8].isChecked())
        self.assertTrue(ctrl._mode_equal.isChecked())
        self.assertFalse(ctrl._mode_quantile.isChecked())
        self.assertTrue(ctrl._x_cal.isChecked())
        self.assertFalse(ctrl._x_uniform.isChecked())
        self.assertTrue(ctrl._gap_seg_actions[14].isChecked())
        self.assertTrue(ctrl._line_straight.isChecked())
        self.assertFalse(ctrl._line_smooth.isChecked())
        self.assertTrue(ctrl._strength_actions[2.0].isChecked())
        self.assertFalse(ctrl._strength_actions[1.0].isChecked())

    def test_sync_updates_bins_after_external_change(self):
        ctrl = self._attached_ctrl()
        UserSettingsService.get_instance().update_player_stats_time_series(
            {"target_progression_bins": 32}
        )
        ctrl.sync_from_settings()
        self.assertTrue(ctrl._bins_actions[32].isChecked())
        self.assertFalse(ctrl._bins_actions[16].isChecked())

    def test_player_stats_time_series_changed_signal_drives_sync(self):
        """player_stats_time_series_changed emitted by update must drive sync."""
        ctrl = self._attached_ctrl()
        self.assertTrue(ctrl._x_uniform.isChecked())

        model = UserSettingsService.get_instance().get_model()
        model.player_stats_time_series_changed.connect(ctrl.sync_from_settings)

        UserSettingsService.get_instance().update_player_stats_time_series(
            {"progression_x_axis_mode": "gap_compressed"}
        )
        self.assertTrue(ctrl._x_gap.isChecked())
        self.assertFalse(ctrl._x_uniform.isChecked())

        model.player_stats_time_series_changed.disconnect(ctrl.sync_from_settings)

    def test_player_stats_time_series_changed_signal_drives_sync_line_style(self):
        ctrl = self._attached_ctrl()
        model = UserSettingsService.get_instance().get_model()
        model.player_stats_time_series_changed.connect(ctrl.sync_from_settings)

        UserSettingsService.get_instance().update_player_stats_time_series(
            {"progression_line_style": "straight"}
        )
        self.assertTrue(ctrl._line_straight.isChecked())
        self.assertFalse(ctrl._line_smooth.isChecked())

        model.player_stats_time_series_changed.disconnect(ctrl.sync_from_settings)


if __name__ == "__main__":
    unittest.main()
