"""Castling rights widget (pills) for board HUD."""

from __future__ import annotations

from typing import Dict, Any, Optional, Tuple

import chess
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QBrush, QPen
from PyQt6.QtWidgets import QWidget

from app.models.board_model import BoardModel
from app.utils.font_utils import resolve_font_family, scale_font_size


class CastlingRightsWidget(QWidget):
    """Render castling rights as small pills (K/Q/k/q)."""

    def __init__(self, config: Dict[str, Any], board_model: Optional[BoardModel] = None, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._board_model: Optional[BoardModel] = None
        self._wk = self._wq = self._bk = self._bq = False
        self._requested_visible: bool = True
        self._load_config()
        if board_model is not None:
            self.set_model(board_model)

    def _load_config(self) -> None:
        ui_cfg = (self.config.get("ui") or {})
        board_cfg = (ui_cfg.get("panels", {}) or {}).get("main", {}).get("board", {})
        cfg = board_cfg.get("castling_rights_widget", {}) if isinstance(board_cfg.get("castling_rights_widget", {}), dict) else {}

        self.pill_size = cfg.get("pill_size", [18, 14])  # [w, h]
        self.spacing_x = int(cfg.get("spacing_x", 4))
        self.spacing_y = int(cfg.get("spacing_y", 3))
        self.border_radius = int(cfg.get("border_radius", 7))
        self.border_width = int(cfg.get("border_width", 1))
        self.padding = cfg.get("padding", [0, 0, 0, 0])  # [t,r,b,l] for layout placement calc
        self.gone_text = str(cfg.get("gone_text", "-"))

        font_family = resolve_font_family(cfg.get("font_family", "Helvetica Neue"))
        font_size = int(scale_font_size(cfg.get("font_size", 10)))
        font_weight = str(cfg.get("font_weight", "bold")).strip().lower()
        self._font = QFont(font_family, font_size)
        if font_weight in ("bold", "700", "800", "900"):
            self._font.setBold(True)

        # Per-side colors (white row vs black row). Fall back to enabled_* for older configs.
        enabled_bg = cfg.get("enabled_background_color", [70, 90, 130])
        enabled_text = cfg.get("enabled_text_color", [240, 240, 240])
        enabled_border = cfg.get("enabled_border_color", [100, 120, 160])

        self.white_bg = QColor(*cfg.get("white_background_color", enabled_bg))
        self.white_text = QColor(*cfg.get("white_text_color", enabled_text))
        self.white_border = QColor(*cfg.get("white_border_color", enabled_border))

        self.black_bg = QColor(*cfg.get("black_background_color", enabled_bg))
        self.black_text = QColor(*cfg.get("black_text_color", enabled_text))
        self.black_border = QColor(*cfg.get("black_border_color", enabled_border))

        # Fixed widget size (2x2 pills) to avoid jitter.
        pw, ph = int(self.pill_size[0]), int(self.pill_size[1])
        w = 2 * pw + self.spacing_x
        h = 2 * ph + self.spacing_y
        self.setFixedSize(int(w), int(h))

    def set_model(self, model: BoardModel) -> None:
        if self._board_model is model:
            return
        if self._board_model is not None:
            try:
                self._board_model.position_changed.disconnect(self._on_position_changed)
            except Exception:
                pass
        self._board_model = model
        if model is not None:
            model.position_changed.connect(self._on_position_changed)
        self._update_rights()
        self._sync_visibility()
        self.update()

    def set_requested_visible(self, visible: bool) -> None:
        """Set whether the user wants this widget shown (subject to rights existing)."""
        self._requested_visible = bool(visible)
        self._sync_visibility()
        self.update()

    def _on_position_changed(self) -> None:
        self._update_rights()
        self._sync_visibility()
        self.update()

    def _update_rights(self) -> None:
        b = self._board_model.board if self._board_model is not None else chess.Board()
        self._wk = bool(b.has_kingside_castling_rights(chess.WHITE))
        self._wq = bool(b.has_queenside_castling_rights(chess.WHITE))
        self._bk = bool(b.has_kingside_castling_rights(chess.BLACK))
        self._bq = bool(b.has_queenside_castling_rights(chess.BLACK))

    def _sync_visibility(self) -> None:
        # Visibility is controlled by the user setting; rights themselves affect labels only.
        self.setVisible(bool(self._requested_visible))

    def rights_tuple(self) -> Tuple[bool, bool, bool, bool]:
        return (self._wk, self._wq, self._bk, self._bq)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)

        pw, ph = int(self.pill_size[0]), int(self.pill_size[1])
        fm = QFontMetrics(self._font)

        from PyQt6.QtCore import QRect

        def draw_pill(
            x: int,
            y: int,
            text: str,
            *,
            show_label: bool,
            bg: QColor,
            fg: QColor,
            border: QColor,
        ) -> None:
            rect = QRect(int(x), int(y), int(pw), int(ph))
            painter.setBrush(QBrush(bg))
            if int(self.border_width) <= 0:
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                pen = QPen(border)
                pen.setWidth(int(self.border_width))
                painter.setPen(pen)
            painter.drawRoundedRect(rect, self.border_radius, self.border_radius)
            label = text if show_label else self.gone_text
            if label:
                painter.setPen(QPen(fg))
                tx = x + (pw - fm.horizontalAdvance(label)) // 2
                ty = y + (ph + fm.ascent() - fm.descent()) // 2
                painter.drawText(int(tx), int(ty), label)

        # Row 0: White (K, Q) ; Row 1: Black (k, q)
        x0 = 0
        y0 = 0
        draw_pill(
            x0,
            y0,
            "K",
            show_label=self._wk,
            bg=self.white_bg,
            fg=self.white_text,
            border=self.white_border,
        )
        draw_pill(
            x0 + pw + self.spacing_x,
            y0,
            "Q",
            show_label=self._wq,
            bg=self.white_bg,
            fg=self.white_text,
            border=self.white_border,
        )

        y1 = ph + self.spacing_y
        draw_pill(
            x0,
            y1,
            "k",
            show_label=self._bk,
            bg=self.black_bg,
            fg=self.black_text,
            border=self.black_border,
        )
        draw_pill(
            x0 + pw + self.spacing_x,
            y1,
            "q",
            show_label=self._bq,
            bg=self.black_bg,
            fg=self.black_text,
            border=self.black_border,
        )

