"""Menu bar and menu styling helpers."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtWidgets import QMenu, QMenuBar

from app.utils.font_utils import resolve_font_family, scale_font_size


def apply_menu_bar_styling(menu_bar: QMenuBar, config: Dict[str, Any]) -> None:
    """Apply styling to the menu bar based on configuration."""
    ui_config = config.get("ui", {})
    menu_config = ui_config.get("menu", {})

    font_family = resolve_font_family(menu_config.get("font_family", "Helvetica Neue"))
    font_size = scale_font_size(menu_config.get("font_size", 10))

    colors_config = menu_config.get("colors", {})
    normal = colors_config.get("normal", {})
    hover = colors_config.get("hover", {})

    norm_bg = normal.get("background", [45, 45, 50])
    norm_text = normal.get("text", [200, 200, 200])
    hover_bg = hover.get("background", [55, 55, 60])
    hover_text = hover.get("text", [230, 230, 230])

    menu_spacing = menu_config.get("spacing", 4)
    menu_bar_config = menu_config.get("menu_bar", {})
    menu_bar_item_padding = menu_bar_config.get("item_padding", [4, 8])

    menu_config_obj = menu_config.get("menu", {})
    menu_border_width = menu_config_obj.get("border_width", 1)
    menu_border_color = menu_config_obj.get("border_color", [60, 60, 65])
    menu_item_padding = menu_config_obj.get("item_padding", [4, 20, 4, 8])

    separator_config = menu_config.get("separator", {})
    separator_height = separator_config.get("height", 1)
    separator_bg_color = separator_config.get("background_color", [60, 60, 65])
    separator_margin = separator_config.get("margin", [2, 4])

    stylesheet = f"""
        QMenuBar {{
            background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
            color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
            font-family: "{font_family}";
            font-size: {font_size}pt;
            spacing: {menu_spacing}px;
        }}

        QMenuBar::item {{
            background-color: transparent;
            padding: {menu_bar_item_padding[0]}px {menu_bar_item_padding[1]}px;
        }}

        QMenuBar::item:selected {{
            background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
            color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
        }}

        QMenuBar::item:pressed {{
            background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
        }}

        QMenu {{
            background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
            color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
            border: {menu_border_width}px solid rgb({menu_border_color[0]}, {menu_border_color[1]}, {menu_border_color[2]});
            font-family: "{font_family}";
            font-size: {font_size}pt;
        }}

        QMenu::item {{
            padding: {menu_item_padding[0]}px {menu_item_padding[1]}px {menu_item_padding[2]}px {menu_item_padding[3]}px;
        }}

        QMenu::item:selected {{
            background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
            color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
        }}

        QMenu::separator {{
            height: {separator_height}px;
            background-color: rgb({separator_bg_color[0]}, {separator_bg_color[1]}, {separator_bg_color[2]});
            margin: {separator_margin[0]}px {separator_margin[1]}px;
        }}
    """

    menu_bar.setStyleSheet(stylesheet)


def apply_menu_styling(menu: QMenu, config: Dict[str, Any]) -> None:
    """Apply styling to a submenu QMenu based on configuration."""
    ui_config = config.get("ui", {})
    menu_config = ui_config.get("menu", {})

    font_family = resolve_font_family(menu_config.get("font_family", "Helvetica Neue"))
    font_size = scale_font_size(menu_config.get("font_size", 10))

    colors_config = menu_config.get("colors", {})
    normal = colors_config.get("normal", {})
    hover = colors_config.get("hover", {})

    norm_bg = normal.get("background", [45, 45, 50])
    norm_text = normal.get("text", [200, 200, 200])
    hover_bg = hover.get("background", [55, 55, 60])
    hover_text = hover.get("text", [230, 230, 230])

    menu_config_obj = menu_config.get("menu", {})
    menu_border_width = menu_config_obj.get("border_width", 1)
    menu_border_color = menu_config_obj.get("border_color", [60, 60, 65])
    menu_item_padding = menu_config_obj.get("item_padding", [4, 20, 4, 8])

    separator_config = menu_config.get("separator", {})
    separator_height = separator_config.get("height", 1)
    separator_bg_color = separator_config.get("background_color", [60, 60, 65])
    separator_margin = separator_config.get("margin", [2, 4])

    stylesheet = f"""
        QMenu {{
            background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
            color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
            border: {menu_border_width}px solid rgb({menu_border_color[0]}, {menu_border_color[1]}, {menu_border_color[2]});
            font-family: "{font_family}";
            font-size: {font_size}pt;
        }}
        QMenu::item {{
            padding: {menu_item_padding[0]}px {menu_item_padding[1]}px {menu_item_padding[2]}px {menu_item_padding[3]}px;
        }}
        QMenu::item:selected {{
            background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
            color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
        }}
        QMenu::separator {{
            height: {separator_height}px;
            background-color: rgb({separator_bg_color[0]}, {separator_bg_color[1]}, {separator_bg_color[2]});
            margin: {separator_margin[0]}px {separator_margin[1]}px;
        }}
    """

    menu.setStyleSheet(stylesheet)

