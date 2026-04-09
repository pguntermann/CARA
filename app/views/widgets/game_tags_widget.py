"""Board-attached widget showing per-game tags as bubbles (display only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QPushButton,
    QSizePolicy,
)

from app.services.game_tags_service import GameTagsService
from app.utils.game_tags_utils import parse_game_tags, PGN_TAG_NAME_GAME_TAGS
from app.utils.font_utils import resolve_font_family, scale_font_size


class GameTagsWidget(QWidget):
    """Widget that renders CARAGameTags as bubbles (no assignment UI)."""

    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._svc = GameTagsService(self.config)
        self._game_model = None
        self._metadata_controller = None
        self._active_game = None
        self._chips: List[QPushButton] = []

        self._load_config()

        # Board-attached widgets use fixed width; height is set by the board view.
        self.setFixedWidth(self.widget_width)
        if getattr(self, "min_interactive_height", 0) and self.min_interactive_height > 0:
            self.setMinimumHeight(int(self.min_interactive_height))
        if self.max_height and self.max_height > 0:
            self.setMaximumHeight(self.max_height)

        self._refresh()

    def _load_config(self) -> None:
        board_cfg = (self.config.get("ui", {}) or {}).get("panels", {}).get("main", {}).get("board", {})
        tags_cfg = board_cfg.get("game_tags_widget", {})
        self.widget_width = int(tags_cfg.get("width", 170))
        self.min_interactive_height = int(tags_cfg.get("min_interactive_height", 0))
        # max_height: if <= 0, board will size this widget to available height.
        self.max_height = int(tags_cfg.get("max_height", 0))
        self.flow_spacing = int(tags_cfg.get("flow_spacing", 6))

        chip_cfg = tags_cfg.get("chip", {}) if isinstance(tags_cfg.get("chip", {}), dict) else {}
        self.chip_border_radius = int(chip_cfg.get("border_radius", 10))
        self.chip_padding = chip_cfg.get("padding", [2, 8])  # [v, h]
        self.chip_min_height = int(chip_cfg.get("minimum_height", 22))
        self.chip_unmanaged_bg = chip_cfg.get("unmanaged_background_color", [95, 95, 100])
        self.chip_hover_bg = chip_cfg.get("hover_background_rgba", [255, 255, 255, 18])

        font_family_raw = chip_cfg.get("font_family", "Helvetica Neue")
        self.chip_font_family = resolve_font_family(font_family_raw)
        self.chip_font_size = int(scale_font_size(chip_cfg.get("font_size", 11)))
        self.chip_font_weight = str(chip_cfg.get("font_weight", "bold")).strip().lower()

    def set_context(self, game_model: Any, metadata_controller: Any) -> None:
        """Provide models/controllers needed for interaction."""
        if self._game_model is not None:
            try:
                self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
            except Exception:
                pass
            try:
                self._game_model.game_tags_changed.disconnect(self._on_game_tags_changed)
            except Exception:
                pass

        self._game_model = game_model
        self._metadata_controller = metadata_controller
        if self._game_model is not None:
            self._game_model.active_game_changed.connect(self._on_active_game_changed)
            self._game_model.game_tags_changed.connect(self._on_game_tags_changed)
            self._active_game = getattr(self._game_model, "active_game", None)
        self._refresh()

        # Enable context menu (mirrors Tag menu) once we can reach a main window.
        if not hasattr(self, "_ctx_enabled"):
            self._ctx_enabled = False
        if not self._ctx_enabled:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._on_context_menu_requested)
            self._ctx_enabled = True

    def _find_main_window(self) -> Optional[Any]:
        w = self.parent()
        # Walk up QObject parent chain to find an object that looks like MainWindow.
        while w is not None:
            if hasattr(w, "controller") and hasattr(w, "config") and hasattr(w, "manage_tags_action"):
                return w
            w = getattr(w, "parent", lambda: None)()
        return None

    def _on_context_menu_requested(self, pos) -> None:
        mw = self._find_main_window()
        if mw is None:
            return
        from app.views.menus.game_tags_context_menu import build_game_tags_context_menu

        menu = build_game_tags_context_menu(mw, parent=self)
        menu.exec(self.mapToGlobal(pos))

    def _on_active_game_changed(self, game: Any) -> None:
        self._active_game = game
        self._refresh()

    def _on_game_tags_changed(self) -> None:
        self._refresh()

    def _current_tags(self) -> List[str]:
        g = self._active_game
        if not g:
            return []
        raw = getattr(g, "game_tags_raw", None)
        if raw is None:
            # Fallback: try to parse from PGN if field isn't present
            raw = ""
            pgn = getattr(g, "pgn", "") or ""
            if "[CARAGameTags" in pgn:
                try:
                    import chess.pgn
                    from io import StringIO

                    io_ = StringIO(pgn)
                    game_obj = chess.pgn.read_game(io_)
                    if game_obj:
                        raw = game_obj.headers.get(PGN_TAG_NAME_GAME_TAGS, "") or ""
                except Exception:
                    raw = ""
        return parse_game_tags(raw or "")

    def _set_tags(self, tags: List[str]) -> None:
        if not self._active_game or not self._metadata_controller:
            return
        raw = format_game_tags(tags)
        if raw:
            self._metadata_controller.update_metadata_tag(PGN_TAG_NAME_GAME_TAGS, raw)
        else:
            self._metadata_controller.remove_metadata_tag(PGN_TAG_NAME_GAME_TAGS)

    def _refresh(self) -> None:
        # Remove existing chips
        for w in self._chips:
            w.setParent(None)
            w.deleteLater()
        self._chips = []

        tags = self._current_tags()
        defs_map = self._svc.get_definition_map()

        for name in tags:
            d = defs_map.get(name.casefold())
            color = d.color if d else (95, 95, 100)
            chip = self._make_chip(name, color, managed=bool(d))
            chip.show()
            self._chips.append(chip)

        # Ensure we render above the board paint content.
        self.raise_()

        self._layout_chips()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_chips()

    def _layout_chips(self) -> None:
        """Deterministically place chips with wrapping (no Qt layout manager)."""
        if not self._chips:
            return
        w_total = max(1, int(self.width()))
        spacing = int(self.flow_spacing)
        x = 0
        y = 0
        line_h = 0

        for chip in self._chips:
            try:
                chip.ensurePolished()
                chip.adjustSize()
            except Exception:
                pass
            try:
                sh = chip.sizeHint()
            except Exception:
                sh = QSize(chip.minimumWidth(), chip.minimumHeight())

            cw = max(int(chip.minimumWidth()), int(sh.width()), 1)
            ch = max(int(chip.minimumHeight()), int(sh.height()), 1)

            if x > 0 and x + cw > w_total:
                x = 0
                y += line_h + spacing
                line_h = 0

            chip.setGeometry(int(x), int(y), int(min(cw, w_total)), int(ch))
            x += min(cw, w_total) + spacing
            line_h = max(line_h, ch)

    def _make_chip(self, name: str, color: Tuple[int, int, int], *, managed: bool) -> QPushButton:
        btn = QPushButton(name, self)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setMinimumHeight(int(self.chip_min_height))
        btn.setFlat(True)
        btn.setEnabled(False)

        # Apply configurable font (try bold text for better legibility).
        font = QFont(self.chip_font_family, self.chip_font_size)
        if self.chip_font_weight in ("bold", "700", "800", "900"):
            font.setBold(True)
        btn.setFont(font)

        if managed:
            q = QColor(int(color[0]), int(color[1]), int(color[2]))
        else:
            ubg = self.chip_unmanaged_bg if isinstance(self.chip_unmanaged_bg, list) else [95, 95, 100]
            q = QColor(int(ubg[0]), int(ubg[1]), int(ubg[2]))
        # Full opacity, no borders.
        bg = f"rgb({q.red()}, {q.green()}, {q.blue()})"
        text = "rgb(15, 15, 18)" if (0.2126 * q.red() + 0.7152 * q.green() + 0.0722 * q.blue()) > 150 else "rgb(245, 245, 245)"
        pad_v = int(self.chip_padding[0]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 1 else 2
        pad_h = int(self.chip_padding[1]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 2 else 8
        # Force a deterministic minimum width so flow layout advances correctly.
        try:
            text_w = btn.fontMetrics().horizontalAdvance(name)
        except Exception:
            text_w = len(name) * 7
        btn.setMinimumWidth(int(text_w + 2 * pad_h + 8))

        btn.setStyleSheet(
            "QPushButton {"
            f"  background-color: {bg};"
            f"  color: {text};"
            f"  border-radius: {self.chip_border_radius}px;"
            f"  padding: {pad_v}px {pad_h}px;"
            "}"
            "QPushButton:disabled {"
            f"  background-color: {bg};"
            f"  color: {text};"
            "}"
        )
        if not managed:
            btn.setToolTip("Unmanaged tag (from shared PGN)")
        return btn

