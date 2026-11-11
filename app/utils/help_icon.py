"""Factory for a reusable ⓘ help button."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QToolButton

from app.utils.themed_icon import SVG_MENU_INFO, themed_icon_from_svg


def make_help_icon(
    config: Dict[str, Any],
    tooltip: str,
    text_color: List[int],
    on_click: Optional[Callable] = None,
) -> QToolButton:
    """Return a small ⓘ QToolButton styled for the given text color."""
    btn = QToolButton()
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAutoRaise(True)
    btn.setFixedSize(22, 22)
    btn.setIconSize(QSize(16, 16))
    icon = themed_icon_from_svg(SVG_MENU_INFO, text_color)
    r, g, b = text_color
    color_rgb = f"rgb({r},{g},{b})"
    if icon.isNull():
        btn.setText("ⓘ")
        btn.setStyleSheet(
            f"QToolButton {{ color: {color_rgb}; background: transparent; border: none; padding: 0px; }}"
            f"QToolButton:hover {{ background: transparent; }}"
        )
    else:
        btn.setIcon(icon)
        btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
            "QToolButton:hover { background: transparent; }"
        )
    if on_click:
        btn.clicked.connect(on_click)
    return btn
