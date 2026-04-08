from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QStyledItemDelegate, QStyle, QStyleOptionViewItem

from app.services.game_tags_service import GameTagsService
from app.utils.game_tags_utils import parse_game_tags
from app.utils.font_utils import resolve_font_family, scale_font_size


class DatabaseTagsChipDelegate(QStyledItemDelegate):
    """Paint single-line tag chips in the database Tags column (display-only)."""

    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._svc = GameTagsService(config)

        board_cfg = (config.get("ui", {}) or {}).get("panels", {}).get("main", {}).get("board", {})
        tags_cfg = board_cfg.get("game_tags_widget", {}) if isinstance(board_cfg, dict) else {}
        self.flow_spacing = int(tags_cfg.get("flow_spacing", 6))

        chip_cfg = tags_cfg.get("chip", {}) if isinstance(tags_cfg.get("chip", {}), dict) else {}
        self.chip_border_radius = int(chip_cfg.get("border_radius", 10))
        self.chip_padding = chip_cfg.get("padding", [2, 8])  # [v, h]
        self.chip_min_height = int(chip_cfg.get("minimum_height", 22))
        self.chip_unmanaged_bg = chip_cfg.get("unmanaged_background_color", [95, 95, 100])

        font_family_raw = chip_cfg.get("font_family", "Helvetica Neue")
        self.chip_font_family = resolve_font_family(font_family_raw)
        self.chip_font_size = int(scale_font_size(chip_cfg.get("font_size", 11)))
        self.chip_font_weight = str(chip_cfg.get("font_weight", "bold")).strip().lower()

        table_cfg = (config.get("ui", {}) or {}).get("panels", {}).get("database", {}).get("table", {})
        tags_col_cfg = table_cfg.get("tags_column", {}) if isinstance(table_cfg, dict) else {}
        self.cell_padding = tags_col_cfg.get("cell_padding", [4, 2])  # [x, y]

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        # Draw the standard cell background/selection, but suppress the model text.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        model = index.model()
        row = index.row()

        # Try to get raw tag list from the underlying game to avoid parsing display text.
        raw = ""
        try:
            if hasattr(model, "get_game"):
                game = model.get_game(row)
                raw = getattr(game, "game_tags_raw", "") or ""
        except Exception:
            raw = ""
        if not raw:
            # Fallback: parse whatever the model displays.
            try:
                raw = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")
            except Exception:
                raw = ""

        tags = parse_game_tags(raw)
        if not tags:
            return

        defs_map = self._svc.get_definition_map()

        pad_x = int(self.cell_padding[0]) if isinstance(self.cell_padding, list) and len(self.cell_padding) >= 1 else 4
        pad_y = int(self.cell_padding[1]) if isinstance(self.cell_padding, list) and len(self.cell_padding) >= 2 else 2

        r = option.rect.adjusted(pad_x, pad_y, -pad_x, -pad_y)
        if r.width() <= 2 or r.height() <= 2:
            return

        font = QFont(self.chip_font_family, self.chip_font_size)
        if self.chip_font_weight in ("bold", "700", "800", "900"):
            font.setBold(True)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(font)

        fm = QFontMetrics(font)
        pad_v = int(self.chip_padding[0]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 1 else 2
        pad_h = int(self.chip_padding[1]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 2 else 8
        spacing = max(1, int(self.flow_spacing))

        x = int(r.x())
        y = int(r.y() + max(0, (r.height() - self.chip_min_height) / 2))
        max_right = int(r.right())

        def chip_colors(tag_name: str) -> Tuple[QColor, QColor]:
            d = defs_map.get(tag_name.casefold())
            if d:
                bg = QColor(int(d.color[0]), int(d.color[1]), int(d.color[2]))
            else:
                ubg = self.chip_unmanaged_bg if isinstance(self.chip_unmanaged_bg, list) else [95, 95, 100]
                bg = QColor(int(ubg[0]), int(ubg[1]), int(ubg[2]))
            lum = 0.2126 * bg.red() + 0.7152 * bg.green() + 0.0722 * bg.blue()
            fg = QColor(15, 15, 18) if lum > 150 else QColor(245, 245, 245)
            return bg, fg

        def chip_width(text: str) -> int:
            return int(fm.horizontalAdvance(text) + 2 * pad_h + 8)

        remaining = len(tags)
        for i, t in enumerate(tags):
            remaining = len(tags) - i
            w = chip_width(t)
            if x + w > max_right and i > 0:
                # No wrap in table cell; show overflow indicator if possible.
                overflow = f"+{remaining}"
                ow = chip_width(overflow)
                if x + ow <= max_right:
                    bg, fg = chip_colors(overflow)
                    self._paint_chip(painter, QRect(x, y, ow, self.chip_min_height), overflow, bg, fg, pad_h)
                break

            bg, fg = chip_colors(t)
            w = min(w, max(1, max_right - x))
            self._paint_chip(painter, QRect(x, y, w, self.chip_min_height), t, bg, fg, pad_h)
            x += w + spacing
            if x > max_right:
                break

        painter.restore()

    def tag_at_pos(self, option: QStyleOptionViewItem, index, local_pos) -> Optional[str]:
        """Hit-test: return the tag name at a local cell position, or None.

        This mirrors the same single-line chip layout used in paint().
        """
        model = index.model()
        row = index.row()

        raw = ""
        try:
            if hasattr(model, "get_game"):
                game = model.get_game(row)
                raw = getattr(game, "game_tags_raw", "") or ""
        except Exception:
            raw = ""
        if not raw:
            try:
                raw = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")
            except Exception:
                raw = ""

        tags = parse_game_tags(raw)
        if not tags:
            return None

        pad_x = int(self.cell_padding[0]) if isinstance(self.cell_padding, list) and len(self.cell_padding) >= 1 else 4
        pad_y = int(self.cell_padding[1]) if isinstance(self.cell_padding, list) and len(self.cell_padding) >= 2 else 2

        r = option.rect.adjusted(pad_x, pad_y, -pad_x, -pad_y)
        if r.width() <= 2 or r.height() <= 2:
            return None

        font = QFont(self.chip_font_family, self.chip_font_size)
        if self.chip_font_weight in ("bold", "700", "800", "900"):
            font.setBold(True)
        fm = QFontMetrics(font)
        pad_h = int(self.chip_padding[1]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 2 else 8
        spacing = max(1, int(self.flow_spacing))

        x = int(r.x())
        y = int(r.y() + max(0, (r.height() - self.chip_min_height) / 2))
        max_right = int(r.right())

        lx = int(local_pos.x())
        ly = int(local_pos.y())
        if not (y <= ly <= y + int(self.chip_min_height)):
            return None

        def chip_width(text: str) -> int:
            return int(fm.horizontalAdvance(text) + 2 * pad_h + 8)

        remaining = len(tags)
        for i, t in enumerate(tags):
            remaining = len(tags) - i
            w = chip_width(t)
            if x + w > max_right and i > 0:
                # Overflow chip (e.g. "+2") is not treated as a clickable tag.
                return None
            w = min(w, max(1, max_right - x))
            if x <= lx <= x + w:
                return t
            x += w + spacing
            if x > max_right:
                break
        return None

    def _paint_chip(self, painter: QPainter, rect: QRect, text: str, bg: QColor, fg: QColor, pad_h: int) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, self.chip_border_radius, self.chip_border_radius)
        painter.setPen(fg)
        text_rect = rect.adjusted(pad_h, 0, -pad_h, 0)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)

