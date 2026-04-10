"""Engines menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenu, QMenuBar

from app.utils.themed_icon import (
    SVG_MENU_GEAR,
    SVG_MENU_PLUS,
    SVG_SIMPLE_X,
    set_menubar_themable_action_icon,
)


def setup_engines_menu(mw, menu_bar: QMenuBar) -> None:
    engines_menu = menu_bar.addMenu("Engines")
    mw._apply_menu_styling(engines_menu)

    add_engine_action = QAction("Add Engine...", mw)
    add_engine_action.setShortcut(QKeySequence("Ctrl+E"))
    add_engine_action.setMenuRole(QAction.MenuRole.NoRole)
    set_menubar_themable_action_icon(mw, add_engine_action, SVG_MENU_PLUS)
    add_engine_action.triggered.connect(mw._add_engine)
    engines_menu.addAction(add_engine_action)

    engines_menu.addSeparator()

    mw.engine_submenus = {}
    mw.no_engines_action = None

    engine_model = mw.controller.get_engine_controller().get_engine_model()
    engine_model.engine_added.connect(mw._on_engine_added)
    engine_model.engine_removed.connect(mw._on_engine_removed)
    engine_model.engines_changed.connect(mw._update_engines_menu)
    engine_model.assignment_changed.connect(mw._update_engines_menu)

    mw.engines_menu = engines_menu
    mw.engine_model = engine_model

    mw._update_engines_menu()


def rebuild_engines_menu(mw) -> None:
    """Rebuild the Engines menu with current engines and assignments."""
    from app.controllers.engine_controller import (
        TASK_BRILLIANCY_DETECTION,
        TASK_EVALUATION,
        TASK_GAME_ANALYSIS,
        TASK_MANUAL_ANALYSIS,
    )

    menu = mw.engines_menu

    reg = getattr(mw, "_menubar_action_icon_svgs", None)
    if reg and mw.engine_submenus:
        for submenu in list(mw.engine_submenus.values()):
            for act in submenu.actions():
                reg.pop(act, None)

    # Clear existing engine submenus (keep "Add Engine..." and separator)
    for submenu in list(mw.engine_submenus.values()):
        menu.removeAction(submenu.menuAction())
    mw.engine_submenus.clear()

    # Remove "no engines" placeholder if it exists
    if mw.no_engines_action is not None:
        menu.removeAction(mw.no_engines_action)
        mw.no_engines_action = None

    engines = mw.engine_model.get_engines()
    if not engines:
        if mw.no_engines_action is None:
            mw.no_engines_action = QAction("(No engines configured)", mw)
            mw.no_engines_action.setEnabled(False)
            menu.addAction(mw.no_engines_action)
        return

    engine_controller = mw.controller.get_engine_controller()
    game_analysis_id = engine_controller.get_engine_assignment(TASK_GAME_ANALYSIS)
    evaluation_id = engine_controller.get_engine_assignment(TASK_EVALUATION)
    manual_analysis_id = engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
    brilliancy_detection_id = engine_controller.get_engine_assignment(TASK_BRILLIANCY_DETECTION)

    for engine in engines:
        engine_submenu = QMenu(engine.name, mw)
        mw._apply_menu_styling(engine_submenu)

        remove_action = QAction("Remove Engine", mw)
        set_menubar_themable_action_icon(mw, remove_action, SVG_SIMPLE_X)
        remove_action.triggered.connect(lambda checked, eid=engine.id: mw._remove_engine(eid))
        engine_submenu.addAction(remove_action)

        config_action = QAction("Engine Configuration", mw)
        set_menubar_themable_action_icon(mw, config_action, SVG_MENU_GEAR)
        config_action.triggered.connect(
            lambda checked, eid=engine.id: mw._open_engine_configuration(eid)
        )
        engine_submenu.addAction(config_action)

        engine_submenu.addSeparator()

        set_all_action = QAction("Set for all tasks", mw)
        set_all_action.setToolTip(
            "Assign this engine to Game Analysis, Evaluation, Manual Analysis, and Brilliancy Detection"
        )
        set_all_action.triggered.connect(lambda checked, eid=engine.id: mw._set_engine_for_all_tasks(eid))
        engine_submenu.addAction(set_all_action)
        engine_submenu.addSeparator()

        game_analysis_action = QAction("Set as Game Analysis Engine", mw)
        game_analysis_action.setCheckable(True)
        game_analysis_action.setChecked(game_analysis_id == engine.id)
        game_analysis_action.triggered.connect(
            lambda checked, eid=engine.id: mw._set_engine_assignment(TASK_GAME_ANALYSIS, eid)
        )
        engine_submenu.addAction(game_analysis_action)

        evaluation_action = QAction("Set as Evaluation Engine", mw)
        evaluation_action.setCheckable(True)
        evaluation_action.setChecked(evaluation_id == engine.id)
        evaluation_action.triggered.connect(
            lambda checked, eid=engine.id: mw._set_engine_assignment(TASK_EVALUATION, eid)
        )
        engine_submenu.addAction(evaluation_action)

        manual_analysis_action = QAction("Set as Manual Analysis Engine", mw)
        manual_analysis_action.setCheckable(True)
        manual_analysis_action.setChecked(manual_analysis_id == engine.id)
        manual_analysis_action.triggered.connect(
            lambda checked, eid=engine.id: mw._set_engine_assignment(TASK_MANUAL_ANALYSIS, eid)
        )
        engine_submenu.addAction(manual_analysis_action)

        brilliancy_detection_action = QAction("Set as Brilliancy Detection Engine", mw)
        brilliancy_detection_action.setCheckable(True)
        brilliancy_detection_action.setChecked(brilliancy_detection_id == engine.id)
        brilliancy_detection_action.triggered.connect(
            lambda checked, eid=engine.id: mw._set_engine_assignment(TASK_BRILLIANCY_DETECTION, eid)
        )
        engine_submenu.addAction(brilliancy_detection_action)

        menu.addMenu(engine_submenu)
        mw.engine_submenus[engine.id] = engine_submenu

