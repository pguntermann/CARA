"""Board menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import QMenuBar


def setup_board_menu(mw, menu_bar: QMenuBar) -> None:
    board_menu = menu_bar.addMenu("Board")
    mw._apply_menu_styling(board_menu)

    mw.rotate_action = QAction("Rotate Board", mw)
    mw.rotate_action.setShortcut(QKeySequence("X"))
    mw.rotate_action.setCheckable(True)
    mw.rotate_action.triggered.connect(mw.controller.rotate_board)
    board_menu.addAction(mw.rotate_action)

    board_menu.addSeparator()

    mw.game_info_action = QAction("Show Game Info", mw)
    mw.game_info_action.setShortcut(QKeySequence("Alt+I"))
    mw.game_info_action.setCheckable(True)
    mw.game_info_action.triggered.connect(mw.controller.toggle_game_info_visibility)
    board_menu.addAction(mw.game_info_action)

    mw.coordinates_action = QAction("Show Coordinates", mw)
    mw.coordinates_action.setShortcut(QKeySequence("Alt+C"))
    mw.coordinates_action.setCheckable(True)
    mw.coordinates_action.triggered.connect(mw.controller.toggle_coordinates_visibility)
    board_menu.addAction(mw.coordinates_action)

    mw.turn_indicator_action = QAction("Show Turn Indicator", mw)
    mw.turn_indicator_action.setShortcut(QKeySequence("Alt+T"))
    mw.turn_indicator_action.setCheckable(True)
    mw.turn_indicator_action.triggered.connect(mw.controller.toggle_turn_indicator_visibility)
    board_menu.addAction(mw.turn_indicator_action)

    mw.material_widget_action = QAction("Show Material", mw)
    mw.material_widget_action.setShortcut(QKeySequence("Alt+U"))
    mw.material_widget_action.setCheckable(True)
    mw.material_widget_action.triggered.connect(mw.controller.toggle_material_widget_visibility)
    board_menu.addAction(mw.material_widget_action)

    mw.game_tags_widget_action = QAction("Show Game Tags", mw)
    mw.game_tags_widget_action.setShortcut(QKeySequence("Alt+G"))
    mw.game_tags_widget_action.setCheckable(True)
    mw.game_tags_widget_action.triggered.connect(mw.controller.toggle_game_tags_widget_visibility)
    board_menu.addAction(mw.game_tags_widget_action)

    board_menu.addSeparator()

    mw.evaluation_bar_action = QAction("Show Evaluation Bar", mw)
    mw.evaluation_bar_action.setShortcut(QKeySequence("Alt+E"))
    mw.evaluation_bar_action.setCheckable(True)
    mw.evaluation_bar_action.triggered.connect(mw.controller.toggle_evaluation_bar_visibility)
    board_menu.addAction(mw.evaluation_bar_action)

    mw.positional_heatmap_action = QAction("Show Positional Heat-map", mw)
    mw.positional_heatmap_action.setShortcut(QKeySequence("Alt+H"))
    mw.positional_heatmap_action.setCheckable(True)
    mw.positional_heatmap_action.triggered.connect(mw.controller.toggle_positional_heatmap_visibility)
    board_menu.addAction(mw.positional_heatmap_action)

    board_menu.addSeparator()

    mw.playedmove_arrow_action = QAction("Show Played Move", mw)
    mw.playedmove_arrow_action.setShortcut(QKeySequence("Alt+P"))
    mw.playedmove_arrow_action.setCheckable(True)
    mw.playedmove_arrow_action.triggered.connect(mw.controller.toggle_playedmove_arrow_visibility)
    board_menu.addAction(mw.playedmove_arrow_action)

    mw.bestnextmove_arrow_action = QAction("Show Best Next Move", mw)
    mw.bestnextmove_arrow_action.setShortcut(QKeySequence("Alt+B"))
    mw.bestnextmove_arrow_action.setCheckable(True)
    mw.bestnextmove_arrow_action.triggered.connect(mw.controller.toggle_bestnextmove_arrow_visibility)
    board_menu.addAction(mw.bestnextmove_arrow_action)

    mw.pv2_arrow_action = QAction("Show Next Best Move (PV2)", mw)
    mw.pv2_arrow_action.setShortcut(QKeySequence("Alt+2"))
    mw.pv2_arrow_action.setCheckable(True)
    mw.pv2_arrow_action.triggered.connect(mw.controller.toggle_pv2_arrow_visibility)
    board_menu.addAction(mw.pv2_arrow_action)

    mw.pv3_arrow_action = QAction("Show Next Best Move (PV3)", mw)
    mw.pv3_arrow_action.setShortcut(QKeySequence("Alt+3"))
    mw.pv3_arrow_action.setCheckable(True)
    mw.pv3_arrow_action.triggered.connect(mw.controller.toggle_pv3_arrow_visibility)
    board_menu.addAction(mw.pv3_arrow_action)

    mw.bestalternativemove_arrow_action = QAction("Show Best Alternative Move", mw)
    mw.bestalternativemove_arrow_action.setShortcut(QKeySequence("Alt+A"))
    mw.bestalternativemove_arrow_action.setCheckable(True)
    mw.bestalternativemove_arrow_action.triggered.connect(
        mw.controller.toggle_bestalternativemove_arrow_visibility
    )
    board_menu.addAction(mw.bestalternativemove_arrow_action)

    mw.move_classification_icons_action = QAction("Show Move Classification Icons", mw)
    mw.move_classification_icons_action.setShortcut(QKeySequence("Alt+4"))
    mw.move_classification_icons_action.setCheckable(True)
    mw.move_classification_icons_action.triggered.connect(
        mw.controller.toggle_move_classification_icons_visibility
    )
    board_menu.addAction(mw.move_classification_icons_action)

    board_menu.addSeparator()

    mw.show_annotations_layer_action = QAction("Show Annotations Layer", mw)
    mw.show_annotations_layer_action.setShortcut(QKeySequence("Alt+L"))
    mw.show_annotations_layer_action.setCheckable(True)
    mw.show_annotations_layer_action.setChecked(True)
    mw.show_annotations_layer_action.triggered.connect(mw._on_show_annotations_layer_toggled)
    board_menu.addAction(mw.show_annotations_layer_action)

    board_menu.addSeparator()

    trajectory_style_menu = board_menu.addMenu("Path trajectory style")
    mw._apply_menu_styling(trajectory_style_menu)

    from app.services.user_settings_service import UserSettingsService

    user_settings = UserSettingsService.get_instance().get_settings()
    board_visibility = user_settings.get("board_visibility", {})
    use_straight_lines = board_visibility.get("use_straight_lines")
    if use_straight_lines is None:
        positional_plans_config = (
            mw.config.get("ui", {})
            .get("panels", {})
            .get("main", {})
            .get("board", {})
            .get("positional_plans", {})
        )
        use_straight_lines = positional_plans_config.get("use_straight_lines", False)

    mw.trajectory_style_straight_action = QAction("Straight", mw)
    mw.trajectory_style_straight_action.setCheckable(True)
    mw.trajectory_style_straight_action.setChecked(bool(use_straight_lines))
    mw.trajectory_style_straight_action.triggered.connect(
        lambda: mw._on_trajectory_style_selected(True)
    )
    trajectory_style_menu.addAction(mw.trajectory_style_straight_action)

    mw.trajectory_style_bezier_action = QAction("Bezier", mw)
    mw.trajectory_style_bezier_action.setCheckable(True)
    mw.trajectory_style_bezier_action.setChecked(not bool(use_straight_lines))
    mw.trajectory_style_bezier_action.triggered.connect(
        lambda: mw._on_trajectory_style_selected(False)
    )
    trajectory_style_menu.addAction(mw.trajectory_style_bezier_action)

    board_model = mw.controller.get_board_controller().get_board_model()
    board_model.flip_state_changed.connect(mw._on_board_flip_state_changed)
    board_model.coordinates_visibility_changed.connect(mw._on_coordinates_visibility_changed)
    board_model.turn_indicator_visibility_changed.connect(mw._on_turn_indicator_visibility_changed)
    board_model.game_info_visibility_changed.connect(mw._on_game_info_visibility_changed)
    board_model.playedmove_arrow_visibility_changed.connect(
        mw._on_playedmove_arrow_visibility_changed
    )
    board_model.bestnextmove_arrow_visibility_changed.connect(
        mw._on_bestnextmove_arrow_visibility_changed
    )
    board_model.bestalternativemove_arrow_visibility_changed.connect(
        mw._on_bestalternativemove_arrow_visibility_changed
    )
    board_model.move_classification_icons_visibility_changed.connect(
        mw._on_move_classification_icons_visibility_changed
    )
    board_model.evaluation_bar_visibility_changed.connect(mw._on_evaluation_bar_visibility_changed)
    board_model.material_widget_visibility_changed.connect(
        mw._on_material_widget_visibility_changed
    )
    board_model.game_tags_widget_visibility_changed.connect(
        mw._on_game_tags_widget_visibility_changed
    )

    mw._update_rotate_action_state(board_model.is_flipped)
    mw._update_coordinates_action_state(board_model.show_coordinates)
    mw._update_turn_indicator_action_state(board_model.show_turn_indicator)
    mw._update_game_info_action_state(board_model.show_game_info)
    mw._update_playedmove_arrow_action_state(board_model.show_playedmove_arrow)
    mw._update_bestnextmove_arrow_action_state(board_model.show_bestnextmove_arrow)
    mw._update_pv2_arrow_action_state(board_model.show_pv2_arrow)
    mw._update_pv3_arrow_action_state(board_model.show_pv3_arrow)
    mw._update_bestalternativemove_arrow_action_state(board_model.show_bestalternativemove_arrow)
    mw._update_move_classification_icons_action_state(board_model.show_move_classification_icons)
    mw._update_evaluation_bar_action_state(board_model.show_evaluation_bar)
    mw._update_material_widget_action_state(board_model.show_material_widget)
    mw._update_game_tags_widget_action_state(board_model.show_game_tags_widget)

    positional_heatmap_model = mw.controller.get_positional_heatmap_controller().get_model()
    positional_heatmap_model.visibility_changed.connect(mw._on_positional_heatmap_visibility_changed)
    mw._update_positional_heatmap_action_state(positional_heatmap_model.is_visible)

    board_menu.addSeparator()
    game_info_center_menu = board_menu.addMenu("Game Info center behaviour")
    mw._apply_menu_styling(game_info_center_menu)
    mw.game_info_center_mode_group = QActionGroup(mw)
    mw.game_info_center_mode_group.setExclusive(True)
    mw.game_info_center_in_view_action = QAction("Center in view", mw)
    mw.game_info_center_in_view_action.setCheckable(True)
    mw.game_info_center_in_view_action.triggered.connect(
        lambda: mw._on_game_info_center_mode_menu_triggered("center_in_view")
    )
    game_info_center_menu.addAction(mw.game_info_center_in_view_action)
    mw.game_info_center_mode_group.addAction(mw.game_info_center_in_view_action)

    mw.game_info_center_over_board_action = QAction("Center over board", mw)
    mw.game_info_center_over_board_action.setCheckable(True)
    mw.game_info_center_over_board_action.triggered.connect(
        lambda: mw._on_game_info_center_mode_menu_triggered("center_over_board")
    )
    game_info_center_menu.addAction(mw.game_info_center_over_board_action)
    mw.game_info_center_mode_group.addAction(mw.game_info_center_over_board_action)

    gic_mode = board_visibility.get("game_info_center_mode", "center_in_view")
    if gic_mode not in ("center_in_view", "center_over_board"):
        gic_mode = "center_in_view"
    mw.game_info_center_in_view_action.setChecked(gic_mode == "center_in_view")
    mw.game_info_center_over_board_action.setChecked(gic_mode == "center_over_board")
