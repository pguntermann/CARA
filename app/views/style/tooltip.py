"""Tooltip styling helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

Rgb = Tuple[int, int, int]


@dataclass(frozen=True)
class TooltipStyle:
    """Theme values for native ``QToolTip`` and the linked-move popup."""

    background: Rgb
    text: Rgb
    border: Rgb
    border_width: int
    border_radius: int
    padding: int
    font_family: str
    font_size: int
    title_color: Rgb
    title_font_size: int
    title_font_weight: str
    muted_color: Rgb
    separator_color: Rgb
    caret_size: int
    anchor_gap: int
    hover_delay_ms: int
    show_position_board: bool
    position_board_size: int
    played_move_arrow_color: Rgb
    show_best_alternative_arrow: bool
    best_alternative_arrow_color: Rgb


def _rgb(value: Any, fallback: Rgb) -> Rgb:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _int(value: Any, fallback: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return fallback


def _text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback


def _bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def load_tooltip_style(config: Dict[str, Any]) -> TooltipStyle:
    """Resolve ``ui.styles.tooltip`` into a single style object."""
    raw = config.get("ui", {}).get("styles", {}).get("tooltip", {})
    if not isinstance(raw, dict):
        raw = {}
    background = _rgb(raw.get("background_color"), (45, 45, 50))
    text = _rgb(raw.get("text_color"), (220, 220, 220))
    border = _rgb(raw.get("border_color"), (60, 60, 65))
    return TooltipStyle(
        background=background,
        text=text,
        border=border,
        border_width=_int(raw.get("border_width"), 1, minimum=0),
        border_radius=_int(raw.get("border_radius"), 5, minimum=0),
        padding=_int(raw.get("padding"), 10, minimum=0),
        font_family=_text(raw.get("font_family"), "Helvetica Neue"),
        font_size=_int(raw.get("font_size"), 11, minimum=8),
        title_color=_rgb(raw.get("title_color"), text),
        title_font_size=_int(raw.get("title_font_size"), 13, minimum=8),
        title_font_weight=_text(raw.get("title_font_weight"), "bold"),
        muted_color=_rgb(raw.get("muted_color"), text),
        separator_color=_rgb(raw.get("separator_color"), border),
        caret_size=_int(raw.get("caret_size"), 8, minimum=4),
        anchor_gap=_int(raw.get("anchor_gap"), 4, minimum=0),
        hover_delay_ms=_int(raw.get("hover_delay_ms"), 300, minimum=0),
        show_position_board=_bool(raw.get("show_position_board"), True),
        position_board_size=_int(raw.get("position_board_size"), 112, minimum=48),
        played_move_arrow_color=_rgb(raw.get("played_move_arrow_color"), (255, 255, 0)),
        show_best_alternative_arrow=_bool(raw.get("show_best_alternative_arrow"), True),
        best_alternative_arrow_color=_rgb(raw.get("best_alternative_arrow_color"), (200, 0, 100)),
    )


def tooltip_qss_block(config: Dict[str, Any]) -> str:
    """Return a ``QToolTip { … }`` QSS block from theme config.

    Embed this in widget-local stylesheets when those stylesheets would otherwise
    override the application-wide tooltip theme.
    """
    style = load_tooltip_style(config)
    bg, fg, border = style.background, style.text, style.border
    return (
        f"QToolTip {{"
        f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});"
        f"color: rgb({fg[0]}, {fg[1]}, {fg[2]});"
        f"border: {style.border_width}px solid rgb({border[0]}, {border[1]}, {border[2]});"
        f"border-radius: {style.border_radius}px;"
        f"padding: {style.padding}px;"
        f"}}"
    )


def apply_tooltip_styling(app: QApplication, config: Dict[str, Any]) -> None:
    """Apply QToolTip stylesheet to the QApplication (application-wide).

    Note: On some platforms (notably macOS), Qt may still draw a thin native
    square frame around a border-radius tip. Masking that frame is not
    reliably cross-compatible, so we accept it and only style colors/padding.
    Linked-move tips use a custom popup instead of ``QToolTip``.
    """
    style = load_tooltip_style(config)
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
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(*style.background))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(*style.text))
    app.setPalette(palette)
