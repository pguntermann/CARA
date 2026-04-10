"""Build QIcons from template SVGs tinted to match UI configuration.

Template assets use ``#ffffff`` fills (see ``app/resources/icons/*.svg``). At runtime
the color is substituted so icons align with menu / toolbar text colors without
duplicating assets per theme.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Sequence, Tuple

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from app.utils.path_resolver import get_app_resource_path

# Default icon tint when Qt reports a light system color scheme (e.g. native macOS menu bar).
_DEFAULT_LIGHT_SCHEME_ICON_TINT: Tuple[int, int, int] = (52, 52, 58)

# Template SVG paths (``#ffffff``); shared by menu bar and dark-styled context menus.
SVG_MENU_COPY = "app/resources/icons/copy_pgn.svg"
SVG_MENU_CUT = "app/resources/icons/cut_selected.svg"
SVG_MENU_PASTE_CLIPBOARD = "app/resources/icons/paste_clipboard_db.svg"
SVG_MENU_PASTE_ACTIVE_DB = "app/resources/icons/paste_active_db.svg"
# QTextEdit standard context menu (styled dark; use with :func:`menu_icon_dark_tint_rgb`).
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
SVG_MENU_LAYERS = "app/resources/icons/menu_layers.svg"
SVG_MENU_MINUS = "app/resources/icons/menu_minus.svg"
SVG_MENU_PLAY = "app/resources/icons/menu_play.svg"
SVG_MENU_PLUS = "app/resources/icons/menu_plus.svg"
SVG_MENU_RESET = "app/resources/icons/menu_reset.svg"
SVG_MENU_SAVE = "app/resources/icons/save_database.svg"
SVG_MENU_STOP = "app/resources/icons/menu_stop.svg"
SVG_MENU_VIDEO = "app/resources/icons/menu_video.svg"
SVG_SIMPLE_X = "app/resources/icons/x.svg"


def _rgb_from_config_list(value: Any) -> Tuple[int, int, int] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    return None


def _is_qt_light_color_scheme() -> bool | None:
    """True if Qt reports light, False if dark, None if unknown or unavailable."""
    app = QGuiApplication.instance()
    if app is None:
        return None
    sh = app.styleHints()
    try:
        cs = sh.colorScheme()
    except AttributeError:
        return None
    if cs == Qt.ColorScheme.Light:
        return True
    if cs == Qt.ColorScheme.Dark:
        return False
    return None


def menu_icon_dark_tint_rgb(config: Dict[str, Any]) -> Tuple[int, int, int]:
    """RGB tint for icons on surfaces that stay dark regardless of OS theme.

    Uses ``ui.menu.icons.tint_color`` if set, otherwise ``ui.menu.colors.normal.text``.
    Context menus that apply a dark stylesheet should use this instead of
    :func:`menu_icon_tint_rgb` so icons match that chrome, not a light menu bar.
    """
    ui = config.get("ui", {})
    menu = ui.get("menu", {})
    icons_cfg = menu.get("icons", {})
    normal = menu.get("colors", {}).get("normal", {})
    text = normal.get("text", [200, 200, 200])
    dark_tint = _rgb_from_config_list(icons_cfg.get("tint_color"))
    if dark_tint is None:
        dark_tint = (int(text[0]), int(text[1]), int(text[2]))
    return dark_tint


def menu_icon_tint_rgb(config: Dict[str, Any]) -> Tuple[int, int, int]:
    """Resolve [R, G, B] for menubar menu icons from config and Qt color scheme.

    On **macOS**, when ``QStyleHints.colorScheme()`` is ``Light``, uses
    ``ui.menu.icons.tint_color_light_scheme`` (or a dark neutral default) so glyphs
    stay visible on a **native light** menu bar.

    On **Linux and Windows**, Qt often reports ``Light`` while CARA still paints the
    menu bar with the configured **dark** stylesheet (``ui.menu.colors``). Using the
    light-scheme tint there makes icons nearly the same RGB as the bar (e.g. manage
    tags vs. open folder perceived contrast). Those platforms always use the same tint
    as :func:`menu_icon_dark_tint_rgb` for the menubar.

    For ``Dark`` or ``Unknown`` on macOS, uses ``ui.menu.icons.tint_color`` if set,
    otherwise ``ui.menu.colors.normal.text``.
    """
    dark_tint = menu_icon_dark_tint_rgb(config)

    if sys.platform != "darwin":
        return dark_tint

    ui = config.get("ui", {})
    menu = ui.get("menu", {})
    icons_cfg = menu.get("icons", {})

    light_tint = _rgb_from_config_list(icons_cfg.get("tint_color_light_scheme"))
    if light_tint is None:
        light_tint = _DEFAULT_LIGHT_SCHEME_ICON_TINT

    scheme = _is_qt_light_color_scheme()
    if scheme is True:
        return light_tint
    return dark_tint


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
    """Assign a themed SVG icon for the menubar and register it for context-menu re-tinting.

    Icons on shared menubar actions are tinted for the OS color scheme. Any root
    context menu that calls :func:`app.views.style.context_menu.try_wire_context_menu_shared_action_icons`
    temporarily switches registered actions to :func:`menu_icon_dark_tint_rgb` while open.
    """
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
