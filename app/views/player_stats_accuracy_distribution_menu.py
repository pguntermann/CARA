"""Player Stats accuracy distribution chart settings (menubar + context menu)."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from app.services.player_stats_accuracy_distribution_user import (
    CHOICES_DISTRIBUTION_LINE_SMOOTH_STRENGTH,
)
from app.services.user_settings_service import UserSettingsService

PLAYER_STATS_ACCURACY_DISTRIBUTION_CONTEXT_SECTIONS: frozenset[str] = frozenset(
    {"Accuracy Distribution"}
)


class PlayerStatsAccuracyDistributionMenuController:
    """Nested \"Accuracy distribution settings\" menu for one host (menubar or context)."""

    def __init__(self, action_parent, style_submenu: Callable[[QMenu], None]) -> None:
        self._parent = action_parent
        self._style = style_submenu
        self.top_menu: Optional[QMenu] = None
        self._skew: Dict[str, QAction] = {}
        self._yaxis: Dict[str, QAction] = {}
        self._bins: Dict[str, QAction] = {}
        self._preset: Dict[str, QAction] = {}
        self._curve_smooth: Optional[QAction] = None
        self._curve_straight: Optional[QAction] = None
        self._smooth_strength: Dict[float, QAction] = {}

    def attach_to_parent_menu(self, parent_menu: QMenu) -> QMenu:
        self.top_menu = parent_menu.addMenu("Accuracy distribution settings")
        self._style(self.top_menu)
        self._ensure_actions()
        self._populate_tree(self.top_menu)
        self.sync_from_settings()
        return self.top_menu

    def append_to_context_menu(self, context_menu: QMenu) -> None:
        ad_menu = context_menu.addMenu("Accuracy distribution settings")
        self._style(ad_menu)
        self._ensure_actions()
        self._populate_tree(ad_menu)
        self.sync_from_settings()

    def _ensure_actions(self) -> None:
        if self._skew:
            return
        p = self._parent
        for key, label in (
            ("linear", "Linear"),
            ("high_accuracy_skew", "High Accuracy Skew"),
            ("very_high_accuracy_skew", "Very High Accuracy Skew"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_skew(k))
            self._skew[key] = act
        for key, label in (
            ("count", "Number of games"),
            ("percent_of_games", "Share of games (%)"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_yaxis(k))
            self._yaxis[key] = act
        for key, label in (
            ("auto", "Automatic"),
            ("fewer", "Fewer bars"),
            ("more", "More bars"),
        ):
            act = QAction(label, p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, k=key: self._on_bins(k))
            self._bins[key] = act
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
        self._curve_smooth = QAction("Smooth", p)
        self._curve_smooth.setCheckable(True)
        self._curve_smooth.setMenuRole(QAction.MenuRole.NoRole)
        self._curve_smooth.triggered.connect(lambda _c=False: self._on_curve("smooth"))
        self._curve_straight = QAction("Straight segments", p)
        self._curve_straight.setCheckable(True)
        self._curve_straight.setMenuRole(QAction.MenuRole.NoRole)
        self._curve_straight.triggered.connect(lambda _c=False: self._on_curve("straight"))
        for x in CHOICES_DISTRIBUTION_LINE_SMOOTH_STRENGTH:
            act = QAction(str(x), p)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.triggered.connect(lambda _c=False, v=x: self._on_smooth_strength(float(v)))
            self._smooth_strength[float(x)] = act

    def _populate_tree(self, root: QMenu) -> None:
        ms = root.addMenu("Accuracy scale")
        self._style(ms)
        for k in ("linear", "high_accuracy_skew", "very_high_accuracy_skew"):
            ms.addAction(self._skew[k])
        my = root.addMenu("Vertical axis")
        self._style(my)
        my.addAction(self._yaxis["count"])
        my.addAction(self._yaxis["percent_of_games"])
        mb = root.addMenu("Bar count")
        self._style(mb)
        for k in ("auto", "fewer", "more"):
            mb.addAction(self._bins[k])
        mc = root.addMenu("Colors")
        self._style(mc)
        for k in ("github_green", "ocean_blue", "amber"):
            mc.addAction(self._preset[k])
        mcrv = root.addMenu("Distribution line curve")
        self._style(mcrv)
        assert self._curve_smooth and self._curve_straight
        mcrv.addAction(self._curve_smooth)
        mcrv.addAction(self._curve_straight)
        mss = root.addMenu("Distribution smoothing strength")
        self._style(mss)
        for x in CHOICES_DISTRIBUTION_LINE_SMOOTH_STRENGTH:
            mss.addAction(self._smooth_strength[float(x)])

    def sync_from_settings(self) -> None:
        if not self._skew:
            return
        s = UserSettingsService.get_instance().get_model().get_player_stats_accuracy_distribution()
        sk = str(s.get("skew_mode", "high_accuracy_skew"))
        for k, a in self._skew.items():
            a.blockSignals(True)
            a.setChecked(k == sk)
            a.blockSignals(False)
        ya = str(s.get("y_axis_mode", "count"))
        for k, a in self._yaxis.items():
            a.blockSignals(True)
            a.setChecked(k == ya)
            a.blockSignals(False)
        bd = str(s.get("bin_density", "auto"))
        for k, a in self._bins.items():
            a.blockSignals(True)
            a.setChecked(k == bd)
            a.blockSignals(False)
        pr = str(s.get("color_preset", "github_green"))
        for k, a in self._preset.items():
            a.blockSignals(True)
            a.setChecked(k == pr)
            a.blockSignals(False)

        crv = str(s.get("distribution_line_curve", "smooth"))
        assert self._curve_smooth and self._curve_straight
        self._curve_smooth.blockSignals(True)
        self._curve_straight.blockSignals(True)
        self._curve_smooth.setChecked(crv == "smooth")
        self._curve_straight.setChecked(crv == "straight")
        self._curve_smooth.blockSignals(False)
        self._curve_straight.blockSignals(False)

        ss = float(s.get("distribution_line_smooth_strength", 1.0))
        for x, a in self._smooth_strength.items():
            a.blockSignals(True)
            a.setChecked(abs(x - ss) < 1e-9)
            a.blockSignals(False)

    def _on_skew(self, key: str) -> None:
        for k, a in self._skew.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_accuracy_distribution({"skew_mode": key})

    def _on_yaxis(self, key: str) -> None:
        for k, a in self._yaxis.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_accuracy_distribution({"y_axis_mode": key})

    def _on_bins(self, key: str) -> None:
        for k, a in self._bins.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_accuracy_distribution({"bin_density": key})

    def _on_preset(self, key: str) -> None:
        for k, a in self._preset.items():
            a.blockSignals(True)
            a.setChecked(k == key)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_accuracy_distribution({"color_preset": key})

    def _on_curve(self, curve: str) -> None:
        assert self._curve_smooth and self._curve_straight
        self._curve_smooth.blockSignals(True)
        self._curve_straight.blockSignals(True)
        self._curve_smooth.setChecked(curve == "smooth")
        self._curve_straight.setChecked(curve == "straight")
        self._curve_smooth.blockSignals(False)
        self._curve_straight.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_accuracy_distribution(
            {"distribution_line_curve": curve}
        )

    def _on_smooth_strength(self, value: float) -> None:
        for x, a in self._smooth_strength.items():
            a.blockSignals(True)
            a.setChecked(abs(x - value) < 1e-9)
            a.blockSignals(False)
        UserSettingsService.get_instance().update_player_stats_accuracy_distribution(
            {"distribution_line_smooth_strength": value}
        )
