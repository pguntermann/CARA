"""Themed dialog corner resize grip (cross-platform, not OS chrome)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from PyQt6.QtCore import QEvent, QPoint, Qt, QRectF
from PyQt6.QtGui import QPainter, QPaintEvent, QPixmap, QImage
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QDialog, QSizeGrip, QWidget

from app.utils.path_resolver import get_app_resource_path
from app.utils.themed_icon import _tint_svg_bytes


SVG_DIALOG_RESIZE_GRIP = "app/resources/icons/dialog_resize_grip.svg"


def _rgb(value: Any, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    return fallback


def dialog_resize_grip_config(config: Dict[str, Any]) -> Dict[str, Any]:
    styles = (config.get("ui") or {}).get("styles") or {}
    cfg = styles.get("dialog_resize_grip") or {}
    return cfg if isinstance(cfg, dict) else {}


class ThemedDialogSizeGrip(QSizeGrip):
    """QSizeGrip that paints a theme-tinted SVG instead of the native grip."""

    def __init__(self, parent: QWidget, config: Dict[str, Any]) -> None:
        super().__init__(parent)
        self._config = config
        grip_cfg = dialog_resize_grip_config(config)
        self._size = max(8, int(grip_cfg.get("size", 16)))
        self._margin = max(0, int(grip_cfg.get("margin", 4)))
        tint = _rgb(grip_cfg.get("tint_color"), (150, 150, 150))
        svg_path = str(grip_cfg.get("svg_path") or SVG_DIALOG_RESIZE_GRIP)
        self._pixmap = self._render_pixmap(svg_path, tint, self._size)
        self.setFixedSize(self._size, self._size)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Resize")
        parent.installEventFilter(self)
        self._reposition()
        self.raise_()
        self.show()

    @staticmethod
    def _render_pixmap(
        relative_path: str,
        tint: Sequence[int],
        size: int,
    ) -> QPixmap:
        path = get_app_resource_path(relative_path)
        if not path.is_file():
            return QPixmap()
        ba = _tint_svg_bytes(path.read_bytes(), (int(tint[0]), int(tint[1]), int(tint[2])))
        if ba.isEmpty():
            return QPixmap()
        renderer = QSvgRenderer(ba)
        if not renderer.isValid():
            return QPixmap()
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, float(size), float(size)))
        painter.end()
        return QPixmap.fromImage(img)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(
            parent.width() - self.width() - self._margin,
            parent.height() - self.height() - self._margin,
        )
        self.raise_()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(QPoint(0, 0), self._pixmap)


def install_themed_dialog_resize_grip(
    dialog: QDialog,
    config: Dict[str, Any],
) -> Optional[ThemedDialogSizeGrip]:
    """Attach a themed corner resize grip to a user-resizable dialog.

    No-op when ``ui.styles.dialog_resize_grip.enabled`` is false.
    """
    grip_cfg = dialog_resize_grip_config(config)
    if not bool(grip_cfg.get("enabled", True)):
        return None
    existing = getattr(dialog, "_cara_themed_resize_grip", None)
    if isinstance(existing, ThemedDialogSizeGrip):
        return existing
    grip = ThemedDialogSizeGrip(dialog, config)
    setattr(dialog, "_cara_themed_resize_grip", grip)
    return grip
