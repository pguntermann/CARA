"""Tooltip styling helpers."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def _tooltip_colors(config: Dict[str, Any]) -> tuple[list[int], list[int], list[int], int, int, int]:
    """Resolve tooltip colors/geometry from ``ui.styles.tooltip``."""
    tooltip_config = config.get("ui", {}).get("styles", {}).get("tooltip", {})
    bg_color = tooltip_config.get("background_color", [45, 45, 50])
    text_color = tooltip_config.get("text_color", [220, 220, 220])
    border_color = tooltip_config.get("border_color", [60, 60, 65])
    if not isinstance(bg_color, list) or len(bg_color) < 3:
        bg_color = [45, 45, 50]
    if not isinstance(text_color, list) or len(text_color) < 3:
        text_color = [220, 220, 220]
    if not isinstance(border_color, list) or len(border_color) < 3:
        border_color = [60, 60, 65]
    border_width = int(tooltip_config.get("border_width", 1))
    border_radius = int(tooltip_config.get("border_radius", 5))
    padding = int(tooltip_config.get("padding", 10))
    return bg_color, text_color, border_color, border_width, border_radius, padding


def tooltip_qss_block(config: Dict[str, Any]) -> str:
    """Return a ``QToolTip { … }`` QSS block from theme config.

    Embed this in widget-local stylesheets when those stylesheets would otherwise
    override the application-wide tooltip theme.
    """
    bg, fg, border, border_width, border_radius, padding = _tooltip_colors(config)
    return (
        f"QToolTip {{"
        f"background-color: rgb({int(bg[0])}, {int(bg[1])}, {int(bg[2])});"
        f"color: rgb({int(fg[0])}, {int(fg[1])}, {int(fg[2])});"
        f"border: {border_width}px solid rgb({int(border[0])}, {int(border[1])}, {int(border[2])});"
        f"border-radius: {border_radius}px;"
        f"padding: {padding}px;"
        f"}}"
    )


def apply_tooltip_styling(app: QApplication, config: Dict[str, Any]) -> None:
    """Apply QToolTip stylesheet to the QApplication (application-wide).

    Note: On some platforms (notably macOS), Qt may still draw a thin native
    square frame around a border-radius tip. Masking that frame is not
    reliably cross-compatible, so we accept it and only style colors/padding.
    """
    bg_color, text_color, _, _, _, _ = _tooltip_colors(config)
    tooltip_stylesheet = tooltip_qss_block(config)

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
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(*bg_color[:3]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(*text_color[:3]))
    app.setPalette(palette)
