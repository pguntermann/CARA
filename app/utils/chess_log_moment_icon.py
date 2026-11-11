"""Themed QIcon provider for the Chess Log 'logged moment' Moves List marker.

Builds two QIcons from ``chess_log_moment.svg`` tinted with the Moves List's
own theme colors (normal move text; active-move row text). Each QIcon also
carries a ``QIcon.Mode.Selected`` pixmap tinted with the Moves List's
selection text color, so Qt's default delegate automatically swaps tint
when the row is selected. On theme change ``apply_theme`` rebuilds the
DetailPanel, which recreates the model and installs a fresh provider — the
cache is therefore implicitly rebuilt from the new config.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from app.utils.path_resolver import get_app_resource_path
from app.utils.themed_icon import SVG_CHESS_LOG_MOMENT

_ICON_SIZES: Tuple[int, ...] = (12, 14, 16, 20, 24)


def _rgb_or_default(value: Any, default: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    return default


def _dig(d: Any, *path: str, default: Any = None) -> Any:
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _resolve_colors(config: Dict[str, Any]) -> Dict[str, Tuple[int, int, int]]:
    """Pull the three Moves List text colors we tint against.

    Matches the keys read by ``DetailMovesListView._configure_table_styling``.
    """
    ui = config.get("ui", {}) if isinstance(config, dict) else {}
    normal = _rgb_or_default(
        _dig(ui, "panels", "detail", "tabs", "colors", "normal", "text"),
        (200, 200, 200),
    )
    table = _dig(ui, "panels", "detail", "moveslist", "table", default={}) or {}
    selected = _rgb_or_default(table.get("selection_text_color"), (240, 240, 240))
    active = _rgb_or_default(
        _dig(table, "active_move", "text_color"),
        (255, 255, 255),
    )
    return {"normal": normal, "selected": selected, "active": active}


def _tint_svg_bytes(data: bytes, rgb: Tuple[int, int, int]) -> QByteArray:
    r, g, b = rgb
    hex_color = f"#{r:02x}{g:02x}{b:02x}"
    s = data.decode("utf-8")
    s = s.replace("#ffffff", hex_color).replace("#FFFFFF", hex_color)
    return QByteArray(s.encode("utf-8"))


def _build_icon(svg_bytes: bytes,
                normal_rgb: Tuple[int, int, int],
                selected_rgb: Tuple[int, int, int]) -> QIcon:
    icon = QIcon()
    for mode, rgb in ((QIcon.Mode.Normal, normal_rgb),
                      (QIcon.Mode.Selected, selected_rgb),
                      (QIcon.Mode.Active, normal_rgb)):
        ba = _tint_svg_bytes(svg_bytes, rgb)
        renderer = QSvgRenderer(ba)
        if not renderer.isValid():
            continue
        for size in _ICON_SIZES:
            img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, float(size), float(size)))
            painter.end()
            icon.addPixmap(QPixmap.fromImage(img), mode, QIcon.State.Off)
    return icon


class ChessLogMomentIconProvider:
    """Holds two tinted QIcons — one for normal rows, one for the current-move row.

    Each icon ships Normal + Selected mode pixmaps so Qt's default delegate
    picks the right tint on selection without a custom paint path.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._colors = _resolve_colors(config)
        svg_path = get_app_resource_path(SVG_CHESS_LOG_MOMENT)
        svg_bytes = svg_path.read_bytes() if svg_path.is_file() else b""
        self._icon_normal = _build_icon(
            svg_bytes, self._colors["normal"], self._colors["selected"]
        )
        self._icon_active = _build_icon(
            svg_bytes, self._colors["active"], self._colors["selected"]
        )

    def icon_for_row(self, *, is_current_move_row: bool) -> QIcon:
        return self._icon_active if is_current_move_row else self._icon_normal

    def colors(self) -> Dict[str, Tuple[int, int, int]]:
        return dict(self._colors)
