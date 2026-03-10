"""Tree view styling helpers for consistent cross-platform appearance."""

from typing import Dict, Any, List

from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtWidgets import QTreeWidget, QHeaderView

from app.utils.font_utils import resolve_font_family, scale_font_size


def apply_tree_view_styling(
    tree_views: List[QTreeWidget],
    config: Dict[str, Any],
    tree_style_key: str = "tree_view",
) -> None:
    """Apply unified styling to one or more QTreeWidget instances.

    The styling parameters are read from config['ui']['styles'][tree_style_key].
    """
    styles_config = config.get("ui", {}).get("styles", {})
    tree_config = styles_config.get(tree_style_key, {})

    # Colors
    text_color = tree_config.get("text_color", [220, 220, 220])
    header_text_color = tree_config.get("header_text_color", text_color)
    background_color = tree_config.get("background_color", [35, 35, 40])
    alt_background_color = tree_config.get("alternate_background_color", [40, 40, 45])
    grid_color = tree_config.get("grid_color", [60, 60, 65])
    selection_bg = tree_config.get("selection_background_color", [70, 90, 130])
    selection_text = tree_config.get("selection_text_color", [240, 240, 240])

    # Fonts
    font_family_raw = tree_config.get("font_family", "Helvetica Neue")
    header_font_family_raw = tree_config.get("header_font_family", font_family_raw)
    font_size_raw = tree_config.get("font_size", 11)
    header_font_size_raw = tree_config.get("header_font_size", font_size_raw)

    font_family = resolve_font_family(font_family_raw)
    header_font_family = resolve_font_family(header_font_family_raw)
    font_size = scale_font_size(font_size_raw)
    header_font_size = scale_font_size(header_font_size_raw)

    row_height = tree_config.get("row_height")
    header_min_height = tree_config.get("header_min_height")
    show_grid = bool(tree_config.get("show_grid", False))
    show_focus_rect = bool(tree_config.get("show_focus_rect", True))

    base_font = QFont(font_family, int(font_size))
    header_font = QFont(header_font_family, int(header_font_size))

    for tree in tree_views:
        if tree is None:
            continue

        tree.setFont(base_font)
        header = tree.header()
        if header is not None:
            header.setFont(header_font)
            if header_min_height is not None:
                header.setMinimumHeight(int(header_min_height))
            header.setHighlightSections(False)

        text_qcolor = QColor(*text_color)
        palette = tree.palette()
        # Ensure generic and platform text roles use our light text color
        palette.setColor(tree.foregroundRole(), text_qcolor)
        palette.setColor(QPalette.ColorRole.Text, text_qcolor)
        palette.setColor(QPalette.ColorRole.WindowText, text_qcolor)
        palette.setColor(QPalette.ColorRole.ButtonText, text_qcolor)
        palette.setColor(QPalette.ColorRole.BrightText, text_qcolor)
        palette.setColor(tree.backgroundRole(), QColor(*background_color))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(*alt_background_color))
        tree.setPalette(palette)

        # Build stylesheet primarily for header, grid lines and selection.
        grid_rgb = f"rgb({grid_color[0]}, {grid_color[1]}, {grid_color[2]})"
        header_text_rgb = (
            f"rgb({header_text_color[0]}, {header_text_color[1]}, {header_text_color[2]})"
        )
        bg_rgb = f"rgb({background_color[0]}, {background_color[1]}, {background_color[2]})"
        alt_bg_rgb = f"rgb({alt_background_color[0]}, {alt_background_color[1]}, {alt_background_color[2]})"
        sel_bg_rgb = f"rgb({selection_bg[0]}, {selection_bg[1]}, {selection_bg[2]})"
        sel_text_rgb = f"rgb({selection_text[0]}, {selection_text[1]}, {selection_text[2]})"

        parts = [
            "QTreeWidget {",
            f"  background-color: {bg_rgb};",
            f"  alternate-background-color: {alt_bg_rgb};",
            "  border: none;",
            "}",
            "QTreeWidget::item {",
            f"  color: {sel_text_rgb};",
            "  padding: 2px 4px;",
            "}",
            "QTreeWidget::item:selected {",
            f"  background-color: {sel_bg_rgb};",
            f"  color: {sel_text_rgb};",
            "}",
            "QHeaderView::section {",
            f"  color: {header_text_rgb};",
            f"  background-color: {bg_rgb};",
            f"  border-bottom: 1px solid {grid_rgb};",
            f"  border-right: 1px solid {grid_rgb};",
            "  padding: 2px 4px;",
            "}",
        ]

        if not show_focus_rect:
            parts.extend(
                [
                    "QTreeWidget::item:focus {",
                    "  outline: none;",
                    "}",
                ]
            )

        if show_grid:
            parts.extend(
                [
                    "QTreeView {",
                    f"  gridline-color: {grid_rgb};",
                    "}",
                ]
            )

        stylesheet = "\n".join(parts)
        existing = tree.styleSheet()
        if existing:
            stylesheet = existing + "\n" + stylesheet
        tree.setStyleSheet(stylesheet)

        if row_height is not None:
            tree.setUniformRowHeights(True)
            tree.setStyleSheet(
                stylesheet
                + f"\nQTreeWidget::item {{ height: {int(row_height)}px; }}"
            )

