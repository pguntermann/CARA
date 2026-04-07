"""Player Stats menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QMenuBar

from app.views.menus.player_stats_accuracy_distribution_menu import (
    PlayerStatsAccuracyDistributionMenuController,
)
from app.views.menus.player_stats_activity_heatmap_menu import PlayerStatsActivityHeatmapMenuController
from app.views.menus.player_stats_time_series_menu import PlayerStatsTimeSeriesMenuController


def setup_player_stats_menu(mw, menu_bar: QMenuBar) -> None:
    """Menu to show/hide Player Stats tab sections (persisted in user settings)."""
    from app.services.user_settings_service import UserSettingsService
    from app.views.detail_player_stats_view import PLAYER_STATS_MENU_SECTIONS

    ps_menu = menu_bar.addMenu("Player Stats")
    mw._apply_menu_styling(ps_menu)
    mw.player_stats_menu = ps_menu
    mw._player_stats_section_actions = {}

    reset_ps_defaults = QAction("Reset to defaults", mw)
    reset_ps_defaults.setMenuRole(QAction.MenuRole.NoRole)
    reset_ps_defaults.triggered.connect(mw._on_player_stats_reset_to_template_defaults)
    ps_menu.addAction(reset_ps_defaults)
    ps_menu.addSeparator()

    enable_all_ps = QAction("Enable all", mw)
    enable_all_ps.setMenuRole(QAction.MenuRole.NoRole)
    enable_all_ps.triggered.connect(mw._on_player_stats_menu_enable_all)
    ps_menu.addAction(enable_all_ps)

    disable_all_ps = QAction("Disable all", mw)
    disable_all_ps.setMenuRole(QAction.MenuRole.NoRole)
    disable_all_ps.triggered.connect(mw._on_player_stats_menu_disable_all)
    ps_menu.addAction(disable_all_ps)
    ps_menu.addSeparator()

    vis = UserSettingsService.get_instance().get_model().get_player_stats_section_visibility()
    sections = list(PLAYER_STATS_MENU_SECTIONS)
    idx_ov = next(i for i, (sid, _) in enumerate(sections) if sid == "overview")
    idx_ah = next(i for i, (sid, _) in enumerate(sections) if sid == "activity_heatmap")
    idx_ad = next(i for i, (sid, _) in enumerate(sections) if sid == "accuracy_distribution")
    idx_acpl = next(i for i, (sid, _) in enumerate(sections) if sid == "acpl_phase_progression")

    def _add_player_stats_section_visibility_actions(pairs: list) -> None:
        for section_id, label in pairs:
            if section_id == "accuracy_progression":
                ps_menu.addSeparator()
            act = QAction(label, mw)
            act.setCheckable(True)
            act.setMenuRole(QAction.MenuRole.NoRole)
            act.setChecked(bool(vis.get(section_id, True)))
            act.triggered.connect(
                lambda checked, sid=section_id: mw._on_player_stats_section_menu_toggled(sid, checked)
            )
            ps_menu.addAction(act)
            mw._player_stats_section_actions[section_id] = act
            if section_id == "endgame_tree":
                ps_menu.addSeparator()

    _add_player_stats_section_visibility_actions([sections[idx_ov]])
    ps_menu.addSeparator()
    _add_player_stats_section_visibility_actions([sections[idx_ah]])
    _setup_player_stats_activity_heatmap_submenu(mw, ps_menu)
    ps_menu.addSeparator()
    _add_player_stats_section_visibility_actions([sections[idx_ad]])
    _setup_player_stats_accuracy_distribution_submenu(mw, ps_menu)
    ps_menu.addSeparator()
    _add_player_stats_section_visibility_actions(sections[idx_ad + 1 : idx_acpl + 1])
    _setup_player_stats_time_series_submenu(mw, ps_menu)
    ps_menu.addSeparator()
    _add_player_stats_section_visibility_actions(sections[idx_acpl + 1 :])


def _setup_player_stats_time_series_submenu(mw, ps_menu: QMenu) -> None:
    from app.services.user_settings_service import UserSettingsService

    mw._ps_ts_menu_controller = PlayerStatsTimeSeriesMenuController(mw, mw._apply_menu_styling)
    mw.player_stats_time_series_menu = mw._ps_ts_menu_controller.attach_to_parent_menu(ps_menu)
    UserSettingsService.get_instance().get_model().player_stats_time_series_changed.connect(
        mw._ps_ts_menu_controller.sync_from_settings
    )


def _setup_player_stats_activity_heatmap_submenu(mw, ps_menu: QMenu) -> None:
    from app.services.user_settings_service import UserSettingsService

    mw._ps_ah_menu_controller = PlayerStatsActivityHeatmapMenuController(mw, mw._apply_menu_styling)
    mw.player_stats_activity_heatmap_menu = mw._ps_ah_menu_controller.attach_to_parent_menu(ps_menu)
    UserSettingsService.get_instance().get_model().player_stats_activity_heatmap_changed.connect(
        mw._ps_ah_menu_controller.sync_from_settings
    )


def _setup_player_stats_accuracy_distribution_submenu(mw, ps_menu: QMenu) -> None:
    from app.services.user_settings_service import UserSettingsService

    mw._ps_ad_menu_controller = PlayerStatsAccuracyDistributionMenuController(mw, mw._apply_menu_styling)
    mw.player_stats_accuracy_distribution_menu = mw._ps_ad_menu_controller.attach_to_parent_menu(ps_menu)
    UserSettingsService.get_instance().get_model().player_stats_accuracy_distribution_changed.connect(
        mw._ps_ad_menu_controller.sync_from_settings
    )

