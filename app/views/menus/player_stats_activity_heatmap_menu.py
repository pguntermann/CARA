"""Player Stats activity heatmap settings (menubar + section context menu).

Use two :class:`PlayerStatsActivityHeatmapMenuController` instances if both UIs are shown.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from app.services.player_stats_activity_heatmap_user import (
    CHOICES_COLOR_SCALE_MAX_FIXED,
    VALID_MONTH_DIVIDER_MODE,
)
from app.services.user_settings_service import UserSettingsService

PLAYER_STATS_ACTIVITY_HEATMAP_CONTEXT_SECTIONS: frozenset[str] = frozenset({"Activity heatmap"})


class PlayerStatsActivityHeatmapMenuController:
    """Nested "Activity heatmap settings" menu for one host (menubar or context)."""

    def __init__(self, action_parent, style_submenu: Callable[[QMenu], None]) -> None:
        self._parent = action_parent
        self._style = style_submenu
        self.top_menu: Optional[QMenu] = None
        self._week_start: Dict[str, QAction] = {}
        self._preset: Dict[str, QAction] = {}
        self._scale_mode: Dict[str, QAction] = {}
        self._scale_fixed: Dict[int, QAction] = {}
        self._partial: Dict[str, QAction] = {}
        self._date_range: Dict[str, QAction] = {}
        self._month_divider: Dict[str, QAction] = {}

    def attach_to_parent_menu(self, parent_menu: QMenu) -> QMenu:
        """Add "Activity heatmap settings" under ``parent_menu`` (menu bar); build once."""
        self.top_menu = parent_menu.addMenu("Activity heatmap settings")
        self._style(self.top_menu)
        self._ensure_actions()
        self._populate_tree(self.top_menu)
        self.sync_from_settings()
        return self.top_menu

    def append_to_context_menu(self, context_menu: QMenu) -> None:
        """Add a fresh "Activity heatmap settings" subtree (new QMenus; reuse cached QActions)."""
        hm_menu = context_menu.addMenu("Activity heatmap settings")
        self._style(hm_menu)
        self._ensure_actions()
        self._populate_tree(hm_menu)
        self.sync_from_settings()

    def _ensure_actions(self) -> None:
        if self._week_start:
            return
        p = self._parent
        for key, label in (("monday", "Monday"), ("sunday", "Sunday")):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_week_start(k))
            self._week_start[key] = act
        for key, label in (
            ("github_green", "Green"),
            ("ocean_blue", "Blue"),
            ("amber", "Amber"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_preset(k))
            self._preset[key] = act
        for key, label in (("auto", "Auto"), ("fixed", "Fixed max")):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_scale_mode(k))
            self._scale_mode[key] = act
        for n in CHOICES_COLOR_SCALE_MAX_FIXED:
            act = QAction(str(n), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=n: self._on_scale_fixed(v))
            self._scale_fixed[int(n)] = act
        for key, label in (
            ("exclude", "Full dates only"),
            ("include_stand_in", "Include partial-date stand-ins"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_partial(k))
            self._partial[key] = act
        for key, label in (
            ("trim_to_data", "Trim to activity"),
            ("rolling_12_months", "Last ~12 months"),
            ("rolling_24_months", "Last ~24 months"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_date_range(k))
            self._date_range[key] = act
        for key, label in (
            ("week_anchor", "Week-aligned"),
            ("calendar_mesh", "Calendar grid"),
            ("off", "Off"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_month_divider(k))
            self._month_divider[key] = act

    def _populate_tree(self, root: QMenu) -> None:
        mw = root.addMenu("Week starts on")
        self._style(mw)
        mw.addAction(self._week_start["monday"])
        mw.addAction(self._week_start["sunday"])
        mc = root.addMenu("Color scale")
        self._style(mc)
        mc.addAction(self._preset["github_green"])
        mc.addAction(self._preset["ocean_blue"])
        mc.addAction(self._preset["amber"])
        ms = root.addMenu("Intensity scale max")
        self._style(ms)
        ms.addAction(self._scale_mode["auto"])
        ms.addAction(self._scale_mode["fixed"])
        mf = ms.addMenu("Fixed cap (games)")
        self._style(mf)
        for n in CHOICES_COLOR_SCALE_MAX_FIXED:
            mf.addAction(self._scale_fixed[int(n)])
        mp = root.addMenu("Partial PGN dates")
        self._style(mp)
        mp.addAction(self._partial["exclude"])
        mp.addAction(self._partial["include_stand_in"])
        mr = root.addMenu("Date range")
        self._style(mr)
        mr.addAction(self._date_range["trim_to_data"])
        mr.addAction(self._date_range["rolling_12_months"])
        mr.addAction(self._date_range["rolling_24_months"])
        mm = root.addMenu("Dividers")
        self._style(mm)
        mm.addAction(self._month_divider["week_anchor"])
        mm.addAction(self._month_divider["calendar_mesh"])
        mm.addAction(self._month_divider["off"])

    def sync_from_settings(self) -> None:
        if not self._week_start:
            return
        s = UserSettingsService.get_instance().get_model().get_player_stats_activity_heatmap()
        w = str(s["week_starts_on"])
        for k, a in self._week_start.items():
            a.blockSignals(True)
            a.setChecked(k == w)
            a.blockSignals(False)
        pr = str(s["color_preset"])
        for k, a in self._preset.items():
            a.blockSignals(True)
            a.setChecked(k == pr)
            a.blockSignals(False)
        sm = str(s["color_scale_max_mode"])
        for k, a in self._scale_mode.items():
            a.blockSignals(True)
            a.setChecked(k == sm)
            a.blockSignals(False)
        sf = int(s["color_scale_max_fixed"])
        for n, a in self._scale_fixed.items():
            a.blockSignals(True)
            a.setChecked(n == sf)
            a.blockSignals(False)
        pd = str(s["partial_dates"])
        for k, a in self._partial.items():
            a.blockSignals(True)
            a.setChecked(k == pd)
            a.blockSignals(False)
        dr = str(s["date_range"])
        for k, a in self._date_range.items():
            a.blockSignals(True)
            a.setChecked(k == dr)
            a.blockSignals(False)
        md = str(s.get("month_divider_mode", "week_anchor"))
        if md not in VALID_MONTH_DIVIDER_MODE:
            md = "week_anchor"
        for k, a in self._month_divider.items():
            a.blockSignals(True)
            a.setChecked(k == md)
            a.blockSignals(False)

    def _on_week_start(self, key: str) -> None:
        for k, a in self._week_start.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap({"week_starts_on": key})

    def _on_preset(self, key: str) -> None:
        for k, a in self._preset.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap({"color_preset": key})

    def _on_scale_mode(self, key: str) -> None:
        for k, a in self._scale_mode.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap({"color_scale_max_mode": key})

    def _on_scale_fixed(self, value: int) -> None:
        for n, a in self._scale_fixed.items():
            a.blockSignals(True)
            a.setChecked(n == value)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap({"color_scale_max_fixed": value})

    def _on_partial(self, key: str) -> None:
        for k, a in self._partial.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap({"partial_dates": key})

    def _on_date_range(self, key: str) -> None:
        for k, a in self._date_range.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap({"date_range": key})

    def _on_month_divider(self, key: str) -> None:
        for k, a in self._month_divider.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_activity_heatmap(
            {"month_divider_mode": key}
        )

