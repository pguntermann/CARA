"""Manual Analysis menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.themed_icon import (
    SVG_MENU_MINUS,
    SVG_MENU_PLAY,
    SVG_MENU_PLUS,
    set_menubar_themable_action_icon,
)


def setup_manual_analysis_menu(mw, menu_bar: QMenuBar) -> None:
    manual_analysis_menu = menu_bar.addMenu("Manual Analysis")
    mw._apply_menu_styling(manual_analysis_menu)

    mw.start_manual_analysis_action = QAction("Start Manual Analysis", mw)
    mw.start_manual_analysis_action.setShortcut(QKeySequence("Alt+M"))
    set_menubar_themable_action_icon(mw, mw.start_manual_analysis_action, SVG_MENU_PLAY)
    mw.start_manual_analysis_action.triggered.connect(mw._on_start_manual_analysis_toggled)
    manual_analysis_menu.addAction(mw.start_manual_analysis_action)

    manual_analysis_menu.addSeparator()

    mw.add_pv_line_action = QAction("Add PV Line", mw)
    mw.add_pv_line_action.setShortcut(QKeySequence("Alt+N"))
    set_menubar_themable_action_icon(mw, mw.add_pv_line_action, SVG_MENU_PLUS)
    mw.add_pv_line_action.triggered.connect(mw._on_add_pv_line)
    manual_analysis_menu.addAction(mw.add_pv_line_action)

    mw.remove_pv_line_action = QAction("Remove PV Line", mw)
    mw.remove_pv_line_action.setShortcut(QKeySequence("Alt+R"))
    set_menubar_themable_action_icon(mw, mw.remove_pv_line_action, SVG_MENU_MINUS)
    mw.remove_pv_line_action.triggered.connect(mw._on_remove_pv_line)
    manual_analysis_menu.addAction(mw.remove_pv_line_action)

    manual_analysis_menu.addSeparator()

    mw.enable_miniature_preview_action = QAction("Enable miniature preview", mw)
    mw.enable_miniature_preview_action.setCheckable(True)
    mw.enable_miniature_preview_action.setChecked(True)
    mw.enable_miniature_preview_action.triggered.connect(mw._on_enable_miniature_preview_toggled)
    manual_analysis_menu.addAction(mw.enable_miniature_preview_action)

    mw.miniature_preview_scale_menu = manual_analysis_menu.addMenu(
        "Set miniature preview scale factor"
    )
    mw._apply_menu_styling(mw.miniature_preview_scale_menu)
    scale_factors = [1.0, 1.25, 1.5, 1.75, 2.0]
    mw.miniature_preview_scale_actions = {}
    for scale in scale_factors:
        action = QAction(f"{scale}x", mw)
        action.setCheckable(True)
        action.setData(scale)
        action.triggered.connect(
            lambda checked, s=scale: mw._on_miniature_preview_scale_factor_selected(s)
        )
        mw.miniature_preview_scale_menu.addAction(action)
        mw.miniature_preview_scale_actions[scale] = action

    manual_analysis_menu.addSeparator()

    mw.explore_pv1_plans_action = QAction("Explore PV1 Positional Plans", mw)
    mw.explore_pv1_plans_action.setCheckable(True)
    mw.explore_pv1_plans_action.setChecked(False)
    mw.explore_pv1_plans_action.triggered.connect(mw._on_explore_pv1_plans_toggled)
    manual_analysis_menu.addAction(mw.explore_pv1_plans_action)

    mw.explore_pv2_plans_action = QAction("Explore PV2 Positional Plans", mw)
    mw.explore_pv2_plans_action.setCheckable(True)
    mw.explore_pv2_plans_action.setChecked(False)
    mw.explore_pv2_plans_action.triggered.connect(mw._on_explore_pv2_plans_toggled)
    manual_analysis_menu.addAction(mw.explore_pv2_plans_action)

    mw.explore_pv3_plans_action = QAction("Explore PV3 Positional Plans", mw)
    mw.explore_pv3_plans_action.setCheckable(True)
    mw.explore_pv3_plans_action.setChecked(False)
    mw.explore_pv3_plans_action.triggered.connect(mw._on_explore_pv3_plans_toggled)
    manual_analysis_menu.addAction(mw.explore_pv3_plans_action)

    max_pieces_menu = manual_analysis_menu.addMenu("Max number of pieces to explore")
    mw._apply_menu_styling(max_pieces_menu)

    from app.services.user_settings_service import UserSettingsService

    user_settings = UserSettingsService.get_instance().get_settings()
    manual_analysis_settings = user_settings.get("manual_analysis", {})
    max_pieces = manual_analysis_settings.get("max_pieces_to_explore", 1)

    mw.max_pieces_1_action = QAction("1", mw)
    mw.max_pieces_1_action.setCheckable(True)
    mw.max_pieces_1_action.setChecked(max_pieces == 1)
    mw.max_pieces_1_action.triggered.connect(lambda: mw._on_max_pieces_selected(1))
    max_pieces_menu.addAction(mw.max_pieces_1_action)

    mw.max_pieces_2_action = QAction("2", mw)
    mw.max_pieces_2_action.setCheckable(True)
    mw.max_pieces_2_action.setChecked(max_pieces == 2)
    mw.max_pieces_2_action.triggered.connect(lambda: mw._on_max_pieces_selected(2))
    max_pieces_menu.addAction(mw.max_pieces_2_action)

    mw.max_pieces_3_action = QAction("3", mw)
    mw.max_pieces_3_action.setCheckable(True)
    mw.max_pieces_3_action.setChecked(max_pieces == 3)
    mw.max_pieces_3_action.triggered.connect(lambda: mw._on_max_pieces_selected(3))
    max_pieces_menu.addAction(mw.max_pieces_3_action)

    max_depth_menu = manual_analysis_menu.addMenu("Max Exploration depth")
    mw._apply_menu_styling(max_depth_menu)

    max_depth = manual_analysis_settings.get("max_exploration_depth", 2)

    mw.max_depth_2_action = QAction("2", mw)
    mw.max_depth_2_action.setCheckable(True)
    mw.max_depth_2_action.setChecked(max_depth == 2)
    mw.max_depth_2_action.triggered.connect(lambda: mw._on_max_exploration_depth_selected(2))
    max_depth_menu.addAction(mw.max_depth_2_action)

    mw.max_depth_3_action = QAction("3", mw)
    mw.max_depth_3_action.setCheckable(True)
    mw.max_depth_3_action.setChecked(max_depth == 3)
    mw.max_depth_3_action.triggered.connect(lambda: mw._on_max_exploration_depth_selected(3))
    max_depth_menu.addAction(mw.max_depth_3_action)

    mw.max_depth_4_action = QAction("4", mw)
    mw.max_depth_4_action.setCheckable(True)
    mw.max_depth_4_action.setChecked(max_depth == 4)
    mw.max_depth_4_action.triggered.connect(lambda: mw._on_max_exploration_depth_selected(4))
    max_depth_menu.addAction(mw.max_depth_4_action)

    board_visibility = user_settings.get("board_visibility", {})
    hide_other_arrows = board_visibility.get("hide_other_arrows_during_plan_exploration", False)

    mw.hide_other_arrows_during_plan_exploration_action = QAction(
        "Hide other arrows during plan exploration", mw
    )
    mw.hide_other_arrows_during_plan_exploration_action.setCheckable(True)
    mw.hide_other_arrows_during_plan_exploration_action.setChecked(hide_other_arrows)
    mw.hide_other_arrows_during_plan_exploration_action.triggered.connect(
        mw._on_hide_other_arrows_during_plan_exploration_toggled
    )
    manual_analysis_menu.addAction(mw.hide_other_arrows_during_plan_exploration_action)

    mw.manual_analysis_menu = manual_analysis_menu

    manual_analysis_controller = mw.controller.get_manual_analysis_controller()
    manual_analysis_model = manual_analysis_controller.get_analysis_model()
    manual_analysis_model.is_analyzing_changed.connect(mw._on_manual_analysis_state_changed)
    manual_analysis_model.lines_changed.connect(mw._on_manual_analysis_lines_changed)

    mw._update_manual_analysis_action_states(manual_analysis_model.is_analyzing, manual_analysis_model.multipv)

