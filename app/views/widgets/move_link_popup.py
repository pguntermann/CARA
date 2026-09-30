"""Caret popup for a linked move in the game summary.

The window is frameless and translucent so the caret and rounded body are
painted by us. That shape is the same on macOS, Windows, and Linux; native
``QToolTip`` cannot host a board widget or a caret reliably on all three.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import chess
from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style.tooltip import TooltipStyle, load_tooltip_style
from app.views.widgets.mini_chessboard_widget import MiniChessBoardWidget

# Highlight sentences wrap here so a long subtitle does not stretch the popup.
_SUBTITLE_WRAP_WIDTH = 280


@dataclass(frozen=True)
class MoveLinkTip:
    """Content for one linked-move hover."""

    title: str
    subtitle: str
    details: Tuple[Tuple[str, str], ...] = ()
    fen: str = ""
    arrow_uci: str = ""
    alternative_uci: str = ""


def move_from_uci(uci: str) -> Optional[chess.Move]:
    """Parse a UCI string, or return None when it is blank or invalid."""
    text = str(uci or "").strip()
    if not text:
        return None
    try:
        return chess.Move.from_uci(text)
    except ValueError:
        return None


def position_board_arrows(
    *,
    played_uci: str,
    alternative_uci: str,
    played_color: Tuple[int, int, int],
    alternative_color: Tuple[int, int, int],
    show_alternative: bool,
) -> List[Tuple[chess.Move, List[int]]]:
    """Played-move arrow, then the best alternative when it is a different move."""
    arrows: List[Tuple[chess.Move, List[int]]] = []
    played = move_from_uci(played_uci)
    if played is not None:
        arrows.append((played, list(played_color)))
    if show_alternative:
        alternative = move_from_uci(alternative_uci)
        if alternative is not None and alternative != played:
            arrows.append((alternative, list(alternative_color)))
    return arrows


def uci_from_san(fen_before: str, san: str) -> str:
    """UCI of ``san`` on the position before the played move, or empty if it cannot be parsed."""
    text = str(san or "").strip()
    fen = str(fen_before or "").strip()
    if not text or not fen:
        return ""
    try:
        return chess.Board(fen).parse_san(text).uci()
    except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
        return ""


def clamp_caret_center(
    caret_x: int,
    popup_width: int,
    caret_size: int,
    border_radius: int,
    border_width: int,
) -> int:
    """Keep the caret on the straight edge, clear of the rounded corners."""
    half = max(1, int(caret_size))
    inset = max(half + 1, int(border_width) + int(border_radius) + half)
    lo = inset
    hi = max(lo, int(popup_width) - inset)
    return max(lo, min(int(caret_x), hi))


def place_move_link_popup(
    *,
    anchor_left: int,
    anchor_top: int,
    anchor_width: int,
    anchor_height: int,
    popup_width: int,
    popup_height: int,
    screen_left: int,
    screen_top: int,
    screen_right: int,
    screen_bottom: int,
    caret_size: int,
    anchor_gap: int,
    border_radius: int,
    border_width: int,
) -> Tuple[int, int, str, int]:
    """Place the popup beside the anchor.

    Returns ``(x, y, caret_edge, caret_center_x)``. ``caret_edge`` is ``"top"``
    when the popup sits below the anchor (caret points up) and ``"bottom"``
    when it sits above.
    """
    anchor_cx = int(anchor_left) + int(anchor_width) // 2
    x = anchor_cx - int(popup_width) // 2
    x = max(int(screen_left), min(x, int(screen_right) - int(popup_width)))

    gap = max(0, int(anchor_gap))
    below_y = int(anchor_top) + int(anchor_height) + gap
    above_y = int(anchor_top) - gap - int(popup_height)
    fits_below = below_y + int(popup_height) <= int(screen_bottom)
    fits_above = above_y >= int(screen_top)
    if fits_below or not fits_above:
        y = below_y
        edge = "top"
        if y + int(popup_height) > int(screen_bottom):
            y = max(int(screen_top), int(screen_bottom) - int(popup_height))
    else:
        y = above_y
        edge = "bottom"

    caret_x = clamp_caret_center(
        anchor_cx - x,
        popup_width,
        caret_size,
        border_radius,
        border_width,
    )
    return x, y, edge, caret_x


class MoveLinkPopup(QWidget):
    """Hover popup: themed body, caret aimed at the linked move, optional board."""

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._style = load_tooltip_style(config)
        self._config = config
        self._anchor: Optional[QWidget] = None
        self._caret_edge = "top"
        self._caret_x = 0
        self._content_size = QSize(0, 0)

        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        family = resolve_font_family(self._style.font_family)
        self._title_font = QFont(family, max(8, scale_font_size(self._style.title_font_size)))
        self._title_font.setBold(self._style.title_font_weight.lower() == "bold")
        self._body_font = QFont(family, max(8, scale_font_size(self._style.font_size)))

        self._content = QWidget(self)
        self._content.setAutoFillBackground(False)
        bg = self._style.background
        self._content.setStyleSheet(
            f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); border: none;"
        )

        row = QHBoxLayout(self._content)
        row.setContentsMargins(
            self._style.padding,
            self._style.padding,
            self._style.padding,
            self._style.padding,
        )
        row.setSpacing(10)

        self._board: Optional[MiniChessBoardWidget] = None
        if self._style.show_position_board:
            self._board = MiniChessBoardWidget(
                config,
                chess.STARTING_FEN,
                embedded=True,
                size_override=self._style.position_board_size,
            )
            self._board.hide()
            row.addWidget(self._board, 0, Qt.AlignmentFlag.AlignTop)

        text_host = QWidget()
        text_host.setAutoFillBackground(False)
        text_host.setStyleSheet(self._content.styleSheet())
        text_host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        text_layout = QVBoxLayout(text_host)
        self._text_host = text_host
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        self._title = self._make_label(self._title_font, self._style.title_color)
        self._subtitle = self._make_label(self._body_font, self._style.text)
        self._subtitle.setWordWrap(True)
        self._separator = QWidget()
        self._separator.setFixedHeight(1)
        sep = self._style.separator_color
        self._separator.setStyleSheet(
            f"background-color: rgb({sep[0]}, {sep[1]}, {sep[2]}); border: none;"
        )
        self._details_host = QWidget()
        self._details_host.setAutoFillBackground(False)
        self._details_host.setStyleSheet(self._content.styleSheet())
        self._details_layout = QVBoxLayout(self._details_host)
        self._details_layout.setContentsMargins(0, 2, 0, 0)
        self._details_layout.setSpacing(2)

        text_layout.addWidget(self._title)
        text_layout.addWidget(self._subtitle)
        text_layout.addWidget(self._separator)
        text_layout.addWidget(self._details_host)
        row.addWidget(text_host, 0, Qt.AlignmentFlag.AlignTop)

    @property
    def hover_delay_ms(self) -> int:
        return self._style.hover_delay_ms

    def present(self, anchor: QWidget, tip: MoveLinkTip, *, is_flipped: bool) -> None:
        """Show ``tip`` with the caret aimed at ``anchor``."""
        if not anchor.isVisible():
            return
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        self.present_at(
            QRect(top_left, anchor.size()),
            tip,
            is_flipped=is_flipped,
            owner=anchor,
        )

    def present_at(
        self,
        global_rect: QRect,
        tip: MoveLinkTip,
        *,
        is_flipped: bool,
        owner: QWidget,
    ) -> None:
        """Show ``tip`` with the caret aimed at a rectangle in global coordinates."""
        if global_rect.isEmpty() or not owner.isVisible():
            return
        self._anchor = owner
        self._apply_tip(tip, is_flipped=is_flipped)
        # Drop the previous tip's fixed size before measuring. A layout pass
        # against that old box squeezes the new labels and they paint over
        # each other.
        unbounded = 16777215
        self.setMinimumSize(0, 0)
        self.setMaximumSize(unbounded, unbounded)
        self._content.setMinimumSize(0, 0)
        self._content.setMaximumSize(unbounded, unbounded)
        self._text_host.setMinimumSize(0, 0)
        self._text_host.setMaximumSize(unbounded, unbounded)
        content_size = self._preferred_content_size()
        content_layout = self._content.layout()
        if content_layout is not None:
            content_layout.invalidate()
            hinted = content_layout.sizeHint()
            if hinted.isValid():
                content_size = hinted.expandedTo(content_size)
        self._content_size = content_size
        self._content.setFixedSize(content_size)
        radius = self._style.border_radius
        popup_width = max(1, content_size.width() + 2 * radius)
        popup_height = max(1, content_size.height() + self._style.caret_size + 2 * radius)
        self.setFixedSize(popup_width, popup_height)
        if content_layout is not None:
            content_layout.invalidate()
            content_layout.activate()
        self._relayout_details()

        screen = QGuiApplication.screenAt(global_rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x, y, edge, caret_x = place_move_link_popup(
            anchor_left=global_rect.left(),
            anchor_top=global_rect.top(),
            anchor_width=global_rect.width(),
            anchor_height=global_rect.height(),
            popup_width=popup_width,
            popup_height=popup_height,
            screen_left=avail.left(),
            screen_top=avail.top(),
            screen_right=avail.right(),
            screen_bottom=avail.bottom(),
            caret_size=self._style.caret_size,
            anchor_gap=self._style.anchor_gap,
            border_radius=self._style.border_radius,
            border_width=self._style.border_width,
        )
        self._caret_edge = edge
        self._caret_x = caret_x
        self._place_content()
        self.update()
        self.move(x, y)
        self.show()
        self.raise_()

    def hide_for(self, anchor: QWidget) -> None:
        """Hide when ``anchor`` is the label that opened this popup."""
        if self._anchor is anchor:
            self._anchor = None
            self.hide()

    def hide(self) -> None:  # noqa: A003
        self._anchor = None
        super().hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_content()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = self._shape_path()
        bg = self._style.background
        border = self._style.border
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg[0], bg[1], bg[2]))
        painter.drawPath(path)
        if self._style.border_width > 0:
            pen = QPen(QColor(border[0], border[1], border[2]))
            pen.setWidth(self._style.border_width)
            pen.setCosmetic(True)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def _apply_tip(self, tip: MoveLinkTip, *, is_flipped: bool) -> None:
        self._title.setText(tip.title)
        self._subtitle.setText(tip.subtitle)
        self._subtitle.setVisible(bool(tip.subtitle))
        self._separator.setVisible(bool(tip.details))
        self._clear_details()
        label_width = self._label_column_width(tip.details)
        for label, value in tip.details:
            self._details_layout.addWidget(self._detail_row(label, value, label_width))
        self._details_host.setVisible(bool(tip.details))

        if self._board is None:
            return
        if not tip.fen:
            self._board.hide()
            return
        self._board.set_position(tip.fen)
        self._board.set_flipped(is_flipped)
        self._board.set_arrows(self._board_arrows(tip))
        self._board.show()

    def _board_arrows(self, tip: MoveLinkTip) -> List[Tuple[chess.Move, List[int]]]:
        """Played move in the theme color, then the best alternative when it differs."""
        style = self._style
        return position_board_arrows(
            played_uci=tip.arrow_uci,
            alternative_uci=tip.alternative_uci,
            played_color=style.played_move_arrow_color,
            alternative_color=style.best_alternative_arrow_color,
            show_alternative=style.show_best_alternative_arrow,
        )

    def _clear_details(self) -> None:
        while self._details_layout.count():
            item = self._details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _relayout_details(self) -> None:
        """Place detail rows even when the text box size did not change.

        Qt skips ``setGeometry`` when a widget's rectangle is unchanged, so
        rows added for the next move would keep the default 640×480 size and
        paint on top of each other.
        """
        if self._details_layout.count() == 0:
            return
        # Rows created while the popup is already open stay hidden, and a
        # hidden layout item is skipped, so they keep the default size and
        # stack on one line.
        self._details_host.show()
        for index in range(self._details_layout.count()):
            item = self._details_layout.itemAt(index)
            row = item.widget() if item is not None else None
            if row is not None:
                row.show()
        self._details_layout.invalidate()
        self._details_layout.setGeometry(self._details_host.contentsRect())
        for index in range(self._details_layout.count()):
            item = self._details_layout.itemAt(index)
            row = item.widget() if item is not None else None
            row_layout = row.layout() if row is not None else None
            if row is None or row_layout is None:
                continue
            row_layout.invalidate()
            row_layout.setGeometry(row.contentsRect())

    def _label_column_width(self, details: Tuple[Tuple[str, str], ...]) -> int:
        return max((self._label_text_size(label, self._body_font)[0] for label, _value in details), default=0)

    def _wrapped_text_size(self, text: str, font: QFont, max_width: int) -> Tuple[int, int]:
        """One line when it fits, otherwise wrapped inside ``max_width``."""
        if not text:
            return 0, 0
        metrics = QFontMetrics(font)
        line_height = metrics.height() + 2
        single_width = metrics.boundingRect(text).width() + 4
        if single_width <= max_width:
            return single_width, line_height
        rect = metrics.boundingRect(
            QRect(0, 0, max_width, 10_000),
            int(Qt.TextFlag.TextWordWrap),
            text,
        )
        return max_width, max(line_height, rect.height() + 2)

    def _label_text_size(self, text: str, font: QFont) -> Tuple[int, int]:
        """Pixel size of one line, with slack so a stylesheet cannot clip it."""
        if not text:
            return 0, 0
        metrics = QFontMetrics(font)
        width = metrics.boundingRect(text).width() + 4
        return width, metrics.height() + 2

    def _preferred_content_size(self) -> QSize:
        """Size the body from the current text and board, ignoring the last tip."""
        title_w, title_h = self._label_text_size(self._title.text(), self._title_font)
        self._title.setMinimumSize(title_w, title_h)
        blocks: list[Tuple[int, int]] = [(title_w, title_h)]

        if self._subtitle.isVisible() and self._subtitle.text():
            sub_w, sub_h = self._wrapped_text_size(
                self._subtitle.text(), self._body_font, _SUBTITLE_WRAP_WIDTH
            )
            self._subtitle.setMinimumSize(sub_w, sub_h)
            self._subtitle.setMaximumWidth(sub_w)
            blocks.append((sub_w, sub_h))
        else:
            self._subtitle.setMinimumSize(0, 0)
            self._subtitle.setMaximumWidth(16777215)

        detail_w, detail_h, rows = self._detail_block_size()
        if self._separator.isVisible():
            blocks.append((0, max(1, self._separator.height())))
        if rows:
            blocks.append((detail_w, detail_h))

        text_w = max((width for width, _height in blocks), default=0)
        text_spacing = 0
        text_layout = self._text_host.layout()
        if text_layout is not None:
            text_spacing = text_layout.spacing()
        text_h = sum(height for _width, height in blocks)
        if len(blocks) > 1:
            text_h += text_spacing * (len(blocks) - 1)
        self._text_host.setMinimumSize(text_w, text_h)

        board_w = 0
        board_h = 0
        if self._board is not None and not self._board.isHidden():
            board_w = self._board.width()
            board_h = self._board.height()

        margins = self._content.layout().contentsMargins() if self._content.layout() else None
        left = margins.left() if margins is not None else 0
        right = margins.right() if margins is not None else 0
        top = margins.top() if margins is not None else 0
        bottom = margins.bottom() if margins is not None else 0
        gap = 0
        if board_w and text_w and self._content.layout() is not None:
            gap = self._content.layout().spacing()
        return QSize(
            max(1, left + right + board_w + gap + text_w),
            max(1, top + bottom + max(board_h, text_h)),
        )

    def _detail_block_size(self) -> Tuple[int, int, int]:
        detail_w = 0
        detail_h = 0
        rows = 0
        spacing = self._details_layout.spacing()
        for index in range(self._details_layout.count()):
            item = self._details_layout.itemAt(index)
            row = item.widget() if item is not None else None
            row_layout = row.layout() if row is not None else None
            if row_layout is None or row_layout.count() < 2:
                continue
            name = row_layout.itemAt(0).widget()
            value = row_layout.itemAt(1).widget()
            if not isinstance(name, QLabel) or not isinstance(value, QLabel):
                continue
            _name_text_w, name_h = self._label_text_size(name.text(), self._body_font)
            value_w, value_h = self._label_text_size(value.text(), self._body_font)
            # Keep every label at the shared column width. A later minimum-size
            # pass used to shrink short labels back to their own text, so the
            # values started at different x positions.
            column_w = name.maximumWidth()
            if column_w >= 16777215:
                column_w = _name_text_w
            name.setFixedWidth(column_w)
            name.setMinimumHeight(name_h)
            value.setMinimumSize(value_w, value_h)
            row_w = column_w + row_layout.spacing() + value_w
            row_h = max(name_h, value_h)
            row.setMinimumSize(row_w, row_h)
            row_layout.invalidate()
            detail_w = max(detail_w, row_w)
            detail_h += row_h
            rows += 1
        if rows > 1:
            detail_h += (rows - 1) * spacing
        if rows:
            detail_h += self._details_layout.contentsMargins().top()
            detail_h += self._details_layout.contentsMargins().bottom()
        self._details_layout.invalidate()
        self._details_host.setMinimumSize(detail_w, detail_h)
        self._details_host.updateGeometry()
        return detail_w, detail_h, rows

    def _detail_row(self, label: str, value: str, label_width: int) -> QWidget:
        row = QWidget()
        row.setAutoFillBackground(False)
        row.setStyleSheet(self._content.styleSheet())
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        name = self._make_label(self._body_font, self._style.muted_color)
        name.setText(label)
        name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if label_width > 0:
            name.setFixedWidth(label_width)
        shown = self._make_label(self._body_font, self._style.text)
        shown.setText(value)
        shown.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(name, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(shown, 1, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _make_label(self, font: QFont, color: Tuple[int, int, int]) -> QLabel:
        label = QLabel()
        label.setFont(font)
        bg = self._style.background
        label.setStyleSheet(
            f"QLabel {{ color: rgb({color[0]}, {color[1]}, {color[2]}); "
            f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); "
            f"border: none; padding: 0px; margin: 0px; }}"
        )
        return label

    def _place_content(self) -> None:
        """Keep the text and board inside the straight part of the rounded body."""
        radius = self._style.border_radius
        caret = self._style.caret_size
        if self._caret_edge == "top":
            top = caret + radius
        else:
            top = radius
        self._content.setGeometry(
            radius,
            top,
            max(0, self._content_size.width()),
            max(0, self._content_size.height()),
        )

    def _shape_path(self) -> QPainterPath:
        style = self._style
        caret = float(style.caret_size)
        radius = float(style.border_radius)
        inset = max(0.5, style.border_width / 2.0)
        width = float(self.width())
        height = float(self.height())
        if self._caret_edge == "top":
            body = QRectF(inset, caret + inset, width - 2 * inset, height - caret - 2 * inset)
            tip_y = inset
            base_y = caret + inset + 1.0
        else:
            body = QRectF(inset, inset, width - 2 * inset, height - caret - 2 * inset)
            tip_y = height - inset
            base_y = height - caret - inset - 1.0
        center = float(self._caret_x)
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        triangle = QPainterPath()
        triangle.moveTo(center - caret, base_y)
        triangle.lineTo(center, tip_y)
        triangle.lineTo(center + caret, base_y)
        triangle.closeSubpath()
        return path.united(triangle)
