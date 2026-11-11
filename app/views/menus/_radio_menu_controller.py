"""Shared base for time-series settings menus (Chess Log Charts + Player Stats).

Builds a 6-group, 3-separator radio-button submenu. Subclasses supply
``_read_settings()`` (returns the current settings dict, aligned key names)
and ``_apply(key, value)`` (writes a single key change to user settings).

All six groups use the aligned Player-Stats key names introduced in Phase 4:
  target_progression_bins, ordinal_fallback_mode, progression_x_axis_mode,
  compress_gap_max_segment_days, progression_line_style, progression_line_smooth_strength.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

_BINS_CHOICES = (8, 12, 16, 24, 32)
_GAP_CHOICES = (14, 28, 50, 100)
_STRENGTH_CHOICES = (0.5, 1.0, 1.5, 2.0)


class RadioMenuController:
    """Abstract base: 6-group radio menu for time-series chart settings."""

    def __init__(self, action_parent, style_submenu: Callable[[QMenu], None]) -> None:
        self._parent = action_parent
        self._style = style_submenu
        self.top_menu: Optional[QMenu] = None
        # Group A — Binning
        self._bins_actions: Dict[int, QAction] = {}
        self._mode_quantile: Optional[QAction] = None
        self._mode_equal: Optional[QAction] = None
        # Group B — X axis
        self._x_uniform: Optional[QAction] = None
        self._x_gap: Optional[QAction] = None
        self._x_cal: Optional[QAction] = None
        self._gap_seg_actions: Dict[int, QAction] = {}
        # Group C — Line style
        self._line_smooth: Optional[QAction] = None
        self._line_straight: Optional[QAction] = None
        self._strength_actions: Dict[float, QAction] = {}

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    def _read_settings(self) -> Dict[str, Any]:
        """Return the current settings dict (aligned key names)."""
        raise NotImplementedError

    def _apply(self, key: str, value: Any) -> None:
        """Persist a single key change to user settings."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach_to_parent_menu(self, parent_menu: QMenu) -> QMenu:
        """Add 'Time series settings' under ``parent_menu``; build once."""
        self.top_menu = parent_menu.addMenu("Time series settings")
        self._style(self.top_menu)
        self._ensure_actions()
        self._populate_tree(self.top_menu)
        self.sync_from_settings()
        return self.top_menu

    def sync_from_settings(self) -> None:
        """Refresh all checked states from persisted user settings."""
        if not self._bins_actions:
            return
        if not (self._mode_quantile and self._mode_equal and
                self._x_uniform and self._x_gap and self._x_cal and
                self._line_smooth and self._line_straight):
            raise RuntimeError("call _ensure_actions() first")
        settings = self._read_settings()

        nb = int(settings["target_progression_bins"])
        for n, a in self._bins_actions.items():
            a.blockSignals(True)
            a.setChecked(n == nb)
            a.blockSignals(False)

        om = str(settings["ordinal_fallback_mode"])
        self._mode_quantile.blockSignals(True)
        self._mode_equal.blockSignals(True)
        self._mode_quantile.setChecked(om == "quantile")
        self._mode_equal.setChecked(om == "equal_width")
        self._mode_quantile.blockSignals(False)
        self._mode_equal.blockSignals(False)

        xm = str(settings["progression_x_axis_mode"])
        self._x_uniform.blockSignals(True)
        self._x_gap.blockSignals(True)
        self._x_cal.blockSignals(True)
        self._x_uniform.setChecked(xm == "uniform_bins")
        self._x_gap.setChecked(xm == "gap_compressed")
        self._x_cal.setChecked(xm == "calendar_linear")
        self._x_uniform.blockSignals(False)
        self._x_gap.blockSignals(False)
        self._x_cal.blockSignals(False)

        gd = int(settings["compress_gap_max_segment_days"])
        for n, a in self._gap_seg_actions.items():
            a.blockSignals(True)
            a.setChecked(n == gd)
            a.blockSignals(False)

        st = str(settings["progression_line_style"])
        self._line_smooth.blockSignals(True)
        self._line_straight.blockSignals(True)
        self._line_smooth.setChecked(st == "smooth")
        self._line_straight.setChecked(st == "straight")
        self._line_smooth.blockSignals(False)
        self._line_straight.blockSignals(False)

        ss = float(settings["progression_line_smooth_strength"])
        for x, a in self._strength_actions.items():
            a.blockSignals(True)
            a.setChecked(abs(x - ss) < 1e-9)
            a.blockSignals(False)

    # ------------------------------------------------------------------
    # Handlers — update checked state then delegate to _apply
    # ------------------------------------------------------------------

    def _on_target_bins_selected(self, value: int) -> None:
        for n, a in self._bins_actions.items():
            a.blockSignals(True)
            a.setChecked(n == value)
            a.blockSignals(False)
        self._apply("target_progression_bins", value)

    def _on_ordinal_mode_selected(self, mode: str) -> None:
        if not (self._mode_quantile and self._mode_equal):
            raise RuntimeError("call _ensure_actions() first")
        self._mode_quantile.blockSignals(True)
        self._mode_equal.blockSignals(True)
        self._mode_quantile.setChecked(mode == "quantile")
        self._mode_equal.setChecked(mode == "equal_width")
        self._mode_quantile.blockSignals(False)
        self._mode_equal.blockSignals(False)
        self._apply("ordinal_fallback_mode", mode)

    def _on_x_axis_mode_selected(self, mode: str) -> None:
        if not (self._x_uniform and self._x_gap and self._x_cal):
            raise RuntimeError("call _ensure_actions() first")
        self._x_uniform.blockSignals(True)
        self._x_gap.blockSignals(True)
        self._x_cal.blockSignals(True)
        self._x_uniform.setChecked(mode == "uniform_bins")
        self._x_gap.setChecked(mode == "gap_compressed")
        self._x_cal.setChecked(mode == "calendar_linear")
        self._x_uniform.blockSignals(False)
        self._x_gap.blockSignals(False)
        self._x_cal.blockSignals(False)
        self._apply("progression_x_axis_mode", mode)

    def _on_gap_segment_days_selected(self, value: int) -> None:
        for n, a in self._gap_seg_actions.items():
            a.blockSignals(True)
            a.setChecked(n == value)
            a.blockSignals(False)
        self._apply("compress_gap_max_segment_days", value)

    def _on_line_style_selected(self, style: str) -> None:
        if not (self._line_smooth and self._line_straight):
            raise RuntimeError("call _ensure_actions() first")
        self._line_smooth.blockSignals(True)
        self._line_straight.blockSignals(True)
        self._line_smooth.setChecked(style == "smooth")
        self._line_straight.setChecked(style == "straight")
        self._line_smooth.blockSignals(False)
        self._line_straight.blockSignals(False)
        self._apply("progression_line_style", style)

    def _on_smooth_strength_selected(self, value: float) -> None:
        for x, a in self._strength_actions.items():
            a.blockSignals(True)
            a.setChecked(abs(x - value) < 1e-9)
            a.blockSignals(False)
        self._apply("progression_line_smooth_strength", value)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_actions(self) -> None:
        if self._bins_actions:
            return
        p = self._parent

        for n in _BINS_CHOICES:
            act = QAction(str(n), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=n: self._on_target_bins_selected(v))
            self._bins_actions[int(n)] = act

        self._mode_quantile = QAction("Quantile (equal games per bin)", p)
        self._mode_quantile.setCheckable(True)
        self._mode_quantile.setMenuRole(QAction.MenuRole.NoRole)
        self._mode_quantile.triggered.connect(lambda _c=False: self._on_ordinal_mode_selected("quantile"))

        self._mode_equal = QAction("Equal calendar width", p)
        self._mode_equal.setCheckable(True)
        self._mode_equal.setMenuRole(QAction.MenuRole.NoRole)
        self._mode_equal.triggered.connect(lambda _c=False: self._on_ordinal_mode_selected("equal_width"))

        self._x_uniform = QAction("Uniform bins", p)
        self._x_uniform.setCheckable(True)
        self._x_uniform.setMenuRole(QAction.MenuRole.NoRole)
        self._x_uniform.triggered.connect(lambda _c=False: self._on_x_axis_mode_selected("uniform_bins"))

        self._x_gap = QAction("Gap compressed", p)
        self._x_gap.setCheckable(True)
        self._x_gap.setMenuRole(QAction.MenuRole.NoRole)
        self._x_gap.triggered.connect(lambda _c=False: self._on_x_axis_mode_selected("gap_compressed"))

        self._x_cal = QAction("Calendar linear", p)
        self._x_cal.setCheckable(True)
        self._x_cal.setMenuRole(QAction.MenuRole.NoRole)
        self._x_cal.triggered.connect(lambda _c=False: self._on_x_axis_mode_selected("calendar_linear"))

        for n in _GAP_CHOICES:
            act = QAction(str(n), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=n: self._on_gap_segment_days_selected(v))
            self._gap_seg_actions[int(n)] = act

        self._line_smooth = QAction("Smooth", p)
        self._line_smooth.setCheckable(True)
        self._line_smooth.setMenuRole(QAction.MenuRole.NoRole)
        self._line_smooth.triggered.connect(lambda _c=False: self._on_line_style_selected("smooth"))

        self._line_straight = QAction("Straight segments", p)
        self._line_straight.setCheckable(True)
        self._line_straight.setMenuRole(QAction.MenuRole.NoRole)
        self._line_straight.triggered.connect(lambda _c=False: self._on_line_style_selected("straight"))

        for x in _STRENGTH_CHOICES:
            act = QAction(str(x), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=x: self._on_smooth_strength_selected(v))
            self._strength_actions[float(x)] = act

    def _populate_tree(self, ts_menu: QMenu) -> None:
        if not (self._mode_quantile and self._mode_equal and
                self._x_uniform and self._x_gap and self._x_cal and
                self._line_smooth and self._line_straight):
            raise RuntimeError("call _ensure_actions() first")
        m_bins = ts_menu.addMenu("Progression bins")
        self._style(m_bins)
        for n in _BINS_CHOICES:
            m_bins.addAction(self._bins_actions[int(n)])

        m_mode = ts_menu.addMenu("Binning mode")
        self._style(m_mode)
        m_mode.addAction(self._mode_quantile)
        m_mode.addAction(self._mode_equal)

        ts_menu.addSeparator()

        m_x = ts_menu.addMenu("X axis layout")
        self._style(m_x)
        m_x.addAction(self._x_uniform)
        m_x.addAction(self._x_gap)
        m_x.addAction(self._x_cal)

        m_gap = ts_menu.addMenu("Max gap segment (calendar days)")
        self._style(m_gap)
        for n in _GAP_CHOICES:
            m_gap.addAction(self._gap_seg_actions[int(n)])

        ts_menu.addSeparator()

        m_line = ts_menu.addMenu("Progression line style")
        self._style(m_line)
        m_line.addAction(self._line_smooth)
        m_line.addAction(self._line_straight)

        m_str = ts_menu.addMenu("Smoothing strength")
        self._style(m_str)
        for x in _STRENGTH_CHOICES:
            m_str.addAction(self._strength_actions[float(x)])
