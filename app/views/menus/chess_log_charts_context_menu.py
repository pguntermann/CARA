"""Context menu builder for DetailChessLogChartsView."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QMenu


def build_chess_log_charts_context_menu(view, *, section_name: Optional[str]) -> QMenu:
    menu = QMenu(view)

    from app.views.style import StyleManager

    StyleManager.style_context_menu(menu, view._config)

    if section_name:
        copy_section = menu.addAction("Copy section to clipboard")
        copy_section.triggered.connect(
            lambda checked=False, name=section_name: view._copy_section_to_clipboard(name)
        )

    copy_log = menu.addAction("Copy log to clipboard")
    copy_log.triggered.connect(view._copy_log_to_clipboard)

    menu.addSeparator()
    export_pdf = menu.addAction("Export PDF Report")
    export_pdf.triggered.connect(view._export_pdf_report)

    export_narrative = menu.addAction("Export Narrative Summary")
    export_narrative.triggered.connect(view._export_narrative_pdf)

    from app.views.style.context_menu import try_wire_context_menu_shared_action_icons

    try_wire_context_menu_shared_action_icons(menu)
    return menu
