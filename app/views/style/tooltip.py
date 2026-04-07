"""Tooltip styling helpers."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtWidgets import QApplication


def apply_tooltip_styling(app: QApplication, config: Dict[str, Any]) -> None:
    """Apply QToolTip stylesheet to the QApplication instance (application-wide)."""
    tooltip_config = config.get("ui", {}).get("styles", {}).get("tooltip", {})

    bg_color = tooltip_config.get("background_color", [45, 45, 50])
    text_color = tooltip_config.get("text_color", [220, 220, 220])
    border_color = tooltip_config.get("border_color", [60, 60, 65])
    border_width = tooltip_config.get("border_width", 1)
    border_radius = tooltip_config.get("border_radius", 5)
    padding = tooltip_config.get("padding", 10)

    tooltip_stylesheet = f"""
        QToolTip {{
            background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
            color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
            border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
            border-radius: {border_radius}px;
            padding: {padding}px;
        }}
    """

    existing_stylesheet = app.styleSheet()
    if existing_stylesheet:
        app.setStyleSheet(existing_stylesheet + "\n" + tooltip_stylesheet)
    else:
        app.setStyleSheet(tooltip_stylesheet)

