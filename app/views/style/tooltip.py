"""Tooltip styling helpers."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def apply_tooltip_styling(app: QApplication, config: Dict[str, Any]) -> None:
    """Apply QToolTip stylesheet to the QApplication (application-wide).

    Note: On some platforms (notably macOS), Qt may still draw a thin native
    square frame around a border-radius tip. Masking that frame is not
    reliably cross-compatible, so we accept it and only style colors/padding.
    """
    tooltip_config = config.get("ui", {}).get("styles", {}).get("tooltip", {})

    bg_color = tooltip_config.get("background_color", [45, 45, 50])
    text_color = tooltip_config.get("text_color", [220, 220, 220])
    border_color = tooltip_config.get("border_color", [60, 60, 65])
    border_width = int(tooltip_config.get("border_width", 1))
    border_radius = int(tooltip_config.get("border_radius", 5))
    padding = int(tooltip_config.get("padding", 10))

    tooltip_stylesheet = f"""
        QToolTip {{
            background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
            color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
            border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
            border-radius: {border_radius}px;
            padding: {padding}px;
        }}
    """

    # Replace any previous QToolTip block rather than appending duplicates on theme switch.
    existing = app.styleSheet() or ""
    marker_start = "/* CARA_TOOLTIP_STYLE_START */"
    marker_end = "/* CARA_TOOLTIP_STYLE_END */"
    if marker_start in existing and marker_end in existing:
        before, rest = existing.split(marker_start, 1)
        _, after = rest.split(marker_end, 1)
        existing = before.rstrip() + after.lstrip()
    app.setStyleSheet(
        (existing + "\n" if existing.strip() else "")
        + f"{marker_start}\n{tooltip_stylesheet}\n{marker_end}\n"
    )

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(*bg_color))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(*text_color))
    app.setPalette(palette)
