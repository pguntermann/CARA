"""Dialog to manage custom game tag definitions.

This dialog uses a chip-style presentation instead of a table:
- Built-in tags are shown as read-only chips (color preview).
- Custom tags are editable cards with swatch + inline name + delete.

Colors/presentation are config-driven and use StyleManager.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QColor, QPalette, QPainter, QPen, QPixmap, QIcon, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QLineEdit,
    QSizePolicy,
    QColorDialog,
    QWidget,
    QScrollArea,
)

from app.services.game_tags_service import GameTagsService, GameTagDefinition
from app.services.user_settings_service import UserSettingsService
from app.views.style import StyleManager
from app.utils.font_utils import resolve_font_family, scale_font_size


class ColorSwatchButton(QPushButton):
    """Button that displays a color swatch and opens color picker on click."""

    def __init__(self, color: QColor, size: int, parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self._size = size
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_icon()

    def set_color(self, color: QColor) -> None:
        self._color = color
        self._update_icon()

    def get_color(self) -> QColor:
        return self._color

    def _update_icon(self) -> None:
        pixmap = QPixmap(self._size, self._size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawEllipse(1, 1, self._size - 2, self._size - 2)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(self._size, self._size))
        self.setStyleSheet("border: none; background: transparent;")


@dataclass
class _CustomRowState:
    name: str
    color: Tuple[int, int, int]


class _RemovableChipButton(QPushButton):
    def __init__(self, label: str, on_remove, parent=None) -> None:
        super().__init__(label, parent)
        self._base_label = label
        self._on_remove = on_remove
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._handle_click)
        # Avoid layout jitter: reserve space for the remove indicator.
        try:
            fm = self.fontMetrics()
            self.setMinimumWidth(int(fm.horizontalAdvance(f"{label}  ✕") + 16))
        except Exception:
            pass
        self._sync_text()

    def get_base_label(self) -> str:
        return self._base_label

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._sync_text()
        return super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._sync_text()
        return super().leaveEvent(event)

    def _sync_text(self) -> None:
        if self._hovered:
            self.setText(f"{self._base_label}  ✕")
            self.setToolTip("Click to remove tag")
        else:
            self.setText(self._base_label)
            self.setToolTip("")

    def _handle_click(self) -> None:
        # Requirement: when hovered, clicking removes the tag definition.
        if self._hovered and callable(self._on_remove):
            self._on_remove()


class _AddChipButton(QPushButton):
    def __init__(self, on_add, parent=None) -> None:
        super().__init__("+", parent)
        self._on_add = on_add
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: callable(self._on_add) and self._on_add())


class ManageGameTagsDialog(QDialog):
    """Manage custom tags (create, recolor, delete). Built-ins are defined in config.json."""

    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._svc = GameTagsService(self.config)
        self._settings_service = UserSettingsService.get_instance()

        self._load_config()
        self._fixed_size = QSize(self.dialog_width, self.dialog_height)
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._original_custom = self._get_custom_from_settings()
        self._working_custom = [c.copy() for c in self._original_custom]

        self._setup_ui()
        self._apply_styling()
        self._rebuild_builtin_chips()
        self._rebuild_custom_chips()
        self.setWindowTitle("Manage Tags")

    def _load_config(self) -> None:
        dlg_cfg = (self.config.get("ui", {}) or {}).get("dialogs", {}).get("manage_game_tags", {})
        self.dialog_width = int(dlg_cfg.get("width", 680))
        self.dialog_height = int(dlg_cfg.get("height", 520))
        self.bg_color = QColor(*(dlg_cfg.get("background_color", [40, 40, 45])))
        self.border_color = dlg_cfg.get("border_color", [60, 60, 65])
        self.layout_margins = (dlg_cfg.get("layout", {}) or {}).get("margins", [18, 18, 18, 18])
        self.layout_spacing = (dlg_cfg.get("layout", {}) or {}).get("spacing", 10)

        groups_cfg = dlg_cfg.get("groups", {}) or {}
        self.group_contents_margins = groups_cfg.get("contents_margins", [10, 14, 10, 10])
        self.group_spacing = int(groups_cfg.get("spacing", 10))
        self.builtin_chip_container_min_h = int(groups_cfg.get("builtin_chip_container_min_height", 36))
        self.custom_chip_container_min_h = int(groups_cfg.get("custom_chip_container_min_height", 36))

        chips_cfg = dlg_cfg.get("chips", {}) or {}
        self.chip_spacing_multiplier = int(chips_cfg.get("spacing_multiplier", 2))
        self.chip_outer_padding_multiplier = int(chips_cfg.get("outer_padding_multiplier", 1))

        plus_cfg = dlg_cfg.get("plus_chip", {}) or {}
        self.plus_chip_text = str(plus_cfg.get("text", "+"))
        self.plus_chip_bold = bool(plus_cfg.get("bold", True))

        add_dlg_cfg = dlg_cfg.get("add_custom_tag_dialog", {}) or {}
        self.add_dialog_width = int(add_dlg_cfg.get("width", 420))
        self.add_dialog_height = int(add_dlg_cfg.get("height", 140))
        add_layout_cfg = add_dlg_cfg.get("layout", {}) or {}
        self.add_dialog_margins = add_layout_cfg.get("margins", [18, 18, 18, 18])
        self.add_dialog_spacing = int(add_layout_cfg.get("spacing", 10))
        self.add_dialog_row_spacing = int(add_layout_cfg.get("row_spacing", 10))
        swatch_cfg = add_dlg_cfg.get("swatch", {}) or {}
        self.add_swatch_min = int(swatch_cfg.get("min_size", 18))
        self.add_swatch_max = int(swatch_cfg.get("max_size", 22))

        inputs_cfg = dlg_cfg.get("inputs", {}) or {}
        self.input_bg_color = inputs_cfg.get("background_color", [30, 30, 35])
        self.input_border_color = inputs_cfg.get("border_color", [60, 60, 65])
        self.input_font_family = resolve_font_family(inputs_cfg.get("font_family", "Cascadia Mono"))
        self.input_font_size = scale_font_size(inputs_cfg.get("font_size", 11))

        # Chip styling should match the board `GameTagsWidget` exactly.
        board_cfg = (self.config.get("ui", {}) or {}).get("panels", {}).get("main", {}).get("board", {})
        tags_cfg = board_cfg.get("game_tags_widget", {}) if isinstance(board_cfg, dict) else {}
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

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*self.layout_margins)
        main_layout.setSpacing(self.layout_spacing)

        # Built-in tags as chips
        builtin_group = QGroupBox("Built-in tags")
        builtin_layout = QVBoxLayout()
        builtin_layout.setContentsMargins(*self.group_contents_margins)
        builtin_layout.setSpacing(self.group_spacing)
        builtin_group.setLayout(builtin_layout)

        self.builtin_chip_container = QWidget()
        self.builtin_chip_container.setMinimumHeight(self.builtin_chip_container_min_h)
        builtin_layout.addWidget(self.builtin_chip_container)
        main_layout.addWidget(builtin_group)

        # Custom tags (chips with + button)
        custom_group = QGroupBox("Custom tags")
        custom_layout = QVBoxLayout()
        custom_layout.setContentsMargins(*self.group_contents_margins)
        custom_layout.setSpacing(self.group_spacing)
        custom_group.setLayout(custom_layout)

        # Scroll area for chips
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Chip galleries should wrap; horizontal scrollbar is noise.
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.custom_chip_container = QWidget()
        self.custom_chip_container.setMinimumHeight(self.custom_chip_container_min_h)
        self.scroll.setWidget(self.custom_chip_container)
        custom_layout.addWidget(self.scroll, 1)

        main_layout.addWidget(custom_group, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.ok_btn = QPushButton("OK")
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._on_ok)
        self.ok_btn.setDefault(True)
        self.ok_btn.setAutoDefault(True)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.ok_btn)
        main_layout.addLayout(btn_row)

    def _apply_styling(self) -> None:
        pal = self.palette()
        pal.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        bg = [self.bg_color.red(), self.bg_color.green(), self.bg_color.blue()]
        border = self.border_color

        # Unified button styling and sizing (matches other dialogs)
        styles_button_cfg = (self.config.get("ui", {}) or {}).get("styles", {}).get("button", {})
        default_btn_w = int(styles_button_cfg.get("default_width", 120))
        default_btn_h = int(styles_button_cfg.get("default_height", 30))

        buttons = [b for b in self.findChildren(QPushButton) if not isinstance(b, ColorSwatchButton)]
        if buttons:
            StyleManager.style_buttons(
                buttons,
                self.config,
                bg,
                border,
                min_width=default_btn_w,
                min_height=default_btn_h,
            )

        groups = list(self.findChildren(QGroupBox))
        if groups:
            StyleManager.style_group_boxes(groups, self.config)

        # Scrollbar styling
        try:
            StyleManager.style_scroll_area(self.scroll, self.config, bg_color=bg, border_color=border, border_radius=3)
        except Exception:
            pass

    def _get_custom_from_settings(self) -> List[dict]:
        settings = self._settings_service.get_settings()
        section = settings.get("game_tags", {}) if isinstance(settings, dict) else {}
        custom = section.get("custom", []) if isinstance(section, dict) else []
        return [c for c in custom if isinstance(c, dict)]

    def _set_custom_to_settings(self, custom: List[dict]) -> None:
        model = self._settings_service.get_model()
        settings = model.get_settings()
        section = settings.get("game_tags", {})
        if not isinstance(section, dict):
            section = {}
        section["custom"] = custom
        updated = settings.copy()
        updated["game_tags"] = section
        model.update_from_dict(updated)

    def _pick_color_for_swatch(self, swatch: ColorSwatchButton) -> None:
        chosen = QColorDialog.getColor(swatch.get_color(), self, "Select tag color")
        if chosen.isValid():
            swatch.set_color(chosen)

    def _pick_color_for_custom_index(self, idx: int, swatch: ColorSwatchButton) -> None:
        chosen = QColorDialog.getColor(swatch.get_color(), self, "Select tag color")
        if not chosen.isValid():
            return
        swatch.set_color(chosen)
        if 0 <= idx < len(self._working_custom):
            self._working_custom[idx]["color"] = [int(chosen.red()), int(chosen.green()), int(chosen.blue())]

    def _rebuild_builtin_chips(self) -> None:
        # Clear existing chips
        for child in self.builtin_chip_container.findChildren(QPushButton):
            child.setParent(None)
            child.deleteLater()

        defs = self._svc.get_definitions()
        builtins = [d for d in defs if d.builtin]

        # Simple manual wrap layout inside container
        gap = max(0, int(self.flow_spacing))
        spacing = max(1, int(gap * self.chip_spacing_multiplier))
        outer_pad = max(0, int(spacing * self.chip_outer_padding_multiplier))
        x = outer_pad
        y = outer_pad
        line_h = 0
        # Use actual available width (avoid clipping/truncation on first show).
        try:
            max_w = int(self.builtin_chip_container.parentWidget().contentsRect().width())
        except Exception:
            max_w = 0
        if max_w <= 1:
            max_w = int(self.builtin_chip_container.width())
        if max_w <= 1:
            max_w = int(self.dialog_width - 60)
        max_w = max(1, int(max_w - outer_pad))
        for d in builtins:
            chip = QPushButton(d.name, self.builtin_chip_container)
            chip.setEnabled(False)
            chip.setCursor(Qt.CursorShape.ArrowCursor)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._style_chip(chip, QColor(*d.color), removable=False)
            chip.adjustSize()
            w = max(chip.sizeHint().width(), 40)
            h = max(chip.sizeHint().height(), 22)
            w = min(w, max_w)
            if x > outer_pad and x + w > max_w + outer_pad:
                x = outer_pad
                y += line_h + spacing
                line_h = 0
            chip.setGeometry(int(x), int(y), int(w), int(h))
            chip.show()
            x += w + spacing
            line_h = max(line_h, h)

        self.builtin_chip_container.setMinimumHeight(int(y + line_h + outer_pad))
        self.builtin_chip_container.updateGeometry()
        self.builtin_chip_container.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rebuild_builtin_chips()
        self._rebuild_custom_chips()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # On macOS, the scroll viewport width can be wrong until after the dialog is shown.
        # Rebuild once on the next tick so chip geometry uses the final layout width.
        QTimer.singleShot(0, lambda: (self._rebuild_builtin_chips(), self._rebuild_custom_chips()))

    def _rebuild_custom_chips(self) -> None:
        for child in self.custom_chip_container.findChildren(QPushButton):
            child.setParent(None)
            child.deleteLater()

        gap = max(0, int(self.flow_spacing))
        spacing = max(1, int(gap * self.chip_spacing_multiplier))
        outer_pad = max(0, int(spacing * self.chip_outer_padding_multiplier))
        x = outer_pad
        y = outer_pad
        line_h = 0
        # Ensure the chip container follows the scroll viewport width so manual geometry is visible immediately.
        viewport_w = 0
        try:
            viewport_w = int(self.scroll.viewport().width())
        except Exception:
            viewport_w = 0
        if viewport_w <= 1:
            viewport_w = int(self.dialog_width - 60)
        self.custom_chip_container.setMinimumWidth(viewport_w)
        self.custom_chip_container.setFixedWidth(viewport_w)
        max_w = max(1, int(viewport_w - outer_pad))

        def _add_chip(widget: QPushButton) -> None:
            nonlocal x, y, line_h
            widget.adjustSize()
            # Some fixed-size buttons (like the + chip) may report small/odd sizeHints;
            # include current width/height to avoid 0-width placement overlap.
            w = max(widget.sizeHint().width(), widget.minimumWidth(), widget.width(), 32)
            h = max(widget.sizeHint().height(), widget.minimumHeight(), widget.height(), 22)
            w = min(w, max_w)
            if x > outer_pad and x + w > max_w + outer_pad:
                x = outer_pad
                y += line_h + spacing
                line_h = 0
            widget.setGeometry(int(x), int(y), int(w), int(h))
            widget.show()
            x += w + spacing
            line_h = max(line_h, h)

        for item in self._working_custom:
            name = self._sanitize_name(str(item.get("name", "")))
            if not name:
                continue
            col = item.get("color", [120, 120, 120])
            try:
                rgb = (int(col[0]), int(col[1]), int(col[2])) if isinstance(col, list) and len(col) == 3 else (120, 120, 120)
            except Exception:
                rgb = (120, 120, 120)

            chip = _RemovableChipButton(
                name,
                on_remove=lambda n=name: self._remove_custom_by_name(n),
                parent=self.custom_chip_container,
            )
            self._style_chip(chip, QColor(*rgb), removable=True)
            _add_chip(chip)

        plus = _AddChipButton(self._open_add_custom_dialog, self.custom_chip_container)
        plus.setText(self.plus_chip_text)
        plus.setToolTip("Add a new tag")
        plus.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Render "+" using the same chip styling as everywhere else (crisp + consistent).
        plus.setMinimumHeight(int(self.chip_min_height))
        try:
            f = plus.font()
            f.setBold(bool(self.plus_chip_bold))
            f.setPointSize(max(11, int(self.chip_font_size)))
            plus.setFont(f)
        except Exception:
            pass
        # Use a neutral chip background but keep the standard hover behavior.
        neutral = QColor(95, 95, 100)
        try:
            ubg = getattr(self, "chip_unmanaged_bg", None)
            if isinstance(ubg, list) and len(ubg) == 3:
                neutral = QColor(int(ubg[0]), int(ubg[1]), int(ubg[2]))
        except Exception:
            pass
        self._style_chip(plus, neutral, removable=True)
        _add_chip(plus)

        self.custom_chip_container.setMinimumHeight(int(y + line_h + outer_pad))
        self.custom_chip_container.updateGeometry()
        self.custom_chip_container.update()

    def _sanitize_name(self, name: str) -> str:
        name = (name or "").strip()
        if ";" in name:
            name = name.replace(";", "").strip()
        return name

    def _remove_custom_by_name(self, name: str) -> None:
        key = self._sanitize_name(name).casefold()
        self._working_custom = [
            item for item in self._working_custom
            if self._sanitize_name(str(item.get("name", ""))).casefold() != key
        ]
        self._rebuild_custom_chips()

    def _upsert_custom(self, name: str, rgb: Tuple[int, int, int]) -> None:
        name = self._sanitize_name(name)
        if not name:
            return
        key = name.casefold()
        color = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
        replaced = False
        new_custom: List[dict] = []
        for item in self._working_custom:
            existing = self._sanitize_name(str(item.get("name", "")))
            if existing.casefold() == key:
                new_custom.append({"name": name, "color": color})
                replaced = True
            else:
                new_custom.append(item)
        if not replaced:
            new_custom.append({"name": name, "color": color})
        self._working_custom = new_custom
        self._rebuild_custom_chips()

    def _open_add_custom_dialog(self) -> None:
        dlg = _AddCustomTagDialog(self.config, self, initial_color=QColor(120, 120, 120))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = dlg.get_name()
        col = dlg.get_color()
        self._upsert_custom(name, (col.red(), col.green(), col.blue()))

    def _style_chip(self, chip: QPushButton, color: QColor, *, removable: bool) -> None:
        # Match `GameTagsWidget._make_chip` behavior for styling.
        chip.setMinimumHeight(int(self.chip_min_height))
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        chip.setFlat(True)

        font = QFont(self.chip_font_family, self.chip_font_size)
        if self.chip_font_weight in ("bold", "700", "800", "900"):
            font.setBold(True)
        chip.setFont(font)

        bg = f"rgb({color.red()}, {color.green()}, {color.blue()})"
        text = "rgb(15, 15, 18)" if (0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()) > 150 else "rgb(245, 245, 245)"
        pad_v = int(self.chip_padding[0]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 1 else 2
        pad_h = int(self.chip_padding[1]) if isinstance(self.chip_padding, list) and len(self.chip_padding) >= 2 else 8
        # Removable chips need a bit more room on the right for the hover ✕ indicator.
        if removable:
            pad_h += 6
        try:
            if removable and isinstance(chip, _RemovableChipButton):
                text_w = chip.fontMetrics().horizontalAdvance(f"{chip.get_base_label()}  ✕")
            else:
                text_w = chip.fontMetrics().horizontalAdvance(chip.text())
        except Exception:
            text_w = len(chip.text()) * 7
        chip.setMinimumWidth(int(text_w + 2 * pad_h + 8))

        hover_rgba = self.chip_hover_bg if isinstance(self.chip_hover_bg, list) and len(self.chip_hover_bg) == 4 else [255, 255, 255, 18]
        hover = (
            "QPushButton:hover {"
            f"  background-color: rgba({int(hover_rgba[0])}, {int(hover_rgba[1])}, {int(hover_rgba[2])}, {int(hover_rgba[3])});"
            "}"
            if removable
            else ""
        )
        chip.setStyleSheet(
            "QPushButton {"
            f"  background-color: {bg};"
            f"  color: {text};"
            f"  border-radius: {int(self.chip_border_radius)}px;"
            f"  padding: {pad_v}px {pad_h}px;"
            "}"
            "QPushButton:disabled {"
            f"  background-color: {bg};"
            f"  color: {text};"
            "}"
            + hover
        )

    def _on_ok(self) -> None:
        # Clean up empties and duplicates case-insensitively
        cleaned: List[dict] = []
        seen = set()
        for item in self._working_custom:
            name = self._sanitize_name(str(item.get("name", "")))
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            col = item.get("color", [120, 120, 120])
            if not (isinstance(col, list) and len(col) == 3):
                col = [120, 120, 120]
            cleaned.append({"name": name, "color": [int(col[0]), int(col[1]), int(col[2])]})
        self._set_custom_to_settings(cleaned)
        self.accept()


class _AddCustomTagDialog(QDialog):
    def __init__(self, config: Dict[str, Any], parent=None, initial_color: QColor | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._color = initial_color or QColor(120, 120, 120)

        self.setWindowTitle("Add Tag")
        self.setModal(True)

        styles_button_cfg = (self.config.get("ui", {}) or {}).get("styles", {}).get("button", {})
        default_btn_w = int(styles_button_cfg.get("default_width", 120))
        default_btn_h = int(styles_button_cfg.get("default_height", 30))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*getattr(parent, "add_dialog_margins", [18, 18, 18, 18]))
        layout.setSpacing(int(getattr(parent, "add_dialog_spacing", 10)))

        row = QHBoxLayout()
        row.setSpacing(int(getattr(parent, "add_dialog_row_spacing", 10)))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Tag name…")
        # Slightly larger swatch, but never taller than the input.
        input_h = max(18, int(self.name_edit.sizeHint().height()))
        sw_min = int(getattr(parent, "add_swatch_min", 18))
        sw_max = int(getattr(parent, "add_swatch_max", 22))
        swatch_size = max(sw_min, min(sw_max, input_h))
        self.swatch = ColorSwatchButton(self._color, swatch_size)
        self.swatch.clicked.connect(self._pick_color)
        row.addWidget(self.swatch, 0)
        row.addWidget(self.name_edit, 1)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.setAutoDefault(True)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.ok_btn)
        layout.addLayout(btn_row)

        # Styling
        bg_color = [40, 40, 45]
        border_color = [60, 60, 65]
        try:
            dlg_cfg = (self.config.get("ui", {}) or {}).get("dialogs", {}).get("manage_game_tags", {})
            bg_color = list(dlg_cfg.get("background_color", bg_color))
            border_color = list(dlg_cfg.get("border_color", border_color))
        except Exception:
            pass

        # Ensure the dialog draws its background (notably required on macOS).
        try:
            self.setAutoFillBackground(True)
            pal = self.palette()
            pal.setColor(self.backgroundRole(), QColor(int(bg_color[0]), int(bg_color[1]), int(bg_color[2])))
            self.setPalette(pal)
        except Exception:
            pass

        StyleManager.style_buttons(
            [self.cancel_btn, self.ok_btn],
            self.config,
            bg_color,
            border_color,
            min_width=default_btn_w,
            min_height=default_btn_h,
        )
        StyleManager.style_line_edits([self.name_edit], self.config)

        w = int(getattr(parent, "add_dialog_width", 420))
        h = int(getattr(parent, "add_dialog_height", 140))
        self.setFixedSize(w, h)

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(self._color, self, "Select tag color")
        if chosen.isValid():
            self._color = chosen
            self.swatch.set_color(chosen)

    def _on_ok(self) -> None:
        name = (self.name_edit.text() or "").strip()
        if ";" in name:
            name = name.replace(";", "").strip()
        if not name:
            return
        self.accept()

    def get_name(self) -> str:
        return (self.name_edit.text() or "").strip()

    def get_color(self) -> QColor:
        return self._color
