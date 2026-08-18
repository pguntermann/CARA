"""Tab-bar scroll-button styling helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.utils.path_resolver import get_app_resource_path


def _rgb(value: Any, fallback: Sequence[int]) -> List[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [int(value[0]), int(value[1]), int(value[2])]
    return [int(fallback[0]), int(fallback[1]), int(fallback[2])]


def _qss_url(path: Path) -> str:
    return path.as_posix() if path.is_file() else ""


def generate_tab_bar_scroll_button_stylesheet(
    config: Dict[str, Any],
    background_color: Optional[List[int]] = None,
) -> str:
    """Return QSS that themes QTabBar overflow scroll buttons.

    Reads ``ui.styles.tab_bar_scroll_buttons``. ``background_color`` overrides
    the theme plate when a panel still supplies ``scroll_button_color``.
    Arrow artwork comes from theme-specific SVGs under ``icon_svg_path``.
    """
    styles_config = config.get("ui", {}).get("styles", {})
    cfg = styles_config.get("tab_bar_scroll_buttons", {})
    if not isinstance(cfg, dict):
        cfg = {}

    bg = _rgb(background_color if background_color is not None else cfg.get("background_color"), [30, 30, 30])
    hover_bg = _rgb(cfg.get("hover_background_color"), bg)
    pressed_bg = _rgb(cfg.get("pressed_background_color"), hover_bg)
    svg_dir = str(cfg.get("icon_svg_path", "app/resources/icons/tab_scroll/default"))
    svg_root = get_app_resource_path(svg_dir)
    scroller_width = int(cfg.get("scroller_width", 32))
    arrow_width = int(cfg.get("arrow_width", 20))
    arrow_height = int(cfg.get("arrow_height", 16))
    border_radius = int(cfg.get("border_radius", 0))

    left_url = _qss_url(svg_root / "left.svg")
    right_url = _qss_url(svg_root / "right.svg")
    left_disabled_url = _qss_url(svg_root / "left_disabled.svg") or left_url
    right_disabled_url = _qss_url(svg_root / "right_disabled.svg") or right_url

    arrow_rules = ""
    if left_url and right_url:
        arrow_rules = f"""
            QTabBar QToolButton::left-arrow {{
                image: url("{left_url}");
                width: {arrow_width}px;
                height: {arrow_height}px;
            }}
            QTabBar QToolButton::right-arrow {{
                image: url("{right_url}");
                width: {arrow_width}px;
                height: {arrow_height}px;
            }}
            QTabBar QToolButton::left-arrow:disabled {{
                image: url("{left_disabled_url}");
            }}
            QTabBar QToolButton::right-arrow:disabled {{
                image: url("{right_disabled_url}");
            }}
        """

    return f"""
            QTabBar::scroller {{
                width: {scroller_width}px;
            }}
            QTabBar::tear {{
                width: 0px;
                border: none;
                background: none;
            }}
            QTabBar QToolButton {{
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                border: none;
                border-radius: {border_radius}px;
                padding: 0px;
            }}
            QTabBar QToolButton:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
            }}
            QTabBar QToolButton:pressed {{
                background-color: rgb({pressed_bg[0]}, {pressed_bg[1]}, {pressed_bg[2]});
            }}
            QTabBar QToolButton:disabled {{
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
            }}
            {arrow_rules}
        """
