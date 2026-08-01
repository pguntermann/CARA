"""Opening Encyclopedia detail dialog."""

from __future__ import annotations

import html
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QRect,
    QSize,
    QUrl,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPalette,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services.opening_encyclopedia_service import (
    EncyclopediaEntry,
    EncyclopediaImage,
    OpeningEncyclopediaService,
)
from app.utils.external_open import open_url
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.themed_icon import (
    SVG_MENU_EXCLAMATION,
    SVG_MENU_MAXIMIZE,
    SVG_MENU_RESET,
    SVG_MENU_SEARCH,
    SVG_MENU_SIZE_EQUAL,
    SVG_MENU_SIZE_HEIGHT,
    SVG_MENU_SIZE_WIDTH,
    SVG_MENU_TEXT_SIZE,
    menu_icon_dark_tint_rgb,
    themed_icon_from_svg,
)
from app.views.delegates.encyclopedia_search_result_delegate import (
    ECO_CHIP_ROLE,
    EncyclopediaSearchResultDelegate,
)
from app.views.style import StyleManager
from app.views.style.menu_bar import apply_menu_styling

# Window-size presets as percent-of-available-screen keys stored in user settings.
_SIZE_PRESET_KEYS = ("45", "60", "80")
_SIZE_PRESET_FRACTIONS = {"45": 0.45, "60": 0.60, "80": 0.80}
# Older keys from previous schemes map to the nearest current preset.
_SIZE_PRESET_LEGACY = {"25": "45", "40": "45", "50": "60", "75": "80"}
_SIZE_PRESET_CUSTOM = "custom"
_SIZE_PRESET_DEFAULT = "default"
_SIZE_AXIS_TOL_PX = 4
# Comfortable reading size used when no preset is chosen yet (and for Reset).
_DEFAULT_TARGET_WIDTH = 880
_DEFAULT_TARGET_HEIGHT = 620
_DEFAULT_MAX_SCREEN_FRACTION = 0.75

_TEXT_SIZE_KEYS = ("small", "medium", "large")
_TEXT_SIZE_DEFAULT = "medium"
_TEXT_SIZE_SCALES = {
    "small": 0.9,
    "medium": 1.0,
    "large": 1.18,
}
_TEXT_SIZE_MENU_A_PT = {
    "small": 11,
    "medium": 14,
    "large": 18,
}
_TEXT_SIZE_LABELS = {
    "small": "Small",
    "medium": "Medium",
    "large": "Large",
}

# SAN-aware matcher for encyclopedia prose (aligned with notes formatter ideas).
_FILE = r"[a-h]"
_RANK = r"[1-8]"
_SQUARE = rf"{_FILE}{_RANK}"
_CHECK = r"[+#]?"
_PROMO = r"(?:=[QRBN])?"
_CASTLING = rf"O-O(?:-O)?{_CHECK}"
_PAWN_SAN = rf"(?:{_FILE}x)?{_SQUARE}{_PROMO}{_CHECK}"
_PIECE_SAN = rf"[KQRBN](?:{_SQUARE}|{_FILE}|{_RANK})?x?{_SQUARE}{_PROMO}{_CHECK}"
_SAN = rf"(?:{_CASTLING}|{_PIECE_SAN}|{_PAWN_SAN})"
_ELLIPSIS = r"(?:…|\.\.\.)"
_BOUNDARY = r"(?<![A-Za-z0-9])"
_TOKEN_END = r"(?=[\s,.;:)\!\?/\-–—]|$)"

_NUMBERED_WHITE = re.compile(
    rf"{_BOUNDARY}(?P<full>(?P<num>\d+)\.\s*(?P<w>{_SAN})){_TOKEN_END}"
    rf"(?:\s+(?P<b>{_SAN}){_TOKEN_END})?"
)
_NUMBERED_BLACK = re.compile(
    rf"{_BOUNDARY}(?P<full>(?P<num>\d+)\s*{_ELLIPSIS}\s*(?P<b>{_SAN})){_TOKEN_END}"
)
_ELLIPSIS_MOVE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<full>{_ELLIPSIS}\s*(?P<m>{_SAN})){_TOKEN_END}"
)
_BARE_SAN = re.compile(rf"{_BOUNDARY}(?P<full>{_SAN}){_TOKEN_END}")


def _rgb(value: Any, default: list[int]) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [int(value[0]), int(value[1]), int(value[2])]
    return list(default)


def _letter_a_menu_icon(
    point_size: int,
    tint_rgb: Tuple[int, int, int],
    *,
    box_size: int = 22,
) -> QIcon:
    """Paint a capital A icon for text-size menu rows (theme-tinted)."""
    dpr = 1.0
    app = QApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            dpr = float(screen.devicePixelRatio())
    px = max(16, int(round(box_size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont(
        resolve_font_family("Helvetica Neue"),
        max(8, int(point_size)),
        QFont.Weight.DemiBold,
    )
    painter.setFont(font)
    painter.setPen(QColor(int(tint_rgb[0]), int(tint_rgb[1]), int(tint_rgb[2])))
    painter.drawText(
        QRect(0, 0, box_size, box_size),
        int(Qt.AlignmentFlag.AlignCenter),
        "A",
    )
    painter.end()
    return QIcon(pm)


def _collect_move_spans(plain: str) -> List[Tuple[int, int]]:
    """Return non-overlapping [start, end) spans of move references in ``plain``."""
    spans: List[Tuple[int, int]] = []

    def add(start: int, end: int) -> None:
        if start < end:
            spans.append((start, end))

    for m in _NUMBERED_WHITE.finditer(plain):
        add(m.start("full"), m.end("w"))
        if m.group("b"):
            add(m.start("b"), m.end("b"))
    for m in _NUMBERED_BLACK.finditer(plain):
        add(m.start("full"), m.end("full"))
    for m in _ELLIPSIS_MOVE.finditer(plain):
        add(m.start("full"), m.end("full"))
    for m in _BARE_SAN.finditer(plain):
        add(m.start("full"), m.end("full"))

    if not spans:
        return []
    spans.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    merged: List[Tuple[int, int]] = []
    last_end = -1
    for start, end in spans:
        if start < last_end:
            continue
        merged.append((start, end))
        last_end = end
    return merged


def format_encyclopedia_text_html(
    plain: str,
    *,
    body_color: list[int],
    move_color: list[int],
    move_font_weight: str = "600",
) -> str:
    """Escape prose and wrap recognized move references in styled spans."""
    if not plain:
        return ""
    spans = _collect_move_spans(plain)
    br = body_color
    mr = move_color
    body_style = f"color: rgb({br[0]}, {br[1]}, {br[2]});"
    move_style = (
        f"color: rgb({mr[0]}, {mr[1]}, {mr[2]}); "
        f"font-weight: {html.escape(str(move_font_weight))};"
    )
    parts: List[str] = [f'<span style="{body_style}">']
    i = 0
    for start, end in spans:
        if start > i:
            parts.append(html.escape(plain[i:start]))
        parts.append(f'<span style="{move_style}">{html.escape(plain[start:end])}</span>')
        i = end
    if i < len(plain):
        parts.append(html.escape(plain[i:]))
    parts.append("</span>")
    return "".join(parts).replace("\n", "<br/>")


def format_image_caption(image: EncyclopediaImage) -> Optional[str]:
    """Primary caption with optional lifespan, e.g. ``Name (1726–1795)``."""
    caption = (image.caption or "").strip()
    lifespan = (image.lifespan or "").strip()
    if caption and lifespan:
        if lifespan in caption:
            return caption
        return f"{caption} ({lifespan})"
    if caption:
        return caption
    if lifespan:
        return lifespan
    return None


def format_image_credit_html(
    image: EncyclopediaImage,
    *,
    credit_color: list[int],
    link_color: list[int],
    font_size_pt: int = 8,
) -> Optional[str]:
    """Attribution / license / source credit line (HTML, source as link when URL)."""
    parts: List[str] = []
    if image.attribution:
        parts.append(html.escape(image.attribution))
    if image.license:
        parts.append(html.escape(image.license))

    credit = " · ".join(parts) if parts else ""
    source = (image.source or "").strip()
    cc = credit_color
    lc = link_color
    color_style = (
        f"color: rgb({cc[0]}, {cc[1]}, {cc[2]}); font-size: {int(font_size_pt)}pt;"
    )
    link_style = f"color: rgb({lc[0]}, {lc[1]}, {lc[2]}); font-size: {int(font_size_pt)}pt;"

    if source and (source.startswith("http://") or source.startswith("https://")):
        href = html.escape(source, quote=True)
        link = f'<a href="{href}" style="{link_style}">Source</a>'
        if credit:
            return f'<span style="{color_style}">{credit}<br/>{link}</span>'
        return f'<span style="{color_style}">{link}</span>'
    if source:
        src_line = html.escape(source)
        if credit:
            return f'<span style="{color_style}">{credit}<br/>{src_line}</span>'
        return f'<span style="{color_style}">{src_line}</span>'
    if credit:
        return f'<span style="{color_style}">{credit}</span>'
    return None


def _fit_pixmap(pix: QPixmap, column_w: int) -> QPixmap:
    """Scale pixmap to the shared column width (aspect ratio preserved)."""
    if pix.isNull() or column_w <= 0:
        return pix
    if pix.width() == column_w:
        return pix
    return pix.scaledToWidth(column_w, Qt.TransformationMode.SmoothTransformation)


def _fit_gallery_pixmap(pix: QPixmap, max_w: int, max_h: int) -> QPixmap:
    """Fit pixmap into bounds without upscaling past the original size."""
    if pix.isNull() or max_w <= 0 or max_h <= 0:
        return pix
    if pix.width() <= max_w and pix.height() <= max_h:
        return pix
    return pix.scaled(
        max_w,
        max_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class _ClickableImageLabel(QLabel):
    """Thumbnail / gallery image that reports left-clicks."""

    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _TitleSearchFade(QWidget):
    """Right-edge fade over the title so the floating search blends in."""

    def __init__(
        self,
        bg_rgb: list[int],
        parent: Optional[QWidget] = None,
        *,
        stops: Optional[List[Tuple[float, int]]] = None,
    ) -> None:
        super().__init__(parent)
        self._bg = QColor(int(bg_rgb[0]), int(bg_rgb[1]), int(bg_rgb[2]))
        # (position 0..1, alpha 0..255), left → right.
        self._stops: List[Tuple[float, int]] = list(stops) if stops else [
            (0.0, 0),
            (0.2, 180),
            (0.4, 255),
            (1.0, 255),
        ]
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        grad = QLinearGradient(0.0, 0.0, float(self.width()), 0.0)
        for pos, alpha in self._stops:
            p = max(0.0, min(1.0, float(pos)))
            a = max(0, min(255, int(alpha)))
            c = QColor(self._bg)
            c.setAlpha(a)
            grad.setColorAt(p, c)
        painter.fillRect(self.rect(), grad)


class EncyclopediaGalleryOverlay(QWidget):
    """In-dialog gallery: dimmed backdrop, fitted image, optional image switcher."""

    closed = pyqtSignal()

    def __init__(
        self,
        parent: QWidget,
        pixmaps: List[QPixmap],
        captions: List[Optional[str]],
        subcaptions: List[Optional[str]],
        gallery_config: Dict[str, Any],
    ) -> None:
        super().__init__(parent)
        self._pixmaps = list(pixmaps)
        self._captions = list(captions)
        self._subcaptions = list(subcaptions)
        self._index = 0
        self._nav_widgets: List[QWidget] = []

        overlay_rgb = _rgb(gallery_config.get("overlay_color"), [0, 0, 0])
        opacity = float(gallery_config.get("overlay_opacity", 0.78))
        opacity = max(0.0, min(1.0, opacity))
        alpha = int(round(255 * opacity))
        padding = int(gallery_config.get("padding", 28))
        self._padding = max(8, padding)

        caption_color = _rgb(gallery_config.get("caption_color"), [220, 220, 225])
        caption_size = int(scale_font_size(gallery_config.get("caption_font_size", 10)))
        subcaption_color = _rgb(
            gallery_config.get("subcaption_color"),
            gallery_config.get("credit_color", [160, 160, 165]),
        )
        subcaption_size = int(
            scale_font_size(
                gallery_config.get(
                    "subcaption_font_size",
                    gallery_config.get("credit_font_size", 8),
                )
            )
        )
        link_color = _rgb(
            gallery_config.get("subcaption_link_color"),
            gallery_config.get("credit_link_color", caption_color),
        )

        nav_cfg = gallery_config.get("nav", {})
        if not isinstance(nav_cfg, dict):
            nav_cfg = {}
        self._dot_size = max(6, int(nav_cfg.get("dot_size", 9)))
        self._dot_color = _rgb(nav_cfg.get("dot_color"), [120, 120, 125])
        self._dot_active = _rgb(nav_cfg.get("dot_active_color"), [235, 235, 240])
        nav_spacing = int(nav_cfg.get("spacing", 10))

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background-color: rgba({overlay_rgb[0]}, {overlay_rgb[1]}, {overlay_rgb[2]}, {alpha});"
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(self._padding, self._padding, self._padding, self._padding)
        root.setSpacing(10)

        root.addStretch(1)

        self._image = _ClickableImageLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setScaledContents(False)
        self._image.setStyleSheet("background: transparent; border: none;")
        self._image.setCursor(Qt.CursorShape.PointingHandCursor)
        self._image.clicked.connect(self.close_gallery)
        root.addWidget(self._image, 0, Qt.AlignmentFlag.AlignCenter)

        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._caption.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._caption.setStyleSheet(
            f"color: rgb({caption_color[0]}, {caption_color[1]}, {caption_color[2]}); "
            f"font-size: {caption_size}pt; background: transparent; border: none;"
        )
        # Full-width row (text centered). AlignHCenter on the widget would shrink it
        # to sizeHint and clip captions.
        root.addWidget(self._caption)

        self._subcaption = QLabel()
        self._subcaption.setWordWrap(True)
        self._subcaption.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._subcaption.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._subcaption.setTextFormat(Qt.TextFormat.RichText)
        self._subcaption.setOpenExternalLinks(False)
        self._subcaption.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self._subcaption.linkActivated.connect(
            lambda url: open_url(QUrl(url), context="encyclopedia.gallery_source")
        )
        self._subcaption.setStyleSheet(
            f"color: rgb({subcaption_color[0]}, {subcaption_color[1]}, {subcaption_color[2]}); "
            f"font-size: {subcaption_size}pt; background: transparent; border: none;"
        )
        root.addWidget(self._subcaption)

        self._nav = QWidget()
        self._nav.setStyleSheet("background: transparent;")
        self._nav.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        nav_row = QHBoxLayout(self._nav)
        nav_row.setContentsMargins(0, 4, 0, 0)
        nav_row.setSpacing(nav_spacing)
        nav_row.addStretch(1)
        if len(self._pixmaps) > 1:
            for i in range(len(self._pixmaps)):
                dot = QPushButton()
                dot.setFixedSize(self._dot_size, self._dot_size)
                dot.setCursor(Qt.CursorShape.PointingHandCursor)
                dot.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                dot.clicked.connect(lambda _checked=False, idx=i: self.show_index(idx))
                nav_row.addWidget(dot, 0, Qt.AlignmentFlag.AlignCenter)
                self._nav_widgets.append(dot)
        nav_row.addStretch(1)
        root.addWidget(self._nav)
        self._nav.setVisible(len(self._pixmaps) > 1)

        root.addStretch(1)

    def open_at(self, index: int) -> None:
        if not self._pixmaps:
            return
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self._index = max(0, min(int(index), len(self._pixmaps) - 1))
        self._apply_caption_texts()
        self._refresh_nav()
        # Show first so width/height and word-wrap metrics are valid, then fit.
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self._refresh_image()
        # Second pass after Qt finishes the initial layout (avoids caption/image collision).
        QTimer.singleShot(0, self._refresh_image)

    def close_gallery(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        self.closed.emit()

    def show_index(self, index: int) -> None:
        if not self._pixmaps:
            return
        self._index = max(0, min(int(index), len(self._pixmaps) - 1))
        self._refresh_image()
        self._refresh_nav()

    def refresh_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        if self.isVisible():
            self._refresh_image()

    def _apply_caption_texts(self) -> None:
        caption = ""
        if 0 <= self._index < len(self._captions) and self._captions[self._index]:
            caption = str(self._captions[self._index])
        self._caption.setText(caption)
        self._caption.setVisible(bool(caption))

        subcaption = ""
        if 0 <= self._index < len(self._subcaptions) and self._subcaptions[self._index]:
            subcaption = str(self._subcaptions[self._index])
        self._subcaption.setText(subcaption)
        self._subcaption.setVisible(bool(subcaption))

    def _footer_height(self, content_width: int) -> int:
        """Vertical space reserved under the image (caption, nav, layout gaps)."""
        layout = self.layout()
        spacing = int(layout.spacing()) if layout is not None else 10
        parts_visible = 0
        total = 0

        if self._caption.isVisible() and self._caption.text():
            # Prefer unwrapped single-line height when the text fits.
            fm = self._caption.fontMetrics()
            text = self._caption.text()
            if fm.horizontalAdvance(text) <= content_width:
                caption_h = fm.height()
            else:
                caption_h = self._caption.heightForWidth(content_width)
                if caption_h < 0:
                    caption_h = self._caption.sizeHint().height()
            total += max(int(caption_h), fm.height())
            parts_visible += 1

        if self._subcaption.isVisible() and self._subcaption.text():
            fm = self._subcaption.fontMetrics()
            hfw = self._subcaption.heightForWidth(content_width)
            if hfw < 0:
                hfw = self._subcaption.sizeHint().height()
            total += max(int(hfw), fm.height())
            parts_visible += 1

        if self._nav.isVisible():
            nav_h = self._nav.sizeHint().height()
            total += max(nav_h, self._dot_size + 8)
            parts_visible += 1

        # Gaps between image / caption / nav, plus a little breathing room.
        if parts_visible:
            total += spacing * parts_visible
        return total

    def _refresh_image(self) -> None:
        self._apply_caption_texts()

        if self.width() <= 1 or self.height() <= 1:
            parent = self.parentWidget()
            if parent is not None:
                self.setGeometry(parent.rect())

        max_w = max(1, self.width() - 2 * self._padding)
        footer_h = self._footer_height(max_w)
        max_h = max(1, self.height() - 2 * self._padding - footer_h)

        pix = self._pixmaps[self._index]
        fitted = _fit_gallery_pixmap(pix, max_w, max_h)
        self._image.setPixmap(fitted)
        self._image.setFixedSize(fitted.size())

        layout = self.layout()
        if layout is not None:
            layout.activate()

    def _refresh_nav(self) -> None:
        for i, dot in enumerate(self._nav_widgets):
            active = i == self._index
            color = self._dot_active if active else self._dot_color
            r = self._dot_size // 2
            dot.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: rgb({color[0]}, {color[1]}, {color[2]});
                    border: none;
                    border-radius: {r}px;
                }}
                """
            )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Keep interactive chrome (nav dots / credit links) from closing the gallery.
            child = self.childAt(event.position().toPoint())
            if child is not None and (
                child is self._nav
                or self._nav.isAncestorOf(child)
                or child is self._subcaption
                or self._subcaption.isAncestorOf(child)
            ):
                super().mouseReleaseEvent(event)
                return
            self.close_gallery()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.close_gallery()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) and len(self._pixmaps) > 1:
            self.show_index((self._index - 1) % len(self._pixmaps))
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down) and len(self._pixmaps) > 1:
            self.show_index((self._index + 1) % len(self._pixmaps))
            return
        super().keyPressEvent(event)


def build_encyclopedia_tag_chip(
    prefix: str,
    value: str,
    *,
    bg: List[int],
    fg: List[int],
    font_size: int = 8,
    border_radius: int = 4,
    padding: Optional[List[int]] = None,
) -> QLabel:
    """Create a small colored metadata chip (``Prefix: value``)."""
    pad = padding if isinstance(padding, (list, tuple)) and len(padding) >= 4 else [2, 6, 2, 6]
    tag = QLabel(f"{prefix}: {value}")
    tag.setFont(QFont(resolve_font_family("Helvetica Neue"), int(font_size)))
    tag.setStyleSheet(
        f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); "
        f"color: rgb({fg[0]}, {fg[1]}, {fg[2]}); "
        f"border-radius: {int(border_radius)}px; "
        f"padding: {int(pad[0])}px {int(pad[1])}px {int(pad[2])}px {int(pad[3])}px;"
    )
    tag.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return tag


class OpeningEncyclopediaDialog(QDialog):
    """Themed dialog showing encyclopedia prose and optional portrait art."""

    def __init__(
        self,
        config: Dict[str, Any],
        entry: EncyclopediaEntry,
        encyclopedia_service: OpeningEncyclopediaService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._entry = entry
        self._encyclopedia = encyclopedia_service
        self._gallery_overlay: Optional[EncyclopediaGalleryOverlay] = None
        self._gallery_pixmaps: List[QPixmap] = []
        self._gallery_images: List[EncyclopediaImage] = []
        self._gallery_captions: List[Optional[str]] = []
        self._gallery_subcaptions: List[Optional[str]] = []
        self._scroll: Optional[QScrollArea] = None
        self._content_host: Optional[QWidget] = None
        self._body_labels: List[QLabel] = []
        self._heading_labels: List[QLabel] = []
        self._title_label: Optional[QLabel] = None
        self._section_blocks: List[QWidget] = []
        self._beside_host: Optional[QWidget] = None
        self._below_host: Optional[QWidget] = None
        self._beside_layout: Optional[QVBoxLayout] = None
        self._below_layout: Optional[QVBoxLayout] = None
        self._top_row: Optional[QWidget] = None
        self._image_panel: Optional[QWidget] = None
        self._image_text_gap: int = 16
        self._beside_block_count: Optional[int] = None
        self._resize_sync_timer = QTimer(self)
        self._resize_sync_timer.setSingleShot(True)
        self._resize_sync_timer.setInterval(40)
        self._resize_sync_timer.timeout.connect(self._sync_scroll_content_size)

        dialog_config = (
            (config.get("ui") or {}).get("dialogs", {}).get("opening_encyclopedia_dialog", {})
        )
        self._dialog_config = dialog_config
        layout_config = dialog_config.get("layout", {})
        self.bottom_button_top_padding = int(dialog_config.get("bottom_button_top_padding", 24))

        self.setWindowTitle(entry.display_name or "Opening Encyclopedia")

        bg = _rgb(dialog_config.get("background_color"), [40, 40, 45])
        self._dialog_bg_rgb = bg
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(*bg))
        self.setPalette(pal)

        min_w = int(dialog_config.get("minimum_width", 520))
        min_h = int(dialog_config.get("minimum_height", 360))
        # Free resize with a layout-safe lower bound only (no artificial max).
        self._min_dialog_size = QSize(min_w, min_h)
        self.setMinimumSize(self._min_dialog_size)

        size_cfg = dialog_config.get("size_toggle", {})
        if not isinstance(size_cfg, dict):
            size_cfg = {}
        raw_presets = size_cfg.get("presets", [0.45, 0.6, 0.8])
        self._size_presets: List[float] = []
        if isinstance(raw_presets, (list, tuple)):
            for value in raw_presets:
                try:
                    frac = float(value)
                except (TypeError, ValueError):
                    continue
                if 0.05 <= frac <= 1.0:
                    self._size_presets.append(frac)
        if len(self._size_presets) != 3:
            self._size_presets = [0.45, 0.6, 0.8]
        labels = size_cfg.get("preset_labels", ["45%", "60%", "80%"])
        if not isinstance(labels, (list, tuple)) or len(labels) < 3:
            labels = ["45%", "60%", "80%"]
        self._size_preset_labels = [str(labels[0]), str(labels[1]), str(labels[2])]
        equal_labels = size_cfg.get("equal_labels")
        if isinstance(equal_labels, (list, tuple)) and len(equal_labels) >= 3:
            self._size_equal_labels = [
                str(equal_labels[0]),
                str(equal_labels[1]),
                str(equal_labels[2]),
            ]
        else:
            self._size_equal_labels = [
                f"{self._size_preset_labels[0]} × {self._size_preset_labels[0]}",
                f"{self._size_preset_labels[1]} × {self._size_preset_labels[1]}",
                f"{self._size_preset_labels[2]} × {self._size_preset_labels[2]}",
            ]
        self._size_section_equal = str(size_cfg.get("section_equal", "Equal"))
        self._size_section_width = str(size_cfg.get("section_width", "Width"))
        self._size_section_height = str(size_cfg.get("section_height", "Height"))
        self._size_reset_label = str(size_cfg.get("reset_label", "Reset to default"))
        self._size_screen_margin = max(0, int(size_cfg.get("screen_margin", 8)))
        default_size_cfg = size_cfg.get("default_size", {})
        if not isinstance(default_size_cfg, dict):
            default_size_cfg = {}
        try:
            self._default_target_width = max(
                1, int(default_size_cfg.get("target_width", _DEFAULT_TARGET_WIDTH))
            )
        except (TypeError, ValueError):
            self._default_target_width = _DEFAULT_TARGET_WIDTH
        try:
            self._default_target_height = max(
                1, int(default_size_cfg.get("target_height", _DEFAULT_TARGET_HEIGHT))
            )
        except (TypeError, ValueError):
            self._default_target_height = _DEFAULT_TARGET_HEIGHT
        try:
            max_frac = float(
                default_size_cfg.get(
                    "max_screen_fraction", _DEFAULT_MAX_SCREEN_FRACTION
                )
            )
        except (TypeError, ValueError):
            max_frac = _DEFAULT_MAX_SCREEN_FRACTION
        self._default_max_screen_fraction = max(0.2, min(1.0, max_frac))
        self._size_preset_key = _SIZE_PRESET_DEFAULT
        self._size_anim: Optional[QPropertyAnimation] = None
        self._suppress_size_persist = False
        self._programmatic_resize = False
        self._center_reassert_token = 0
        self._size_applied_on_show = False
        self._size_persist_timer = QTimer(self)
        self._size_persist_timer.setSingleShot(True)
        self._size_persist_timer.setInterval(200)
        self._size_persist_timer.timeout.connect(self._persist_current_size)

        text_size_cfg = size_cfg.get("text_size", {})
        if not isinstance(text_size_cfg, dict):
            text_size_cfg = {}
        self._text_size_section = str(text_size_cfg.get("section", "Text size"))
        self._text_size_options: List[Dict[str, Any]] = []
        raw_text_opts = text_size_cfg.get("options")
        if isinstance(raw_text_opts, list):
            for item in raw_text_opts:
                if not isinstance(item, dict):
                    continue
                opt_id = str(item.get("id") or "").strip().lower()
                if opt_id not in _TEXT_SIZE_KEYS:
                    continue
                try:
                    scale = float(item.get("scale", _TEXT_SIZE_SCALES[opt_id]))
                except (TypeError, ValueError):
                    scale = _TEXT_SIZE_SCALES[opt_id]
                try:
                    menu_a_pt = int(item.get("menu_a_pt", _TEXT_SIZE_MENU_A_PT[opt_id]))
                except (TypeError, ValueError):
                    menu_a_pt = _TEXT_SIZE_MENU_A_PT[opt_id]
                self._text_size_options.append(
                    {
                        "id": opt_id,
                        "label": str(
                            item.get("label") or _TEXT_SIZE_LABELS.get(opt_id, opt_id)
                        ),
                        "scale": max(0.5, min(2.0, scale)),
                        "menu_a_pt": max(8, min(28, menu_a_pt)),
                    }
                )
        if len(self._text_size_options) != 3:
            self._text_size_options = [
                {
                    "id": key,
                    "label": _TEXT_SIZE_LABELS[key],
                    "scale": _TEXT_SIZE_SCALES[key],
                    "menu_a_pt": _TEXT_SIZE_MENU_A_PT[key],
                }
                for key in _TEXT_SIZE_KEYS
            ]
        self._text_size_scales = {
            str(opt["id"]): float(opt["scale"]) for opt in self._text_size_options
        }
        stored_text = str(
            self._load_size_settings().get("text_size")
            or text_size_cfg.get("default")
            or _TEXT_SIZE_DEFAULT
        ).strip().lower()
        if stored_text not in self._text_size_scales:
            stored_text = _TEXT_SIZE_DEFAULT
        self._text_size_key = stored_text
        self._text_size_scale = float(
            self._text_size_scales.get(stored_text, _TEXT_SIZE_SCALES[_TEXT_SIZE_DEFAULT])
        )

        root = QVBoxLayout(self)
        margins = layout_config.get("margins", [20, 20, 20, 20])
        if isinstance(margins, (list, tuple)) and len(margins) >= 4:
            root.setContentsMargins(int(margins[0]), int(margins[1]), int(margins[2]), int(margins[3]))
        root.setSpacing(int(layout_config.get("spacing", 12)))

        border = _rgb(
            (dialog_config.get("buttons") or {}).get("border_color"),
            [60, 60, 65],
        )

        # Single scroll area for text + images together.
        # Manual content sizing (not widgetResizable) avoids inflated QLabel
        # height hints leaving a tall blank scrollable region under short prose.
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        StyleManager.style_scroll_area(
            scroll,
            config,
            bg,
            border,
            border_radius=0,
            include_scroll_area_border=False,
        )
        self._scroll = scroll

        content_host = QWidget()
        content_host.setStyleSheet("background: transparent;")
        content_host.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self._content_host = content_host
        content_col = QVBoxLayout(content_host)
        content_col.setSpacing(int(layout_config.get("section_spacing", 10)))
        content_col.setContentsMargins(0, 0, 4, 0)
        content_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._image_text_gap = int(layout_config.get("image_text_gap", 16))

        title_cfg = dialog_config.get("title", {})
        title = QLabel(entry.display_name)
        title.setWordWrap(True)
        self._title_font_family = resolve_font_family(
            title_cfg.get("font_family", "Helvetica Neue")
        )
        try:
            self._title_font_base = float(title_cfg.get("font_size", 14))
        except (TypeError, ValueError):
            self._title_font_base = 14.0
        title.setFont(
            QFont(
                self._title_font_family,
                self._content_pt(self._title_font_base),
                QFont.Weight.Bold,
            )
        )
        title_color = _rgb(title_cfg.get("text_color"), [240, 240, 240])
        title.setStyleSheet(
            f"color: rgb({title_color[0]}, {title_color[1]}, {title_color[2]}); background: transparent;"
        )
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._title_label = title

        tags_row = self._build_tags_row(entry, dialog_config)
        self._tags_row = tags_row

        search_cfg = dialog_config.get("search", {})
        if not isinstance(search_cfg, dict):
            search_cfg = {}
        self._search_open = False
        self._search_container = self._build_search_widget(search_cfg, dialog_config)
        self._search_fade_extra = int(search_cfg.get("title_fade_extra_width", 56))
        self._search_fade_min_width = int(search_cfg.get("title_fade_min_width", 72))
        fade_stops = self._parse_title_fade_stops(search_cfg.get("title_fade_stops"))
        self._title_fade = _TitleSearchFade(bg, title, stops=fade_stops)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        body_cfg = dialog_config.get("body", {})
        body_family = resolve_font_family(body_cfg.get("font_family", "Helvetica Neue"))
        self._body_font_family = body_family
        try:
            self._body_font_base = float(body_cfg.get("font_size", 11))
        except (TypeError, ValueError):
            self._body_font_base = 11.0
        body_size = self._content_pt(self._body_font_base)
        body_color = _rgb(body_cfg.get("text_color"), [200, 200, 200])
        move_cfg = dialog_config.get("move_highlight", {})
        move_color = _rgb(move_cfg.get("text_color"), [100, 150, 255])
        move_weight = str(move_cfg.get("font_weight", "600"))
        section_cfg = dialog_config.get("section_title", {})
        try:
            self._section_font_base = float(section_cfg.get("font_size", 11))
        except (TypeError, ValueError):
            self._section_font_base = 11.0
        section_size = self._content_pt(self._section_font_base)
        section_color = _rgb(section_cfg.get("text_color"), [180, 180, 185])
        sep_cfg = dialog_config.get("section_separator", {})
        if not isinstance(sep_cfg, dict):
            sep_cfg = {}
        sep_enabled = bool(sep_cfg.get("enabled", True))
        sep_color = _rgb(sep_cfg.get("color"), [70, 70, 75])
        sep_height = max(1, int(sep_cfg.get("height", 1)))
        sep_margin = sep_cfg.get("margin", [10, 0, 6, 0])
        if not isinstance(sep_margin, list) or len(sep_margin) < 4:
            sep_margin = [10, 0, 6, 0]
        sep_mt, _sep_mr, sep_mb, _sep_ml = (int(v) for v in sep_margin[:4])
        section_spacing = int(layout_config.get("section_spacing", 10))

        def _make_separator() -> QWidget:
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            v = QVBoxLayout(wrap)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)
            if sep_mt:
                v.addSpacing(sep_mt)
            line = QFrame()
            line.setFixedHeight(sep_height)
            line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            c = sep_color
            line.setStyleSheet(
                f"background-color: rgb({c[0]}, {c[1]}, {c[2]}); border: none;"
            )
            v.addWidget(line)
            if sep_mb:
                v.addSpacing(sep_mb)
            return wrap

        def _make_section(
            heading: Optional[str],
            body: Optional[str],
            *,
            emphasize: bool = False,
            with_separator: bool = False,
        ) -> Optional[QWidget]:
            if not body:
                return None
            block = QWidget()
            block.setStyleSheet("background: transparent;")
            block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            col = QVBoxLayout(block)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(section_spacing)
            col.setAlignment(Qt.AlignmentFlag.AlignTop)
            if with_separator and sep_enabled:
                col.addWidget(_make_separator())
            if heading:
                h = QLabel(heading)
                h.setFont(QFont(body_family, section_size, QFont.Weight.DemiBold))
                h.setStyleSheet(
                    f"color: rgb({section_color[0]}, {section_color[1]}, {section_color[2]}); "
                    "background: transparent;"
                )
                h.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                col.addWidget(h)
                self._heading_labels.append(h)
            lab = QLabel()
            lab.setWordWrap(True)
            lab.setTextFormat(Qt.TextFormat.RichText)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            size = body_size + (1 if emphasize else 0)
            lab.setFont(QFont(body_family, size))
            lab.setStyleSheet("background: transparent;")
            lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lab.setMinimumHeight(0)
            lab.setText(
                format_encyclopedia_text_html(
                    body,
                    body_color=body_color,
                    move_color=move_color,
                    move_font_weight=move_weight,
                )
            )
            lab._encyclopedia_emphasize = bool(emphasize)  # type: ignore[attr-defined]
            col.addWidget(lab)
            self._body_labels.append(lab)
            # Stash the body label on the block for width-specific measuring.
            block._encyclopedia_body = lab  # type: ignore[attr-defined]
            return block

        self._section_blocks = []
        for heading, body, emphasize in (
            (None, entry.summary, True),
            ("Key ideas", entry.key_ideas, False),
            ("Name origin", entry.name_origin, False),
            ("History", entry.history, False),
        ):
            block = _make_section(
                heading,
                body,
                emphasize=emphasize,
                with_separator=bool(heading) and bool(self._section_blocks),
            )
            if block is not None:
                self._section_blocks.append(block)

        beside_host = QWidget()
        beside_host.setStyleSheet("background: transparent;")
        beside_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._beside_host = beside_host
        self._beside_layout = QVBoxLayout(beside_host)
        self._beside_layout.setContentsMargins(0, 0, 0, 0)
        self._beside_layout.setSpacing(section_spacing)
        self._beside_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        below_host = QWidget()
        below_host.setStyleSheet("background: transparent;")
        below_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._below_host = below_host
        self._below_layout = QVBoxLayout(below_host)
        self._below_layout.setContentsMargins(0, 0, 0, 0)
        self._below_layout.setSpacing(section_spacing)
        self._below_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        top_row = QWidget()
        top_row.setStyleSheet("background: transparent;")
        top_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._top_row = top_row
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(self._image_text_gap)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        top_layout.addWidget(beside_host, 1)

        self._image_panel = None
        if entry.images:
            image_panel = self._build_image_column(
                entry,
                encyclopedia_service,
                dialog_config,
            )
            self._image_panel = image_panel
            top_layout.addWidget(image_panel, 0, Qt.AlignmentFlag.AlignTop)

        content_col.addWidget(top_row)
        content_col.addWidget(below_host)
        # Initial placement; refined on show/resize once widths are known.
        for block in self._section_blocks:
            self._beside_layout.addWidget(block)

        # Header block: title + search/size tools on the first line, tags below.
        # The title gets full width; the tool buttons are small fixed-size
        # widgets that don't compress the title.  When the search field
        # expands it overlaps via a floating results dropdown, not by
        # squeezing the title.
        header_host = QWidget()
        header_host.setStyleSheet("background: transparent;")
        header_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        header_col = QVBoxLayout(header_host)
        header_col.setContentsMargins(0, 0, 0, 0)
        header_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title.setMinimumWidth(0)
        title_row.addWidget(title, 1)
        title_row.addWidget(self._search_container, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        header_col.addLayout(title_row)

        if tags_row is not None:
            header_col.addWidget(tags_row)

        root.addWidget(header_host)

        scroll.setWidget(content_host)
        root.addWidget(scroll, 1)
        root.addSpacing(self.bottom_button_top_padding)

        buttons_config = dialog_config.get("buttons", {})
        button_row = QHBoxLayout()
        button_row.setSpacing(int(buttons_config.get("spacing", 10)))
        button_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        StyleManager.style_buttons(
            [close_btn],
            config,
            bg,
            _rgb(buttons_config.get("border_color"), [60, 60, 65]),
            min_width=int(buttons_config.get("width", 120)),
            min_height=int(buttons_config.get("height", 30)),
        )
        root.addLayout(button_row)

        if self._gallery_pixmaps:
            gallery_cfg = dialog_config.get("gallery", {})
            if not isinstance(gallery_cfg, dict):
                gallery_cfg = {}
            # Build gallery text with overlay-specific colors (not dialog-body colors).
            caption_color = _rgb(gallery_cfg.get("caption_color"), [220, 220, 225])
            subcaption_color = _rgb(
                gallery_cfg.get("subcaption_color"),
                gallery_cfg.get("credit_color", [160, 160, 165]),
            )
            link_color = _rgb(
                gallery_cfg.get("subcaption_link_color"),
                gallery_cfg.get("credit_link_color", caption_color),
            )
            subcaption_size = min(
                8,
                int(
                    scale_font_size(
                        gallery_cfg.get(
                            "subcaption_font_size",
                            gallery_cfg.get("credit_font_size", 8),
                        )
                    )
                ),
            )
            self._gallery_captions = [
                format_image_caption(image) for image in self._gallery_images
            ]
            self._gallery_subcaptions = [
                format_image_credit_html(
                    image,
                    credit_color=subcaption_color,
                    link_color=link_color,
                    font_size_pt=subcaption_size,
                )
                for image in self._gallery_images
            ]
            self._gallery_overlay = EncyclopediaGalleryOverlay(
                self,
                self._gallery_pixmaps,
                self._gallery_captions,
                self._gallery_subcaptions,
                gallery_cfg,
            )

    def _build_tags_row(
        self,
        entry: EncyclopediaEntry,
        dialog_config: Dict[str, Any],
    ) -> Optional[QWidget]:
        """Build a horizontal row of small colored metadata tags."""
        tags_cfg = dialog_config.get("tags", {})
        if not isinstance(tags_cfg, dict):
            tags_cfg = {}
        font_size = int(scale_font_size(tags_cfg.get("font_size", 8)))
        border_radius = int(tags_cfg.get("border_radius", 4))
        pad = tags_cfg.get("padding", [2, 6, 2, 6])
        if not isinstance(pad, (list, tuple)) or len(pad) < 4:
            pad = [2, 6, 2, 6]
        spacing = int(tags_cfg.get("spacing", 5))
        margin_top = int(tags_cfg.get("margin_top", 4))

        tag_defs: List[Tuple[str, str, list, list]] = []
        if entry.opening_id:
            tag_defs.append((
                "ID",
                entry.opening_id,
                _rgb(tags_cfg.get("id_background"), [55, 55, 62]),
                _rgb(tags_cfg.get("id_text_color"), [180, 180, 190]),
            ))
        if entry.tier:
            tag_defs.append((
                "Tier",
                entry.tier,
                _rgb(tags_cfg.get("tier_background"), [50, 60, 75]),
                _rgb(tags_cfg.get("tier_text_color"), [130, 170, 230]),
            ))
        if entry.family_id:
            tag_defs.append((
                "Family",
                entry.family_id,
                _rgb(tags_cfg.get("family_background"), [55, 62, 55]),
                _rgb(tags_cfg.get("family_text_color"), [130, 200, 140]),
            ))
        eco_list = self._parse_eco_codes(entry.eco_codes)
        if eco_list:
            eco_label = ", ".join(eco_list[:5])
            if len(eco_list) > 5:
                eco_label += f" (+{len(eco_list) - 5})"
            tag_defs.append((
                "ECO",
                eco_label,
                _rgb(tags_cfg.get("eco_background"), [65, 55, 55]),
                _rgb(tags_cfg.get("eco_text_color"), [210, 160, 130]),
            ))

        if not tag_defs:
            return None

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, margin_top, 0, 0)
        h.setSpacing(spacing)

        for prefix, value, bg, fg in tag_defs:
            h.addWidget(
                build_encyclopedia_tag_chip(
                    prefix,
                    value,
                    bg=bg,
                    fg=fg,
                    font_size=font_size,
                    border_radius=border_radius,
                    padding=list(pad),
                )
            )
        h.addStretch(1)
        return row

    @staticmethod
    def _parse_eco_codes(eco_codes: Optional[str]) -> List[str]:
        if not eco_codes:
            return []
        eco_codes = eco_codes.strip()
        if eco_codes.startswith("["):
            try:
                parsed = json.loads(eco_codes)
                if isinstance(parsed, list):
                    return [str(c) for c in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return [c.strip() for c in eco_codes.split(",") if c.strip()]

    @staticmethod
    def _parse_title_fade_stops(raw: Any) -> List[Tuple[float, int]]:
        """Parse ``title_fade_stops`` as ``[[position, alpha], ...]``."""
        defaults: List[Tuple[float, int]] = [
            (0.0, 0),
            (0.2, 180),
            (0.4, 255),
            (1.0, 255),
        ]
        if not isinstance(raw, (list, tuple)) or not raw:
            return defaults
        parsed: List[Tuple[float, int]] = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            try:
                pos = float(item[0])
                alpha = int(item[1])
            except (TypeError, ValueError):
                continue
            parsed.append((max(0.0, min(1.0, pos)), max(0, min(255, alpha))))
        return parsed if len(parsed) >= 2 else defaults

    def _build_search_widget(
        self,
        search_cfg: Dict[str, Any],
        dialog_config: Dict[str, Any],
    ) -> QWidget:
        """Build header tools: search icon + size menu + feedback + floating input/results."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        icon_tint = _rgb(search_cfg.get("icon_tint_rgb"), search_cfg.get("icon_color", [160, 160, 165]))
        icon_size = int(search_cfg.get("icon_size", 18))
        icon_svg = str(search_cfg.get("icon_svg") or SVG_MENU_SEARCH)
        btn = QPushButton()
        btn.setFixedSize(icon_size + 8, icon_size + 8)
        btn.setIcon(themed_icon_from_svg(icon_svg, icon_tint))
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolTip("Search openings")
        btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        btn.clicked.connect(self._toggle_search)
        self._search_btn = btn
        lay.addWidget(btn)

        size_cfg = dialog_config.get("size_toggle", {})
        if not isinstance(size_cfg, dict):
            size_cfg = {}
        size_icon_size = int(size_cfg.get("icon_size", icon_size))
        size_tint = _rgb(size_cfg.get("icon_tint_rgb"), icon_tint)
        size_icon_svg = str(size_cfg.get("icon_svg") or SVG_MENU_MAXIMIZE)
        size_tooltip = str(size_cfg.get("tooltip", "Window size"))

        size_btn = QPushButton()
        size_btn.setFixedSize(size_icon_size + 8, size_icon_size + 8)
        size_btn.setIcon(themed_icon_from_svg(size_icon_svg, size_tint))
        size_btn.setIconSize(QSize(size_icon_size, size_icon_size))
        size_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        size_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        size_btn.setToolTip(size_tooltip)
        size_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        size_btn.clicked.connect(self._show_size_menu)
        self._size_toggle_btn = size_btn
        lay.addWidget(size_btn)

        feedback_cfg = dialog_config.get("feedback", {})
        if not isinstance(feedback_cfg, dict):
            feedback_cfg = {}
        if bool(feedback_cfg.get("enabled", True)):
            fb_icon_size = int(feedback_cfg.get("icon_size", icon_size))
            fb_tint = _rgb(feedback_cfg.get("icon_tint_rgb"), icon_tint)
            fb_svg = str(feedback_cfg.get("icon_svg") or SVG_MENU_EXCLAMATION)
            fb_btn = QPushButton()
            fb_btn.setFixedSize(fb_icon_size + 8, fb_icon_size + 8)
            fb_btn.setIcon(themed_icon_from_svg(fb_svg, fb_tint))
            fb_btn.setIconSize(QSize(fb_icon_size, fb_icon_size))
            fb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            fb_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            fb_btn.setToolTip(str(feedback_cfg.get("tooltip", "Report feedback")))
            fb_btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
            fb_btn.clicked.connect(self._open_feedback_dialog)
            self._feedback_btn = fb_btn
            lay.addWidget(fb_btn)
        else:
            self._feedback_btn = None

        input_h = int(search_cfg.get("input_height", 28))
        input_bg = _rgb(search_cfg.get("input_background"), [50, 50, 56])
        input_fg = _rgb(search_cfg.get("input_text_color"), [220, 220, 225])
        input_border = _rgb(search_cfg.get("input_border_color"), [70, 70, 78])
        input_focus_border = _rgb(search_cfg.get("input_focus_border_color"), input_border)
        input_placeholder = _rgb(search_cfg.get("input_placeholder_color"), input_fg)
        input_selection_bg = _rgb(
            search_cfg.get("input_selection_background"),
            search_cfg.get("result_hover_background", input_border),
        )
        input_selection_fg = _rgb(search_cfg.get("input_selection_text_color"), input_fg)
        input_radius = int(search_cfg.get("input_border_radius", 5))
        input_font_size = int(scale_font_size(search_cfg.get("input_font_size", 10)))

        # Floating input — parented to the dialog (self), not in any layout,
        # so it never affects the title's available width.
        inp = QLineEdit(self)
        inp.setPlaceholderText("Search openings…")
        inp.setFixedHeight(input_h)
        inp.setFixedWidth(0)
        inp.setVisible(False)
        inp.setFont(QFont(
            resolve_font_family("Helvetica Neue"),
            input_font_size,
        ))
        inp_palette = inp.palette()
        inp_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(*input_placeholder))
        inp.setPalette(inp_palette)
        inp.setStyleSheet(
            f"QLineEdit {{ background-color: rgb({input_bg[0]}, {input_bg[1]}, {input_bg[2]}); "
            f"color: rgb({input_fg[0]}, {input_fg[1]}, {input_fg[2]}); "
            f"border: 1px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]}); "
            f"border-radius: {input_radius}px; padding: 2px 8px; "
            f"selection-background-color: rgb({input_selection_bg[0]}, {input_selection_bg[1]}, {input_selection_bg[2]}); "
            f"selection-color: rgb({input_selection_fg[0]}, {input_selection_fg[1]}, {input_selection_fg[2]}); }}"
            f"QLineEdit:focus {{ border: 1px solid rgb({input_focus_border[0]}, {input_focus_border[1]}, {input_focus_border[2]}); }}"
        )
        inp.textChanged.connect(self._on_search_text_changed)
        self._search_input = inp

        result_bg = _rgb(search_cfg.get("input_background"), [50, 50, 56])
        result_fg = _rgb(search_cfg.get("result_text_color"), [200, 200, 205])
        result_hover = _rgb(search_cfg.get("result_hover_background"), [55, 55, 62])
        result_selected_bg = _rgb(search_cfg.get("result_selected_background"), result_hover)
        result_selected_fg = _rgb(search_cfg.get("result_selected_text_color"), result_fg)
        result_font_size = int(scale_font_size(search_cfg.get("result_font_size", 10)))
        result_border = _rgb(search_cfg.get("input_border_color"), [70, 70, 78])
        result_padding = search_cfg.get("result_padding", [4, 8, 4, 8])
        if not isinstance(result_padding, (list, tuple)) or len(result_padding) < 4:
            result_padding = [4, 8, 4, 8]
        max_results_h = int(search_cfg.get("results_max_height", 200))

        results = QListWidget(self)
        results.setVisible(False)
        results.setMaximumHeight(max_results_h)
        results.setFont(QFont(
            resolve_font_family("Helvetica Neue"),
            result_font_size,
        ))
        results.setStyleSheet(
            f"QListWidget {{ background-color: rgb({result_bg[0]}, {result_bg[1]}, {result_bg[2]}); "
            f"color: rgb({result_fg[0]}, {result_fg[1]}, {result_fg[2]}); "
            f"border: 1px solid rgb({result_border[0]}, {result_border[1]}, {result_border[2]}); "
            f"border-radius: {input_radius}px; outline: none; }} "
            f"QListWidget::item {{ padding: {int(result_padding[0])}px {int(result_padding[1])}px {int(result_padding[2])}px {int(result_padding[3])}px; }} "
            f"QListWidget::item:hover {{ background-color: rgb({result_hover[0]}, {result_hover[1]}, {result_hover[2]}); }} "
            f"QListWidget::item:selected {{ background-color: rgb({result_selected_bg[0]}, {result_selected_bg[1]}, {result_selected_bg[2]}); "
            f"color: rgb({result_selected_fg[0]}, {result_selected_fg[1]}, {result_selected_fg[2]}); }}"
        )
        tags_cfg = dialog_config.get("tags", {})
        if not isinstance(tags_cfg, dict):
            tags_cfg = {}
        results.setItemDelegate(
            EncyclopediaSearchResultDelegate(
                tags_cfg,
                name_color=result_fg,
                selected_name_color=result_selected_fg,
                parent=results,
            )
        )
        results.itemClicked.connect(self._on_search_result_clicked)
        self._search_results = results

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._perform_search)

        self._search_expanded_width = int(search_cfg.get("input_expanded_width", 220))
        self._results_min_width = int(search_cfg.get("results_min_width", 420))
        resources = (self.config.get("resources") or {})
        if not isinstance(resources, dict):
            resources = {}
        self._search_result_limit = max(
            1, int(resources.get("encyclopedia_search_results_limit", 15))
        )
        self._search_overflow_color = _rgb(
            search_cfg.get("overflow_text_color"),
            search_cfg.get("result_id_color", [140, 140, 148]),
        )
        self._search_overflow_font_size = int(
            scale_font_size(search_cfg.get("overflow_font_size", max(8, result_font_size - 1)))
        )
        self._search_overflow_template = str(
            search_cfg.get("overflow_text", "… {count} further results")
        )
        self._search_anim: Optional[QPropertyAnimation] = None
        return container

    def _available_geometry(self) -> QRect:
        """Work area of the screen this dialog is on (excludes taskbar/dock)."""
        screen = self.screen()
        if screen is None:
            center = self.frameGeometry().center()
            screen = QApplication.screenAt(center)
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1280, 800)
        return screen.availableGeometry()

    def _content_pt(self, base_size: float) -> int:
        """DPI-scale a base point size, then apply the encyclopedia text-size preference."""
        return max(
            1,
            int(round(scale_font_size(float(base_size)) * float(self._text_size_scale))),
        )

    def _text_size_label_for_key(self, key: str) -> str:
        for opt in self._text_size_options:
            if opt["id"] == key:
                return str(opt["label"])
        return _TEXT_SIZE_LABELS.get(key, key)

    def _refresh_content_fonts(self) -> None:
        title = getattr(self, "_title_label", None)
        if isinstance(title, QLabel):
            title.setFont(
                QFont(
                    getattr(self, "_title_font_family", title.font().family()),
                    self._content_pt(getattr(self, "_title_font_base", 14.0)),
                    QFont.Weight.Bold,
                )
            )
        section_pt = self._content_pt(getattr(self, "_section_font_base", 11.0))
        body_family = getattr(self, "_body_font_family", "Helvetica Neue")
        for heading in getattr(self, "_heading_labels", []):
            if isinstance(heading, QLabel):
                heading.setFont(QFont(body_family, section_pt, QFont.Weight.DemiBold))
        body_base_pt = self._content_pt(getattr(self, "_body_font_base", 11.0))
        for lab in getattr(self, "_body_labels", []):
            if not isinstance(lab, QLabel):
                continue
            emphasize = bool(getattr(lab, "_encyclopedia_emphasize", False))
            lab.setFont(QFont(body_family, body_base_pt + (1 if emphasize else 0)))
            # Clear fixed height so reflow remeasures.
            lab.setMinimumHeight(0)
            lab.setMaximumHeight(16777215)

    def _set_text_size(self, key: str) -> None:
        key = str(key or "").strip().lower()
        if key not in self._text_size_scales:
            return
        if key == self._text_size_key and abs(
            self._text_size_scale - float(self._text_size_scales[key])
        ) < 0.001:
            return
        self._text_size_key = key
        self._text_size_scale = float(self._text_size_scales[key])
        self._refresh_content_fonts()
        self._beside_block_count = None
        self._sync_scroll_content_size()
        try:
            from app.services.user_settings_service import UserSettingsService

            UserSettingsService.get_instance().update_opening_encyclopedia_dialog(
                {"text_size": key}
            )
        except Exception:
            pass

    def _usable_screen_size(self) -> Tuple[int, int]:
        avail = self._available_geometry()
        margin = self._size_screen_margin
        usable_w = max(1, avail.width() - 2 * margin)
        usable_h = max(1, avail.height() - 2 * margin)
        return usable_w, usable_h

    def _size_for_fractions(self, width_frac: float, height_frac: float) -> QSize:
        usable_w, usable_h = self._usable_screen_size()
        w = max(self._min_dialog_size.width(), int(usable_w * width_frac))
        h = max(self._min_dialog_size.height(), int(usable_h * height_frac))
        w = min(w, usable_w)
        h = min(h, usable_h)
        return QSize(w, h)

    def _size_for_fraction(self, fraction: float) -> QSize:
        return self._size_for_fractions(fraction, fraction)

    def _centered_geometry_for_size(self, size: QSize) -> QRect:
        """Client geometry that centers the window frame in the available screen."""
        avail = self._available_geometry()
        margin = self._size_screen_margin
        usable_w, usable_h = self._usable_screen_size()
        w = max(self._min_dialog_size.width(), min(size.width(), usable_w))
        h = max(self._min_dialog_size.height(), min(size.height(), usable_h))

        # geometry() is the client area; frameGeometry() includes decorations.
        # Center the outer frame, then convert back to a client rect for setGeometry.
        geo = self.geometry()
        frame = self.frameGeometry()
        if self.isVisible() and frame.isValid() and geo.isValid() and geo.width() > 0:
            dx = geo.x() - frame.x()
            dy = geo.y() - frame.y()
            extra_w = max(0, frame.width() - geo.width())
            extra_h = max(0, frame.height() - geo.height())
        else:
            dx = dy = 0
            extra_w = extra_h = 0

        frame_w = w + extra_w
        frame_h = h + extra_h
        frame_x = avail.x() + (avail.width() - frame_w) // 2
        frame_y = avail.y() + (avail.height() - frame_h) // 2
        frame_x = max(
            avail.x() + margin,
            min(frame_x, avail.right() - frame_w - margin + 1),
        )
        frame_y = max(
            avail.y() + margin,
            min(frame_y, avail.bottom() - frame_h - margin + 1),
        )
        return QRect(frame_x + dx, frame_y + dy, w, h)

    def _geometry_animation_reliable(self) -> bool:
        """False on Linux/Wayland where WMs often ignore animated moves."""
        app = QApplication.instance()
        platform = ((app.platformName() if app is not None else "") or "").lower()
        if platform.startswith("wayland"):
            return False
        if sys.platform.startswith("linux"):
            return False
        return True

    def _commit_window_geometry(self, end: QRect) -> None:
        """Resize then center via frameGeometry — reliable on Linux window managers.

        Many Linux WMs keep the top-left fixed across ``setGeometry``/animated
        resizes and only honor an explicit ``move`` after the size has settled.
        """
        size = end.size()
        self._center_reassert_token += 1
        token = self._center_reassert_token
        self._programmatic_resize = True
        self._suppress_size_persist = True
        try:
            self.resize(size)
            avail = self._available_geometry()
            margin = self._size_screen_margin
            fg = self.frameGeometry()
            # If the frame size hasn't updated yet, synthesize from client + prior chrome.
            if fg.width() < size.width() or fg.height() < size.height():
                geo = self.geometry()
                extra_w = max(0, fg.width() - max(1, geo.width()))
                extra_h = max(0, fg.height() - max(1, geo.height()))
                fg.setSize(QSize(size.width() + extra_w, size.height() + extra_h))
            fg.moveCenter(avail.center())
            if fg.left() < avail.left() + margin:
                fg.moveLeft(avail.left() + margin)
            if fg.top() < avail.top() + margin:
                fg.moveTop(avail.top() + margin)
            if fg.right() > avail.right() - margin:
                fg.moveRight(avail.right() - margin)
            if fg.bottom() > avail.bottom() - margin:
                fg.moveBottom(avail.bottom() - margin)
            self.move(fg.topLeft())
        finally:
            self._programmatic_resize = False
            self._suppress_size_persist = False
        # Re-assert once after the WM processes the resize. Cancelled if the user
        # starts a manual resize/move before it runs.
        QTimer.singleShot(0, lambda t=token: self._reassert_centered_on_screen(t))

    def _cancel_pending_center_reassert(self) -> None:
        """Invalidate any deferred screen-centering from a preset size change."""
        self._center_reassert_token += 1

    def _reassert_centered_on_screen(self, token: int) -> None:
        if token != self._center_reassert_token:
            return
        if not self.isVisible() or self._programmatic_resize:
            return
        avail = self._available_geometry()
        margin = self._size_screen_margin
        fg = self.frameGeometry()
        target = QRect(fg)
        target.moveCenter(avail.center())
        if target.left() < avail.left() + margin:
            target.moveLeft(avail.left() + margin)
        if target.top() < avail.top() + margin:
            target.moveTop(avail.top() + margin)
        if target.right() > avail.right() - margin:
            target.moveRight(avail.right() - margin)
        if target.bottom() > avail.bottom() - margin:
            target.moveBottom(avail.bottom() - margin)
        if abs(fg.x() - target.x()) > 2 or abs(fg.y() - target.y()) > 2:
            self._programmatic_resize = True
            self._suppress_size_persist = True
            try:
                self.move(target.topLeft())
            finally:
                self._programmatic_resize = False
                self._suppress_size_persist = False

    def _is_near_size(self, size: QSize, other: QSize, tol: int = _SIZE_AXIS_TOL_PX) -> bool:
        return abs(size.width() - other.width()) <= tol and abs(size.height() - other.height()) <= tol

    def _matched_frac_for_axis(self, axis: str) -> Optional[float]:
        """Return preset fraction if the given axis currently matches a preset size."""
        usable_w, usable_h = self._usable_screen_size()
        current = self.width() if axis == "w" else self.height()
        usable = usable_w if axis == "w" else usable_h
        minimum = (
            self._min_dialog_size.width()
            if axis == "w"
            else self._min_dialog_size.height()
        )
        for frac in self._size_presets:
            expected = max(minimum, int(usable * frac))
            expected = min(expected, usable)
            if abs(current - expected) <= _SIZE_AXIS_TOL_PX:
                return frac
        return None

    def _current_axis_fraction(self, axis: str) -> float:
        matched = self._matched_frac_for_axis(axis)
        if matched is not None:
            return matched
        usable_w, usable_h = self._usable_screen_size()
        if axis == "w":
            return max(0.05, min(1.0, self.width() / float(usable_w)))
        return max(0.05, min(1.0, self.height() / float(usable_h)))

    def _preset_key_for_fraction(self, fraction: float) -> str:
        for key, frac in _SIZE_PRESET_FRACTIONS.items():
            if abs(frac - fraction) < 0.001:
                return key
        for index, frac in enumerate(self._size_presets):
            if abs(frac - fraction) < 0.001 and index < len(_SIZE_PRESET_KEYS):
                return _SIZE_PRESET_KEYS[index]
        return "60"

    def _matching_equal_preset_key(self) -> Optional[str]:
        """Return equal-preset key when both axes match the same preset fraction."""
        w_frac = self._matched_frac_for_axis("w")
        h_frac = self._matched_frac_for_axis("h")
        if w_frac is None or h_frac is None:
            return None
        if abs(w_frac - h_frac) > 0.001:
            return None
        return self._preset_key_for_fraction(w_frac)

    def _matching_preset_key(self) -> Optional[str]:
        return self._matching_equal_preset_key()

    def _stop_size_anim(self) -> None:
        anim = getattr(self, "_size_anim", None)
        if anim is not None:
            self._suppress_size_persist = True
            try:
                anim.stop()
            finally:
                self._size_anim = None
                self._suppress_size_persist = False

    def _animate_to_geometry(self, end: QRect) -> None:
        if not self._geometry_animation_reliable():
            self._commit_window_geometry(end)
            self._persist_current_size()
            return
        if (
            abs(self.geometry().width() - end.width()) <= 2
            and abs(self.geometry().height() - end.height()) <= 2
            and abs(self.geometry().x() - end.x()) <= 2
            and abs(self.geometry().y() - end.y()) <= 2
        ):
            self._commit_window_geometry(end)
            return
        self._stop_size_anim()
        start = self.geometry()
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(220)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._suppress_size_persist = True

        def _finished() -> None:
            self._size_anim = None
            self._suppress_size_persist = False
            # Final frame-aware center (covers WMs that ignored mid-animation moves).
            self._commit_window_geometry(end)
            self._persist_current_size()

        anim.finished.connect(_finished)
        anim.start()
        self._size_anim = anim

    def _apply_size_fractions(
        self,
        width_frac: float,
        height_frac: float,
        *,
        animate: bool = True,
    ) -> None:
        if self._search_open:
            self._close_search()
        if self.isMaximized():
            self.showNormal()
        target = self._size_for_fractions(width_frac, height_frac)
        geom = self._centered_geometry_for_size(target)
        if abs(width_frac - height_frac) < 0.001:
            self._size_preset_key = self._preset_key_for_fraction(width_frac)
        else:
            self._size_preset_key = _SIZE_PRESET_CUSTOM
        if animate and self.isVisible():
            self._animate_to_geometry(geom)
        else:
            self._commit_window_geometry(geom)
            self._persist_current_size()

    def _apply_size_preset(self, fraction: float, *, animate: bool = True) -> None:
        self._apply_size_fractions(fraction, fraction, animate=animate)

    def _apply_width_fraction(self, width_frac: float, *, animate: bool = True) -> None:
        self._apply_size_fractions(
            width_frac,
            self._current_axis_fraction("h"),
            animate=animate,
        )

    def _apply_height_fraction(self, height_frac: float, *, animate: bool = True) -> None:
        self._apply_size_fractions(
            self._current_axis_fraction("w"),
            height_frac,
            animate=animate,
        )

    def _apply_custom_size(self, width: int, height: int, *, animate: bool = False) -> None:
        if self.isMaximized():
            self.showNormal()
        geom = self._centered_geometry_for_size(QSize(int(width), int(height)))
        self._size_preset_key = _SIZE_PRESET_CUSTOM
        if animate and self.isVisible():
            self._animate_to_geometry(geom)
        else:
            self._commit_window_geometry(geom)

    def _compute_auto_default_size(self) -> QSize:
        """Comfortable absolute reading size, clamped to the usable screen."""
        usable_w, usable_h = self._usable_screen_size()
        min_w = self._min_dialog_size.width()
        min_h = self._min_dialog_size.height()
        max_w = max(min_w, int(usable_w * float(self._default_max_screen_fraction)))
        max_h = max(min_h, int(usable_h * float(self._default_max_screen_fraction)))
        max_w = min(max_w, usable_w)
        max_h = min(max_h, usable_h)
        w = min(max(int(self._default_target_width), min_w), max_w)
        h = min(max(int(self._default_target_height), min_h), max_h)
        return QSize(w, h)

    def _apply_auto_default_size(self, *, animate: bool = False) -> None:
        """Apply the calculated default size and remember preset mode as default."""
        if self._search_open:
            self._close_search()
        if self.isMaximized():
            self.showNormal()
        target = self._compute_auto_default_size()
        geom = self._centered_geometry_for_size(target)
        self._size_preset_key = _SIZE_PRESET_DEFAULT
        if animate and self.isVisible():
            self._animate_to_geometry(geom)
        else:
            self._commit_window_geometry(geom)
            self._persist_current_size()

    def _is_near_auto_default_size(self) -> bool:
        return self._is_near_size(self.size(), self._compute_auto_default_size())

    def _persist_current_size(self) -> None:
        if getattr(self, "_suppress_size_persist", False):
            return
        usable_w, usable_h = self._usable_screen_size()
        width_pct = int(round((self.width() / float(usable_w)) * 100.0))
        height_pct = int(round((self.height() / float(usable_h)) * 100.0))
        width_pct = max(1, min(100, width_pct))
        height_pct = max(1, min(100, height_pct))

        matched = self._matching_equal_preset_key()
        if (
            self._size_preset_key == _SIZE_PRESET_DEFAULT
            and self._is_near_auto_default_size()
        ):
            # Prefer explicit default mode over a coincidental % match.
            preset_key = _SIZE_PRESET_DEFAULT
        elif matched is not None:
            preset_key = matched
            self._size_preset_key = matched
        else:
            preset_key = _SIZE_PRESET_CUSTOM
            self._size_preset_key = _SIZE_PRESET_CUSTOM

        payload = {
            "size_preset": preset_key,
            "width_pct": width_pct,
            "height_pct": height_pct,
            "width": self.width(),
            "height": self.height(),
            "text_size": self._text_size_key,
        }
        try:
            from app.services.user_settings_service import UserSettingsService

            UserSettingsService.get_instance().update_opening_encyclopedia_dialog(payload)
        except Exception:
            pass

    def _load_size_settings(self) -> Dict[str, Any]:
        try:
            from app.services.user_settings_service import UserSettingsService

            data = UserSettingsService.get_instance().get_opening_encyclopedia_dialog()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _pct_to_frac(self, value: Any) -> Optional[float]:
        try:
            pct = float(value)
        except (TypeError, ValueError):
            return None
        if pct > 1.0:
            pct = pct / 100.0
        if 0.05 <= pct <= 1.0:
            return pct
        return None

    def _settings_request_auto_default(self, settings: Dict[str, Any]) -> bool:
        """True when no user size choice exists yet, or default mode is active."""
        if not settings:
            return True
        preset = str(settings.get("size_preset") or "").strip().lower()
        preset = _SIZE_PRESET_LEGACY.get(preset, preset)
        if preset == _SIZE_PRESET_DEFAULT or preset == "":
            # Empty / default: only treat as auto if no explicit % or pixel size.
            if preset == _SIZE_PRESET_DEFAULT:
                return True
            has_pct = (
                self._pct_to_frac(settings.get("width_pct")) is not None
                and self._pct_to_frac(settings.get("height_pct")) is not None
            )
            try:
                width = int(settings.get("width") or 0)
                height = int(settings.get("height") or 0)
            except (TypeError, ValueError):
                width, height = 0, 0
            has_px = (
                width >= self._min_dialog_size.width()
                and height >= self._min_dialog_size.height()
            )
            return not has_pct and not has_px
        return False

    def _apply_persisted_or_default_size(self) -> None:
        """Restore last size, or compute a comfortable default when unset."""
        settings = self._load_size_settings()
        if self._settings_request_auto_default(settings):
            self._apply_auto_default_size(animate=False)
            return

        preset = str(settings.get("size_preset") or "").strip().lower()
        preset = _SIZE_PRESET_LEGACY.get(preset, preset)
        if preset in _SIZE_PRESET_FRACTIONS:
            self._apply_size_preset(_SIZE_PRESET_FRACTIONS[preset], animate=False)
            return

        if preset == _SIZE_PRESET_CUSTOM:
            try:
                width = int(settings.get("width") or 0)
                height = int(settings.get("height") or 0)
            except (TypeError, ValueError):
                width, height = 0, 0
            if (
                width >= self._min_dialog_size.width()
                and height >= self._min_dialog_size.height()
            ):
                self._apply_custom_size(width, height, animate=False)
                self._persist_current_size()
                return

        width_frac = self._pct_to_frac(settings.get("width_pct"))
        height_frac = self._pct_to_frac(settings.get("height_pct"))
        if width_frac is not None and height_frac is not None:
            self._apply_size_fractions(width_frac, height_frac, animate=False)
            return

        self._apply_auto_default_size(animate=False)

    def _current_size_percent_label(self) -> str:
        """Current size as independent W% × H% of usable screen."""
        usable_w, usable_h = self._usable_screen_size()
        pct_w = int(round((self.width() / float(usable_w)) * 100.0))
        pct_h = int(round((self.height() / float(usable_h)) * 100.0))
        pct_w = max(1, min(100, pct_w))
        pct_h = max(1, min(100, pct_h))
        return f"{pct_w}% × {pct_h}%"

    def _frac_percent_label(self, frac: Optional[float], *, axis: Optional[str] = None) -> str:
        if frac is not None:
            return f"{int(round(frac * 100))}%"
        if axis in ("w", "h"):
            usable_w, usable_h = self._usable_screen_size()
            usable = usable_w if axis == "w" else usable_h
            px = self.width() if axis == "w" else self.height()
            pct = int(round((px / float(usable)) * 100.0))
            return f"{max(1, min(100, pct))}%"
        return ""

    def _size_branch_title(self, section: str, detail: str) -> str:
        """Build a two-column menu title (label + value) using a tab stop."""
        detail = (detail or "").strip()
        if not detail:
            return section
        return f"{section}\t{detail}"

    def _populate_size_preset_submenu(
        self,
        submenu: QMenu,
        *,
        kind: str,
        active_frac: Optional[float],
        use_equal_labels: bool,
    ) -> None:
        group = QActionGroup(submenu)
        group.setExclusive(True)
        for index, frac in enumerate(self._size_presets):
            if use_equal_labels:
                label = (
                    self._size_equal_labels[index]
                    if index < len(self._size_equal_labels)
                    else f"{int(round(frac * 100))}% × {int(round(frac * 100))}%"
                )
            else:
                label = (
                    self._size_preset_labels[index]
                    if index < len(self._size_preset_labels)
                    else f"{int(round(frac * 100))}%"
                )
            action = QAction(label, submenu)
            action.setCheckable(True)
            action.setChecked(
                active_frac is not None and abs(active_frac - frac) < 0.001
            )
            action.setData((kind, frac))
            group.addAction(action)
            submenu.addAction(action)

    def _show_size_menu(self) -> None:
        if self._search_open:
            self._close_search()
        btn = getattr(self, "_size_toggle_btn", None)
        if btn is None:
            return

        menu = QMenu(self)
        apply_menu_styling(menu, self.config)
        icon_tint = menu_icon_dark_tint_rgb(self.config)
        size_cfg = (
            (self._dialog_config.get("size_toggle") or {})
            if isinstance(self._dialog_config, dict)
            else {}
        )
        if not isinstance(size_cfg, dict):
            size_cfg = {}

        def _branch_icon(config_key: str, default_svg: str) -> Any:
            svg = str(size_cfg.get(config_key) or default_svg)
            return themed_icon_from_svg(svg, icon_tint)

        equal_key = self._matching_equal_preset_key()
        width_frac = self._matched_frac_for_axis("w")
        height_frac = self._matched_frac_for_axis("h")
        equal_frac = (
            _SIZE_PRESET_FRACTIONS.get(equal_key) if equal_key is not None else None
        )
        if equal_frac is None and equal_key is not None:
            try:
                equal_frac = float(equal_key) / 100.0
            except (TypeError, ValueError):
                equal_frac = None

        equal_menu = menu.addMenu(
            self._size_branch_title(
                self._size_section_equal,
                self._frac_percent_label(equal_frac)
                if equal_frac is not None
                else "—",
            )
        )
        equal_menu.menuAction().setIcon(
            _branch_icon("icon_equal_svg", SVG_MENU_SIZE_EQUAL)
        )
        apply_menu_styling(equal_menu, self.config)
        self._populate_size_preset_submenu(
            equal_menu,
            kind="equal",
            active_frac=equal_frac,
            use_equal_labels=True,
        )

        width_menu = menu.addMenu(
            self._size_branch_title(
                self._size_section_width,
                self._frac_percent_label(width_frac, axis="w"),
            )
        )
        width_menu.menuAction().setIcon(
            _branch_icon("icon_width_svg", SVG_MENU_SIZE_WIDTH)
        )
        apply_menu_styling(width_menu, self.config)
        self._populate_size_preset_submenu(
            width_menu,
            kind="width",
            active_frac=width_frac,
            use_equal_labels=False,
        )

        height_menu = menu.addMenu(
            self._size_branch_title(
                self._size_section_height,
                self._frac_percent_label(height_frac, axis="h"),
            )
        )
        height_menu.menuAction().setIcon(
            _branch_icon("icon_height_svg", SVG_MENU_SIZE_HEIGHT)
        )
        apply_menu_styling(height_menu, self.config)
        self._populate_size_preset_submenu(
            height_menu,
            kind="height",
            active_frac=height_frac,
            use_equal_labels=False,
        )

        menu.addSeparator()
        reset_action = QAction(self._size_reset_label, menu)
        reset_action.setIcon(
            themed_icon_from_svg(
                str(size_cfg.get("icon_reset_svg") or SVG_MENU_RESET),
                icon_tint,
            )
        )
        reset_action.setData((_SIZE_PRESET_DEFAULT, None))
        on_default = (
            self._size_preset_key == _SIZE_PRESET_DEFAULT
            and self._is_near_auto_default_size()
        )
        reset_action.setEnabled(not on_default)
        menu.addAction(reset_action)

        menu.addSeparator()
        text_menu = menu.addMenu(
            self._size_branch_title(
                self._text_size_section,
                self._text_size_label_for_key(self._text_size_key),
            )
        )
        text_size_cfg = size_cfg.get("text_size", {})
        text_icon_svg = SVG_MENU_TEXT_SIZE
        if isinstance(text_size_cfg, dict):
            text_icon_svg = str(text_size_cfg.get("icon_svg") or SVG_MENU_TEXT_SIZE)
        text_menu.menuAction().setIcon(themed_icon_from_svg(text_icon_svg, icon_tint))
        apply_menu_styling(text_menu, self.config)
        text_group = QActionGroup(text_menu)
        text_group.setExclusive(True)
        for opt in self._text_size_options:
            opt_id = str(opt["id"])
            action = QAction(str(opt["label"]), text_menu)
            action.setIcon(
                _letter_a_menu_icon(int(opt["menu_a_pt"]), icon_tint)
            )
            action.setCheckable(True)
            action.setChecked(opt_id == self._text_size_key)
            action.setData(("text_size", opt_id))
            text_group.addAction(action)
            text_menu.addAction(action)

        if equal_key is None:
            menu.addSeparator()
            if (
                self._size_preset_key == _SIZE_PRESET_DEFAULT
                and self._is_near_auto_default_size()
            ):
                default_action = QAction(
                    self._size_branch_title(
                        "Default", self._current_size_percent_label()
                    ),
                    menu,
                )
                default_action.setCheckable(True)
                default_action.setChecked(True)
                default_action.setData((_SIZE_PRESET_DEFAULT, None))
                menu.addAction(default_action)
            else:
                custom = QAction(
                    self._size_branch_title(
                        "Custom", self._current_size_percent_label()
                    ),
                    menu,
                )
                custom.setCheckable(True)
                custom.setChecked(True)
                custom.setData((_SIZE_PRESET_CUSTOM, None))
                menu.addAction(custom)

        chosen = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if chosen is None:
            return
        data = chosen.data()
        if not isinstance(data, (tuple, list)) or len(data) < 2:
            return
        kind, value = data[0], data[1]
        if kind == _SIZE_PRESET_DEFAULT:
            self._apply_auto_default_size(animate=True)
            return
        if kind == _SIZE_PRESET_CUSTOM:
            return
        if kind == "text_size":
            self._set_text_size(str(value))
            return
        try:
            fraction = float(value)
        except (TypeError, ValueError):
            return
        if kind == "equal":
            self._apply_size_preset(fraction, animate=True)
        elif kind == "width":
            self._apply_width_fraction(fraction, animate=True)
        elif kind == "height":
            self._apply_height_fraction(fraction, animate=True)

    def _open_feedback_dialog(self) -> None:
        if self._search_open:
            self._close_search()
        from app.views.dialogs.opening_encyclopedia_feedback_dialog import (
            OpeningEncyclopediaFeedbackDialog,
        )

        OpeningEncyclopediaFeedbackDialog.show_for_entry(
            self.config, self._entry, parent=self
        )

    def _is_search_ui_global_pos(self, global_pos) -> bool:
        """True if ``global_pos`` hits the search chrome (button/input/results/tools)."""
        widgets = (
            getattr(self, "_search_container", None),
            getattr(self, "_search_btn", None),
            getattr(self, "_search_input", None),
            getattr(self, "_search_results", None),
            getattr(self, "_size_toggle_btn", None),
            getattr(self, "_feedback_btn", None),
        )
        for w in widgets:
            if w is None or not w.isVisible():
                continue
            local = w.mapFromGlobal(global_pos)
            if w.rect().contains(local):
                return True
        return False

    def _sync_title_fade(self, search_width: Optional[int] = None) -> None:
        """Place/hide the title fade to match the floating search field."""
        fade = getattr(self, "_title_fade", None)
        title = self._title_label
        if fade is None or title is None:
            return
        if not self._search_open:
            fade.hide()
            return
        tw = max(1, title.width())
        th = max(1, title.height())
        sw = int(search_width) if search_width is not None else max(0, self._search_input.width())
        fade_w = max(
            self._search_fade_min_width,
            min(tw, sw + max(0, self._search_fade_extra)),
        )
        fade.setGeometry(tw - fade_w, 0, fade_w, th)
        fade.show()
        fade.raise_()

    def _toggle_search(self) -> None:
        if self._search_open:
            self._close_search()
        else:
            self._open_search()

    def _position_search_input(self, width: int) -> None:
        """Place the floating search input to the left of the search button."""
        btn = self._search_btn
        inp = self._search_input
        btn_pos = btn.mapTo(self, btn.rect().topRight())
        x = btn_pos.x() - width - 4
        y = btn_pos.y() + (btn.height() - inp.height()) // 2
        x = max(12, x)
        inp.move(x, y)
        inp.setFixedWidth(width)
        self._sync_title_fade(width)

    def _stop_search_anim(self) -> None:
        anim = getattr(self, "_search_anim", None)
        if anim is not None:
            anim.stop()
            self._search_anim = None

    def _open_search(self) -> None:
        self._search_open = True
        inp = self._search_input
        self._stop_search_anim()
        self._position_search_input(0)
        inp.setVisible(True)
        inp.raise_()
        self._sync_title_fade(0)
        anim = QPropertyAnimation(inp, b"minimumWidth", self)
        anim.setDuration(200)
        anim.setStartValue(0)
        anim.setEndValue(self._search_expanded_width)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: self._position_search_input(int(v)))
        anim.start()
        self._search_anim = anim
        inp.setFocus()

    def _close_search(self) -> None:
        if not self._search_open and not self._search_input.isVisible():
            return
        self._search_open = False
        self._search_input.clear()
        self._search_results.setVisible(False)
        inp = self._search_input
        self._stop_search_anim()
        start_w = max(0, inp.width())
        if start_w <= 0:
            inp.setVisible(False)
            self._sync_title_fade(0)
            return
        anim = QPropertyAnimation(inp, b"minimumWidth", self)
        anim.setDuration(150)
        anim.setStartValue(start_w)
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def _on_width(v: object) -> None:
            w = int(v)
            self._position_search_input(w)
            if w <= 0:
                self._sync_title_fade(0)

        anim.valueChanged.connect(_on_width)

        def _on_finished() -> None:
            inp.setVisible(False)
            self._sync_title_fade(0)

        anim.finished.connect(_on_finished)
        anim.start()
        self._search_anim = anim

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if (
            self._search_open
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            if not self._is_search_ui_global_pos(event.globalPosition().toPoint()):
                self._close_search()
        return super().eventFilter(obj, event)

    def done(self, result: int) -> None:  # noqa: N802
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().done(result)

    def _on_search_text_changed(self, text: str) -> None:
        if not text.strip():
            self._search_results.setVisible(False)
            return
        self._search_timer.start()

    def _perform_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            self._search_results.setVisible(False)
            return
        page = self._encyclopedia.search(query, limit=self._search_result_limit)
        self._search_results.clear()
        if not page.results:
            self._search_results.setVisible(False)
            return
        for r in page.results:
            eco_list = self._parse_eco_codes(r.eco_codes)
            eco_label = ""
            if eco_list:
                eco_codes = ", ".join(eco_list[:3])
                if len(eco_list) > 3:
                    eco_codes += f" (+{len(eco_list) - 3})"
                eco_label = f"ECO: {eco_codes}"
            item = QListWidgetItem(r.display_name)
            item.setData(Qt.ItemDataRole.UserRole, r.opening_id)
            if eco_label:
                item.setData(ECO_CHIP_ROLE, eco_label)
            self._search_results.addItem(item)

        remaining = max(0, int(page.total) - len(page.results))
        if remaining > 0:
            overflow = QListWidgetItem(
                self._search_overflow_template.format(count=remaining)
            )
            overflow.setFlags(Qt.ItemFlag.NoItemFlags)
            overflow.setForeground(QColor(*self._search_overflow_color))
            overflow_font = QFont(self._search_results.font())
            overflow_font.setPointSize(self._search_overflow_font_size)
            overflow_font.setItalic(True)
            overflow.setFont(overflow_font)
            overflow.setData(Qt.ItemDataRole.UserRole, None)
            self._search_results.addItem(overflow)

        self._position_search_results()
        self._search_results.setVisible(True)
        self._search_results.raise_()

    def _position_search_results(self) -> None:
        """Place the results dropdown below the search input."""
        inp = self._search_input
        results = self._search_results
        if not inp.isVisible():
            return
        # Prefer a wide panel so longer opening names stay readable.
        available = max(200, self.width() - 40)
        w = min(available, max(self._results_min_width, inp.width() + 160))
        pos = inp.mapTo(self, inp.rect().bottomRight())
        x = max(12, min(pos.x() - w, self.width() - w - 12))
        y = pos.y() + 2
        results.setFixedWidth(w)
        results.move(x, y)
        results.adjustSize()

    def _on_search_result_clicked(self, item: QListWidgetItem) -> None:
        opening_id = item.data(Qt.ItemDataRole.UserRole)
        if not opening_id:
            return
        entry = self._encyclopedia.get_entry_by_id(str(opening_id))
        if entry is None:
            return
        config = self.config
        encyclopedia = self._encyclopedia
        parent = self.parentWidget()
        self._close_search()
        self.accept()
        # Defer opening the next modal dialog until this one has fully exited.
        QTimer.singleShot(
            0,
            lambda: OpeningEncyclopediaDialog.show_entry(
                config, entry, encyclopedia, parent
            ),
        )

    def _build_image_column(
        self,
        entry: EncyclopediaEntry,
        encyclopedia_service: OpeningEncyclopediaService,
        dialog_config: Dict[str, Any],
    ) -> QWidget:
        """Non-scrolling portrait column (scrolls with the dialog content)."""
        images = entry.images
        column_w = int(dialog_config.get("thumbnail_max_width", 160))
        slot_spacing = int(dialog_config.get("image_slot_spacing", 14))

        caption_color = _rgb(dialog_config.get("caption_color"), [150, 150, 155])
        caption_size = int(scale_font_size(dialog_config.get("caption_font_size", 9)))
        credit_color = _rgb(dialog_config.get("credit_color"), caption_color)
        credit_size = min(8, int(scale_font_size(dialog_config.get("credit_font_size", 8))))
        link_color = _rgb(
            dialog_config.get("credit_link_color"),
            dialog_config.get("move_highlight", {}).get("text_color", [100, 150, 255]),
        )

        host = QWidget()
        host.setFixedWidth(column_w)
        host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        host.setStyleSheet("background: transparent;")
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(slot_spacing)
        col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        for image in images:
            block = self._build_image_block(
                entry.opening_id,
                image,
                encyclopedia_service,
                column_w=column_w,
                caption_color=caption_color,
                caption_size=caption_size,
                credit_color=credit_color,
                credit_size=credit_size,
                link_color=link_color,
            )
            if block is None:
                continue
            col.addWidget(block, 0, Qt.AlignmentFlag.AlignHCenter)

        host.adjustSize()
        host.setMinimumHeight(max(1, host.sizeHint().height()))
        return host

    def _open_gallery(self, index: int) -> None:
        if self._gallery_overlay is None:
            return
        self._gallery_overlay.open_at(index)

    def _build_image_block(
        self,
        opening_id: str,
        image: EncyclopediaImage,
        encyclopedia_service: OpeningEncyclopediaService,
        *,
        column_w: int,
        caption_color: list[int],
        caption_size: int,
        credit_color: list[int],
        credit_size: int,
        link_color: list[int],
    ) -> Optional[QWidget]:
        raw = encyclopedia_service.get_image_bytes(opening_id, image.slot)
        if not raw:
            return None
        pix = QPixmap()
        if not pix.loadFromData(raw):
            return None
        fitted = _fit_pixmap(pix, column_w)
        gallery_index = len(self._gallery_pixmaps)
        self._gallery_pixmaps.append(pix)
        self._gallery_images.append(image)

        block = QWidget()
        block.setFixedWidth(column_w)
        block.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        block.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        thumb = _ClickableImageLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        thumb.setScaledContents(False)
        thumb.setStyleSheet("background: transparent; border: none;")
        thumb.setPixmap(fitted)
        thumb.setFixedSize(column_w, fitted.height())
        thumb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        thumb.clicked.connect(lambda idx=gallery_index: self._open_gallery(idx))
        layout.addWidget(thumb, 0, Qt.AlignmentFlag.AlignHCenter)

        caption = format_image_caption(image)
        if caption:
            cap = QLabel(caption)
            cap.setWordWrap(True)
            cap.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            cap.setFixedWidth(column_w)
            cap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            cap.setStyleSheet(
                f"color: rgb({caption_color[0]}, {caption_color[1]}, {caption_color[2]}); "
                f"font-size: {caption_size}pt; background: transparent; border: none;"
            )
            layout.addWidget(cap)

        credit_html = format_image_credit_html(
            image,
            credit_color=credit_color,
            link_color=link_color,
            font_size_pt=credit_size,
        )
        if credit_html:
            credit = QLabel()
            credit.setWordWrap(True)
            credit.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            credit.setFixedWidth(column_w)
            credit.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            credit.setTextFormat(Qt.TextFormat.RichText)
            credit.setOpenExternalLinks(False)
            credit.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            credit.linkActivated.connect(
                lambda url: open_url(QUrl(url), context="encyclopedia.image_source")
            )
            credit.setStyleSheet(
                f"color: rgb({credit_color[0]}, {credit_color[1]}, {credit_color[2]}); "
                f"font-size: {credit_size}pt; background: transparent; border: none;"
            )
            credit.setText(credit_html)
            layout.addWidget(credit)

        block.adjustSize()
        # Prevent parent compression from stacking caption onto the image.
        block.setMinimumHeight(max(1, block.sizeHint().height()))
        return block

    @staticmethod
    def _measure_label_height(lab: QLabel, width: int) -> int:
        """Measure wrapped label height at ``width``."""
        width = max(1, int(width))
        if lab.textFormat() == Qt.TextFormat.RichText:
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setDefaultFont(lab.font())
            doc.setHtml(lab.text())
            doc.setTextWidth(float(width))
            return max(1, int(doc.size().height()) + lab.fontMetrics().descent() + 4)
        hfw = lab.heightForWidth(width)
        return hfw if hfw > 0 else max(1, lab.sizeHint().height())

    def _fit_label_to_width(self, lab: QLabel, width: int) -> int:
        """Update label geometry for ``width`` only when values change."""
        width = max(1, int(width))
        h = self._measure_label_height(lab, width)
        if lab.maximumWidth() != width:
            lab.setMaximumWidth(width)
        if lab.minimumWidth() != 0:
            lab.setMinimumWidth(0)
        if lab.height() != h or lab.minimumHeight() != h or lab.maximumHeight() != h:
            lab.setFixedHeight(h)
        return h

    def _estimate_block_height(self, block: QWidget, width: int) -> int:
        """Measure block height at ``width`` without mutating widgets."""
        lab = getattr(block, "_encyclopedia_body", None)
        body_h = (
            self._measure_label_height(lab, width) if isinstance(lab, QLabel) else 0
        )
        chrome = 0
        lay = block.layout()
        if lay is not None:
            for i in range(lay.count()):
                item = lay.itemAt(i)
                w = item.widget() if item is not None else None
                if w is None or w is lab:
                    continue
                chrome += max(0, w.sizeHint().height())
            chrome += max(0, lay.spacing()) * max(0, lay.count() - 1)
        if body_h:
            return body_h + chrome
        return max(1, block.sizeHint().height())

    def _fit_block_to_width(self, block: QWidget, width: int) -> int:
        lab = getattr(block, "_encyclopedia_body", None)
        body_h = self._fit_label_to_width(lab, width) if isinstance(lab, QLabel) else 0
        chrome = 0
        lay = block.layout()
        if lay is not None:
            for i in range(lay.count()):
                item = lay.itemAt(i)
                w = item.widget() if item is not None else None
                if w is None or w is lab:
                    continue
                chrome += max(0, w.sizeHint().height())
            chrome += max(0, lay.spacing()) * max(0, lay.count() - 1)
        return body_h + chrome if body_h else max(1, block.sizeHint().height())

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _image_column_height(self) -> int:
        if self._image_panel is None:
            return 0
        return max(
            self._image_panel.minimumHeight(),
            self._image_panel.sizeHint().height(),
        )

    def _desired_beside_count(self, beside_w: int, image_h: int) -> int:
        """How many section blocks should sit beside the images at ``beside_w``."""
        if image_h <= 0:
            return len(self._section_blocks)
        spacing = (
            max(0, self._beside_layout.spacing()) if self._beside_layout is not None else 10
        )
        used = 0
        count = 0
        for block in self._section_blocks:
            if used >= image_h:
                break
            used += spacing + self._estimate_block_height(block, beside_w)
            count += 1
        return count

    def _apply_section_placement(self, beside_count: int) -> None:
        """Reparent sections only when the beside/below split changes."""
        beside = self._beside_layout
        below = self._below_layout
        if beside is None or below is None:
            return
        if self._beside_block_count == beside_count and beside.count() > 0:
            return

        self._clear_layout(beside)
        self._clear_layout(below)
        for i, block in enumerate(self._section_blocks):
            if i < beside_count:
                beside.addWidget(block)
            else:
                below.addWidget(block)
        if self._below_host is not None:
            self._below_host.setVisible(below.count() > 0)
        self._beside_block_count = beside_count

    def _measure_laid_out_heights(
        self, beside_w: int, full_w: int, image_h: int
    ) -> Tuple[int, int]:
        """Fit visible labels and return ``(top_row_height, below_height)``."""
        beside = self._beside_layout
        below = self._below_layout
        if beside is None or below is None:
            return 0, 0

        beside_h = 0
        spacing = max(0, beside.spacing())
        below_spacing = max(0, below.spacing())

        below_h = 0
        first_below = True
        for i, block in enumerate(self._section_blocks):
            if image_h and i >= (self._beside_block_count or 0):
                bh = self._fit_block_to_width(block, full_w)
                if not first_below:
                    below_h += below_spacing
                below_h += bh
                first_below = False
            else:
                w = beside_w if image_h else full_w
                beside_h += spacing + self._fit_block_to_width(block, w)

        top_h = max(beside_h, image_h) if image_h else beside_h
        return top_h, below_h

    def _sync_scroll_content_size(self) -> None:
        """Reflow only when split changes; otherwise just retarget widths/heights."""
        host = self._content_host
        scroll = self._scroll
        if host is None or scroll is None:
            return
        viewport_w = scroll.viewport().width()
        if viewport_w <= 0:
            return

        lay = host.layout()
        margins = lay.contentsMargins() if lay is not None else None
        inner_w = viewport_w
        pad_y = 0
        if margins is not None:
            inner_w = max(80, viewport_w - margins.left() - margins.right())
            pad_y = margins.top() + margins.bottom()

        image_w = 0
        if self._image_panel is not None:
            image_w = max(
                self._image_panel.minimumWidth(),
                self._image_panel.sizeHint().width(),
            )
        gap = self._image_text_gap if image_w else 0
        image_h = self._image_column_height()
        beside_w = max(80, inner_w - image_w - gap) if image_w else inner_w

        beside_count = self._desired_beside_count(beside_w, image_h)
        self._apply_section_placement(beside_count)
        top_h, below_h = self._measure_laid_out_heights(beside_w, inner_w, image_h)

        content_h = top_h + pad_y
        if below_h > 0 and lay is not None:
            content_h += lay.spacing() + below_h
        content_h = max(1, content_h)

        if host.width() != viewport_w or host.height() != content_h:
            host.setFixedSize(viewport_w, content_h)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Floating search is positioned absolutely; collapse it on any real resize
        # so it doesn't linger in the old spot after maximize / drag-resize.
        old = event.oldSize()
        if old.isValid() and event.size() != old and self._search_open:
            self._close_search()

        # Free user resize → remember as custom (debounced); skip animation frames.
        if (
            old.isValid()
            and event.size() != old
            and not getattr(self, "_suppress_size_persist", False)
            and not getattr(self, "_programmatic_resize", False)
            and self._size_applied_on_show
        ):
            # User is drag-resizing: never snap back to screen center.
            self._cancel_pending_center_reassert()
            self._size_persist_timer.start()

        if self._search_open:
            self._sync_title_fade()

        if self._gallery_overlay is not None and self._gallery_overlay.isVisible():
            self._gallery_overlay.refresh_geometry()
        # Keep width in sync immediately; debounce full text reflow to avoid flicker.
        if self._content_host is not None and self._scroll is not None:
            vw = self._scroll.viewport().width()
            if vw > 0 and self._content_host.width() != vw:
                self._content_host.setFixedWidth(vw)
        self._resize_sync_timer.start()

    def moveEvent(self, event: QMoveEvent) -> None:  # noqa: N802
        super().moveEvent(event)
        # User drag-move should cancel a pending preset recenter.
        if (
            self._size_applied_on_show
            and not getattr(self, "_programmatic_resize", False)
            and not getattr(self, "_suppress_size_persist", False)
        ):
            self._cancel_pending_center_reassert()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._gallery_overlay is not None and self._gallery_overlay.isVisible():
                self._gallery_overlay.close_gallery()
                return
            if self._search_open:
                self._close_search()
                return
        super().keyPressEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._size_applied_on_show:
            self._apply_persisted_or_default_size()
            self._size_applied_on_show = True
        self._beside_block_count = None  # force initial placement
        self._sync_scroll_content_size()

    @staticmethod
    def show_entry(
        config: Dict[str, Any],
        entry: EncyclopediaEntry,
        encyclopedia_service: OpeningEncyclopediaService,
        parent=None,
    ) -> None:
        dialog = OpeningEncyclopediaDialog(config, entry, encyclopedia_service, parent)
        dialog.exec()
