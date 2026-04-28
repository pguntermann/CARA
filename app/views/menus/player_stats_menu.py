"""Player Stats menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QMenuBar

from app.utils.themed_icon import (
    SVG_MENU_CHECKMARK,
    SVG_MENU_EYE_OFF,
    SVG_MENU_RESET,
    set_menubar_themable_action_icon,
)
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
    mw._player_stats_profile_actions = {}

    # Rebuild once and keep in sync via settings signals.
    svc = UserSettingsService.get_instance()
    model = svc.get_model()
    model.player_stats_profiles_changed.connect(mw._update_player_stats_menu)
    model.player_stats_active_profile_changed.connect(lambda _name: mw._update_player_stats_menu())

    mw._update_player_stats_menu()

    # Keep section checkmarks synced when the controller updates them programmatically.
    try:
        mw.controller.get_menu_options_sync_controller().sync_player_stats_from_settings()
    except Exception:
        pass


def rebuild_player_stats_menu(mw) -> None:
    """Rebuild Player Stats menu (profiles + section visibility + submenus)."""
    from app.services.user_settings_service import UserSettingsService
    from app.views.detail_player_stats_view import PLAYER_STATS_MENU_SECTIONS

    menu = mw.player_stats_menu
    reg = getattr(mw, "_menubar_action_icon_svgs", None)
    if reg:
        for act in menu.actions():
            reg.pop(act, None)
    menu.clear()

    mw._player_stats_section_actions.clear()
    mw._player_stats_profile_actions.clear()

    svc = UserSettingsService.get_instance()
    model = svc.get_model()
    ps_profile_controller = mw.controller.get_player_stats_profile_controller()
    profile_names = ps_profile_controller.get_profile_names()
    active_profile = ps_profile_controller.get_active_profile_name()

    # Profile toggle actions at top.
    for profile_name in profile_names:
        act = QAction(profile_name, mw)
        act.setCheckable(True)
        act.setMenuRole(QAction.MenuRole.NoRole)
        act.setChecked(profile_name == active_profile)
        act.triggered.connect(lambda checked=False, name=profile_name: mw._on_player_stats_profile_selected(name))
        menu.addAction(act)
        mw._player_stats_profile_actions[profile_name] = act

    if profile_names:
        menu.addSeparator()

    save_profile_action = QAction("Save Profile", mw)
    save_profile_action.setMenuRole(QAction.MenuRole.NoRole)
    save_profile_action.triggered.connect(mw._save_player_stats_profile)
    menu.addAction(save_profile_action)

    save_profile_as_action = QAction("Save Profile as...", mw)
    save_profile_as_action.setMenuRole(QAction.MenuRole.NoRole)
    save_profile_as_action.triggered.connect(mw._save_player_stats_profile_as)
    menu.addAction(save_profile_as_action)

    remove_profile_action = QAction("Remove Profile", mw)
    remove_profile_action.setMenuRole(QAction.MenuRole.NoRole)
    remove_profile_action.setEnabled(active_profile != "Default")
    remove_profile_action.triggered.connect(mw._remove_player_stats_profile)
    menu.addAction(remove_profile_action)

    menu.addSeparator()

    reset_ps_defaults = QAction("Reset to defaults", mw)
    reset_ps_defaults.setMenuRole(QAction.MenuRole.NoRole)
    set_menubar_themable_action_icon(mw, reset_ps_defaults, SVG_MENU_RESET)
    reset_ps_defaults.triggered.connect(mw._on_player_stats_reset_to_template_defaults)
    menu.addAction(reset_ps_defaults)
    menu.addSeparator()

    enable_all_ps = QAction("Enable all", mw)
    enable_all_ps.setMenuRole(QAction.MenuRole.NoRole)
    set_menubar_themable_action_icon(mw, enable_all_ps, SVG_MENU_CHECKMARK)
    enable_all_ps.triggered.connect(
        lambda checked=False: mw.controller.get_menu_options_sync_controller().set_all_player_stats_sections_visible(True)
    )
    menu.addAction(enable_all_ps)

    disable_all_ps = QAction("Disable all", mw)
    disable_all_ps.setMenuRole(QAction.MenuRole.NoRole)
    set_menubar_themable_action_icon(mw, disable_all_ps, SVG_MENU_EYE_OFF)
    disable_all_ps.triggered.connect(
        lambda checked=False: mw.controller.get_menu_options_sync_controller().set_all_player_stats_sections_visible(False)
    )
    menu.addAction(disable_all_ps)
    menu.addSeparator()

    vis = model.get_player_stats_section_visibility()
    sections = list(PLAYER_STATS_MENU_SECTIONS)
    idx_ov = next(i for i, (sid, _) in enumerate(sections) if sid == "overview")
    idx_ah = next(i for i, (sid, _) in enumerate(sections) if sid == "activity_heatmap")
    idx_ad = next(i for i, (sid, _) in enumerate(sections) if sid == "accuracy_distribution")
    idx_acpl = next(i for i, (sid, _) in enumerate(sections) if sid == "acpl_phase_progression")

    def _add_player_stats_section_visibility_actions(pairs: list) -> None:
        for section_id, label in pairs:
            if section_id == "accuracy_progression":
                menu.addSeparator()
            act2 = QAction(label, mw)
            act2.setCheckable(True)
            act2.setMenuRole(QAction.MenuRole.NoRole)
            act2.setChecked(bool(vis.get(section_id, True)))
            menu.addAction(act2)
            mw._player_stats_section_actions[section_id] = act2
            if section_id == "endgame_tree":
                menu.addSeparator()

    _add_player_stats_section_visibility_actions([sections[idx_ov]])
    menu.addSeparator()
    _add_player_stats_section_visibility_actions([sections[idx_ah]])
    _setup_player_stats_activity_heatmap_submenu(mw, menu)
    menu.addSeparator()
    _add_player_stats_section_visibility_actions([sections[idx_ad]])
    _setup_player_stats_accuracy_distribution_submenu(mw, menu)
    menu.addSeparator()
    _add_player_stats_section_visibility_actions(sections[idx_ad + 1 : idx_acpl + 1])
    _setup_player_stats_time_series_submenu(mw, menu)
    menu.addSeparator()
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

