"""Build QIcons from template SVGs tinted to match UI configuration.

Template assets use ``#ffffff`` fills (see ``app/resources/icons/*.svg``). At runtime
the color is substituted so icons align with menu / toolbar text colors without
duplicating assets per theme.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from app.utils.path_resolver import get_app_resource_path

# Template SVG paths (``#ffffff``); shared by menu bar and dark-styled context menus.
SVG_MENU_COPY = "app/resources/icons/copy_pgn.svg"
SVG_MENU_CUT = "app/resources/icons/cut_selected.svg"
SVG_MENU_PASTE_CLIPBOARD = "app/resources/icons/paste_clipboard_db.svg"
SVG_MENU_PASTE_ACTIVE_DB = "app/resources/icons/paste_active_db.svg"
# QTextEdit standard context menu (styled dark; use with :func:`menu_icon_tint_rgb`).
SVG_CONTEXT_UNDO = "app/resources/icons/context_undo.svg"
SVG_CONTEXT_REDO = "app/resources/icons/context_redo.svg"
SVG_CONTEXT_SELECT_ALL = "app/resources/icons/context_select_all.svg"
SVG_CONTEXT_DELETE = "app/resources/icons/context_delete.svg"
SVG_MENU_TAG_BUBBLE = "app/resources/icons/tag_bubble.svg"
SVG_MENU_BOOK = "app/resources/icons/menu_book.svg"
SVG_MENU_CHECKMARK = "app/resources/icons/checkmark.svg"
SVG_MENU_CLEAR_ALL_GAME_TAGS = "app/resources/icons/clear_all_game_tags.svg"
SVG_MENU_EYE_OFF = "app/resources/icons/eye_off.svg"
SVG_MENU_FOLDER_OPEN = "app/resources/icons/folder_open.svg"
SVG_MENU_GEAR = "app/resources/icons/menu_gear.svg"
SVG_MENU_INFO = "app/resources/icons/menu_info.svg"
SVG_MENU_KEYBOARD = "app/resources/icons/menu_keyboard.svg"
SVG_MENU_LAYERS = "app/resources/icons/menu_layers.svg"
SVG_MENU_MINUS = "app/resources/icons/menu_minus.svg"
SVG_MENU_TRASH = "app/resources/icons/menu_trash.svg"
SVG_MENU_PALETTE = "app/resources/icons/menu_palette.svg"
SVG_MENU_PLAY = "app/resources/icons/menu_play.svg"
SVG_MENU_PLUS = "app/resources/icons/menu_plus.svg"
SVG_MENU_DOWNLOAD = "app/resources/icons/menu_download.svg"
SVG_ZOOM_IN = "app/resources/icons/zoom_in.svg"
SVG_ZOOM_OUT = "app/resources/icons/zoom_out.svg"
SVG_MENU_RESET = "app/resources/icons/menu_reset.svg"
SVG_MENU_SEARCH = "app/resources/icons/menu_search.svg"
SVG_MENU_MAXIMIZE = "app/resources/icons/menu_maximize.svg"
SVG_MENU_RESTORE = "app/resources/icons/menu_restore.svg"
SVG_MENU_PENCIL = "app/resources/icons/pencil.svg"
SVG_MENU_EXCLAMATION = "app/resources/icons/menu_exclamation.svg"
SVG_MENU_SIZE_EQUAL = "app/resources/icons/menu_size_equal.svg"
SVG_MENU_SIZE_WIDTH = "app/resources/icons/menu_size_width.svg"
SVG_MENU_SIZE_HEIGHT = "app/resources/icons/menu_size_height.svg"
SVG_MENU_TEXT_SIZE = "app/resources/icons/menu_text_size.svg"
SVG_MENU_SAVE = "app/resources/icons/save_database.svg"
SVG_MENU_STOP = "app/resources/icons/menu_stop.svg"
SVG_MENU_FREEZE = "app/resources/icons/menu_freeze.svg"
SVG_MENU_VIDEO = "app/resources/icons/menu_video.svg"
SVG_SIMPLE_X = "app/resources/icons/x.svg"


def _rgb_from_config_list(value: Any) -> Tuple[int, int, int] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    return None


def menu_icon_tint_rgb(config: Dict[str, Any]) -> Tuple[int, int, int]:
    """RGB tint for menu / menubar icons from the active style config.

    Uses ``ui.menu.icons.tint_color`` if set, otherwise ``ui.menu.colors.normal.text``.
    Qt-drawn menus use the configured chrome colors; no OS light/dark remapping.
    """
    ui = config.get("ui", {})
    menu = ui.get("menu", {})
    icons_cfg = menu.get("icons", {})
    normal = menu.get("colors", {}).get("normal", {})
    text = normal.get("text", [200, 200, 200])
    tint = _rgb_from_config_list(icons_cfg.get("tint_color"))
    if tint is None:
        tint = (int(text[0]), int(text[1]), int(text[2]))
    return tint


# Alias kept for call sites that historically meant "dark chrome" icons.
menu_icon_dark_tint_rgb = menu_icon_tint_rgb


def _tint_svg_bytes(data: bytes, rgb: Tuple[int, int, int]) -> QByteArray:
    r, g, b = rgb
    hex_color = f"#{r:02x}{g:02x}{b:02x}"
    try:
        svg_str = data.decode("utf-8")
    except UnicodeDecodeError:
        return QByteArray()
    svg_str = svg_str.replace("#ffffff", hex_color).replace("#FFFFFF", hex_color)
    return QByteArray(svg_str.encode("utf-8"))


def themed_icon_from_svg(relative_path: str, rgb: Sequence[int]) -> QIcon:
    """Load an SVG from the app bundle, tint template white to ``rgb``, return a multi-size QIcon."""
    path = get_app_resource_path(relative_path)
    if not path.is_file():
        return QIcon()

    data = path.read_bytes()
    triplet = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    ba = _tint_svg_bytes(data, triplet)
    if ba.isEmpty():
        return QIcon()

    renderer = QSvgRenderer(ba)
    if not renderer.isValid():
        return QIcon()

    icon = QIcon()
    for size in (16, 20, 22, 24, 32):
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, float(size), float(size)))
        painter.end()
        icon.addPixmap(QPixmap.fromImage(img), QIcon.Mode.Normal, QIcon.State.Off)
    return icon


def set_menubar_themable_action_icon(mw: Any, action: Any, svg_path: str) -> None:
    """Assign a themed SVG icon for the menubar and register it for refresh on theme change."""
    if not hasattr(mw, "_menubar_action_icon_svgs"):
        mw._menubar_action_icon_svgs = {}
    mw._menubar_action_icon_svgs[action] = svg_path
    action.setIcon(themed_icon_from_svg(svg_path, menu_icon_tint_rgb(mw.config)))


def refresh_all_menubar_themable_action_icons(mw: Any) -> None:
    """Re-apply menubar tint to every action registered via :func:`set_menubar_themable_action_icon`."""
    reg: Dict[Any, str] = getattr(mw, "_menubar_action_icon_svgs", None) or {}
    if not reg:
        return
    tint = menu_icon_tint_rgb(mw.config)
    for action, svg_path in list(reg.items()):
        action.setIcon(themed_icon_from_svg(svg_path, tint))
