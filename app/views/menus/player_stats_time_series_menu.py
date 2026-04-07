"""Player Stats time-series settings menus (menubar + chart context menu).

Two separate :class:`PlayerStatsTimeSeriesMenuController` instances are required if both
UIs are used: the same :class:`QAction` cannot appear in the menu bar and a popup at once.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from app.services.player_stats_time_series_user import (
    CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS,
    CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH,
    CHOICES_TARGET_PROGRESSION_BINS,
)
from app.services.user_settings_service import UserSettingsService

PLAYER_STATS_TIME_SERIES_CONTEXT_SECTIONS: frozenset[str] = frozenset(
    {"Accuracy progression", "Move quality progression", "ACPL progression by phase"}
)


class PlayerStatsTimeSeriesMenuController:
    """Creates and syncs the nested "Time series settings" menu for one host (menubar or context)."""

    def __init__(self, action_parent, style_submenu: Callable[[QMenu], None]) -> None:
        self._parent = action_parent
        self._style = style_submenu
        self.top_menu: Optional[QMenu] = None
        self._ps_ts_bins_actions: Dict[int, QAction] = {}
        self._ps_ts_mode_quantile: Optional[QAction] = None
        self._ps_ts_mode_equal: Optional[QAction] = None
        self._ps_ts_x_uniform: Optional[QAction] = None
        self._ps_ts_x_gap: Optional[QAction] = None
        self._ps_ts_x_cal: Optional[QAction] = None
        self._ps_ts_gap_seg_actions: Dict[int, QAction] = {}
        self._ps_ts_line_smooth: Optional[QAction] = None
        self._ps_ts_line_straight: Optional[QAction] = None
        self._ps_ts_smooth_strength_actions: Dict[float, QAction] = {}

    def attach_to_parent_menu(self, parent_menu: QMenu) -> QMenu:
        """Add "Time series settings" under ``parent_menu`` (menu bar); build once."""
        self.top_menu = parent_menu.addMenu("Time series settings")
        self._style(self.top_menu)
        self._ensure_actions()
        self._populate_tree(self.top_menu)
        self.sync_from_settings()
        return self.top_menu

    def append_to_context_menu(self, context_menu: QMenu) -> None:
        """Add a fresh "Time series settings" subtree (new QMenus; reuse cached QActions)."""
        ts_menu = context_menu.addMenu("Time series settings")
        self._style(ts_menu)
        self._ensure_actions()
        self._populate_tree(ts_menu)
        self.sync_from_settings()

    def _ensure_actions(self) -> None:
        if self._ps_ts_bins_actions:
            return
        p = self._parent
        for n in CHOICES_TARGET_PROGRESSION_BINS:
            act = QAction(str(n), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=n: self._on_target_bins_selected(v))
            self._ps_ts_bins_actions[int(n)] = act
        self._ps_ts_mode_quantile = QAction("Quantile (equal games per bin)", p)
        self._ps_ts_mode_quantile.setCheckable(True)
        self._ps_ts_mode_quantile.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_mode_quantile.triggered.connect(lambda _c=False: self._on_ordinal_mode_selected("quantile"))
        self._ps_ts_mode_equal = QAction("Equal calendar width", p)
        self._ps_ts_mode_equal.setCheckable(True)
        self._ps_ts_mode_equal.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_mode_equal.triggered.connect(lambda _c=False: self._on_ordinal_mode_selected("equal_width"))
        self._ps_ts_x_uniform = QAction("Uniform bins", p)
        self._ps_ts_x_uniform.setCheckable(True)
        self._ps_ts_x_uniform.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_x_uniform.triggered.connect(lambda _c=False: self._on_x_axis_mode_selected("uniform_bins"))
        self._ps_ts_x_gap = QAction("Gap compressed", p)
        self._ps_ts_x_gap.setCheckable(True)
        self._ps_ts_x_gap.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_x_gap.triggered.connect(lambda _c=False: self._on_x_axis_mode_selected("gap_compressed"))
        self._ps_ts_x_cal = QAction("Calendar linear", p)
        self._ps_ts_x_cal.setCheckable(True)
        self._ps_ts_x_cal.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_x_cal.triggered.connect(lambda _c=False: self._on_x_axis_mode_selected("calendar_linear"))
        for n in CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS:
            act = QAction(str(n), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=n: self._on_gap_segment_days_selected(v))
            self._ps_ts_gap_seg_actions[int(n)] = act
        self._ps_ts_line_smooth = QAction("Smooth", p)
        self._ps_ts_line_smooth.setCheckable(True)
        self._ps_ts_line_smooth.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_line_smooth.triggered.connect(lambda _c=False: self._on_line_style_selected("smooth"))
        self._ps_ts_line_straight = QAction("Straight segments", p)
        self._ps_ts_line_straight.setCheckable(True)
        self._ps_ts_line_straight.setMenuRole(QAction.MenuRole.NoRole)
        self._ps_ts_line_straight.triggered.connect(lambda _c=False: self._on_line_style_selected("straight"))
        for x in CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH:
            act = QAction(str(x), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=x: self._on_smooth_strength_selected(v))
            self._ps_ts_smooth_strength_actions[float(x)] = act

    def _populate_tree(self, ts_menu: QMenu) -> None:
        m_bins = ts_menu.addMenu("Progression bins")
        self._style(m_bins)
        for n in CHOICES_TARGET_PROGRESSION_BINS:
            m_bins.addAction(self._ps_ts_bins_actions[int(n)])

        m_mode = ts_menu.addMenu("Binning mode")
        self._style(m_mode)
        assert self._ps_ts_mode_quantile and self._ps_ts_mode_equal
        m_mode.addAction(self._ps_ts_mode_quantile)
        m_mode.addAction(self._ps_ts_mode_equal)

        m_x = ts_menu.addMenu("X axis layout")
        self._style(m_x)
        assert self._ps_ts_x_uniform and self._ps_ts_x_gap and self._ps_ts_x_cal
        m_x.addAction(self._ps_ts_x_uniform)
        m_x.addAction(self._ps_ts_x_gap)
        m_x.addAction(self._ps_ts_x_cal)

        m_gap = ts_menu.addMenu("Max gap segment (calendar days)")
        self._style(m_gap)
        for n in CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS:
            m_gap.addAction(self._ps_ts_gap_seg_actions[int(n)])

        m_line = ts_menu.addMenu("Progression line style")
        self._style(m_line)
        assert self._ps_ts_line_smooth and self._ps_ts_line_straight
        m_line.addAction(self._ps_ts_line_smooth)
        m_line.addAction(self._ps_ts_line_straight)

        m_str = ts_menu.addMenu("Smoothing strength")
        self._style(m_str)
        for x in CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH:
            m_str.addAction(self._ps_ts_smooth_strength_actions[float(x)])

    def sync_from_settings(self) -> None:
        if not self._ps_ts_bins_actions:
            return
        ts = UserSettingsService.get_instance().get_model().get_player_stats_time_series()
        nb = int(ts["target_progression_bins"])
        for n, a in self._ps_ts_bins_actions.items():
            a.blockSignals(True)
            a.setChecked(n == nb)
            a.blockSignals(False)

        om = str(ts["ordinal_fallback_mode"])
        assert self._ps_ts_mode_quantile and self._ps_ts_mode_equal
        self._ps_ts_mode_quantile.blockSignals(True)
        self._ps_ts_mode_equal.blockSignals(True)
        self._ps_ts_mode_quantile.setChecked(om == "quantile")
        self._ps_ts_mode_equal.setChecked(om == "equal_width")
        self._ps_ts_mode_quantile.blockSignals(False)
        self._ps_ts_mode_equal.blockSignals(False)

        xm = str(ts["progression_x_axis_mode"])
        assert self._ps_ts_x_uniform and self._ps_ts_x_gap and self._ps_ts_x_cal
        self._ps_ts_x_uniform.blockSignals(True)
        self._ps_ts_x_gap.blockSignals(True)
        self._ps_ts_x_cal.blockSignals(True)
        self._ps_ts_x_uniform.setChecked(xm == "uniform_bins")
        self._ps_ts_x_gap.setChecked(xm == "gap_compressed")
        self._ps_ts_x_cal.setChecked(xm == "calendar_linear")
        self._ps_ts_x_uniform.blockSignals(False)
        self._ps_ts_x_gap.blockSignals(False)
        self._ps_ts_x_cal.blockSignals(False)

        gd = int(ts["compress_gap_max_segment_days"])
        for n, a in self._ps_ts_gap_seg_actions.items():
            a.blockSignals(True)
            a.setChecked(n == gd)
            a.blockSignals(False)

        st = str(ts["progression_line_style"])
        assert self._ps_ts_line_smooth and self._ps_ts_line_straight
        self._ps_ts_line_smooth.blockSignals(True)
        self._ps_ts_line_straight.blockSignals(True)
        self._ps_ts_line_smooth.setChecked(st == "smooth")
        self._ps_ts_line_straight.setChecked(st == "straight")
        self._ps_ts_line_smooth.blockSignals(False)
        self._ps_ts_line_straight.blockSignals(False)

        ss = float(ts["progression_line_smooth_strength"])
        for x, a in self._ps_ts_smooth_strength_actions.items():
            a.blockSignals(True)
            a.setChecked(abs(x - ss) < 1e-9)
            a.blockSignals(False)

    def _on_target_bins_selected(self, value: int) -> None:
        for n, a in self._ps_ts_bins_actions.items():
            a.blockSignals(True)
            a.setChecked(n == value)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_time_series({"target_progression_bins": value})

    def _on_ordinal_mode_selected(self, mode: str) -> None:
        assert self._ps_ts_mode_quantile and self._ps_ts_mode_equal
        self._ps_ts_mode_quantile.blockSignals(True)
        self._ps_ts_mode_equal.blockSignals(True)
        self._ps_ts_mode_quantile.setChecked(mode == "quantile")
        self._ps_ts_mode_equal.setChecked(mode == "equal_width")
        self._ps_ts_mode_quantile.blockSignals(False)
        self._ps_ts_mode_equal.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_time_series({"ordinal_fallback_mode": mode})

    def _on_x_axis_mode_selected(self, mode: str) -> None:
        assert self._ps_ts_x_uniform and self._ps_ts_x_gap and self._ps_ts_x_cal
        self._ps_ts_x_uniform.blockSignals(True)
        self._ps_ts_x_gap.blockSignals(True)
        self._ps_ts_x_cal.blockSignals(True)
        self._ps_ts_x_uniform.setChecked(mode == "uniform_bins")
        self._ps_ts_x_gap.setChecked(mode == "gap_compressed")
        self._ps_ts_x_cal.setChecked(mode == "calendar_linear")
        self._ps_ts_x_uniform.blockSignals(False)
        self._ps_ts_x_gap.blockSignals(False)
        self._ps_ts_x_cal.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_time_series({"progression_x_axis_mode": mode})

    def _on_gap_segment_days_selected(self, value: int) -> None:
        for n, a in self._ps_ts_gap_seg_actions.items():
            a.blockSignals(True)
            a.setChecked(n == value)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_time_series({"compress_gap_max_segment_days": value})

    def _on_line_style_selected(self, style: str) -> None:
        assert self._ps_ts_line_smooth and self._ps_ts_line_straight
        self._ps_ts_line_smooth.blockSignals(True)
        self._ps_ts_line_straight.blockSignals(True)
        self._ps_ts_line_smooth.setChecked(style == "smooth")
        self._ps_ts_line_straight.setChecked(style == "straight")
        self._ps_ts_line_smooth.blockSignals(False)
        self._ps_ts_line_straight.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_time_series({"progression_line_style": style})

    def _on_smooth_strength_selected(self, value: float) -> None:
        for x, a in self._ps_ts_smooth_strength_actions.items():
            a.blockSignals(True)
            a.setChecked(abs(x - value) < 1e-9)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_time_series({"progression_line_smooth_strength": value})

