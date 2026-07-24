"""Floating branch-select overlay for PGN variation navigation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.pgn_variation_path import Path


class BranchSelectOverlay(QFrame):
    """Small popup listing forward branch choices (mainline + sidelines)."""

    choice_activated = pyqtSignal(object)  # Path
    dismissed = pyqtSignal()

    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._choices: List[Tuple[Path, str]] = []
        self._selected = 0
        self._labels: List[QLabel] = []
        self._separator: Optional[QFrame] = None
        self._apply_style(config)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(*self._padding)
        self._layout.setSpacing(self._spacing)

        self.hide()

    def _branch_cfg(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return (
            config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("pgn_notation", {})
            .get("branch_select", {})
        )

    def _apply_style(self, config: Dict[str, Any]) -> None:
        cfg = self._branch_cfg(config)
        colors = cfg.get("colors", {}) if isinstance(cfg.get("colors"), dict) else {}
        self._bg = colors.get("background", [45, 45, 50])
        self._border = colors.get("border", [90, 90, 100])
        self._text = colors.get("text", [220, 220, 220])
        self._muted = colors.get("muted", [160, 160, 165])
        self._selected_bg = colors.get("selected_background", [70, 90, 130])
        self._selected_text = colors.get("selected_text", [240, 240, 240])
        self._radius = int(cfg.get("border_radius", 6))
        self._border_width = int(cfg.get("border_width", 1))
        pad = cfg.get("padding", [8, 10, 8, 10])
        if not isinstance(pad, list) or len(pad) < 4:
            pad = [8, 10, 8, 10]
        self._padding = (int(pad[0]), int(pad[1]), int(pad[2]), int(pad[3]))
        self._spacing = int(cfg.get("row_spacing", 2))
        self._min_width = int(cfg.get("min_width", 96))
        family = resolve_font_family(cfg.get("font_family", "Helvetica Neue"))
        self._font = QFont(family, scale_font_size(cfg.get("font_size", 10)))
        self._font_selected = QFont(family, scale_font_size(cfg.get("font_size", 10)))
        self._font_selected.setBold(True)

        separator = cfg.get("separator", {}) if isinstance(cfg.get("separator"), dict) else {}
        self._separator_enabled = bool(separator.get("enabled", True))
        self._separator_color = separator.get("color", self._border)
        self._separator_height = max(1, int(separator.get("height", 1)))
        sep_margin = separator.get("margin", [4, 4, 4, 4])
        if not isinstance(sep_margin, list) or len(sep_margin) < 4:
            sep_margin = [4, 4, 4, 4]
        self._separator_margin = (
            int(sep_margin[0]),
            int(sep_margin[1]),
            int(sep_margin[2]),
            int(sep_margin[3]),
        )

        self.setStyleSheet(
            f"""
            BranchSelectOverlay {{
                background-color: rgb({self._bg[0]}, {self._bg[1]}, {self._bg[2]});
                border: {self._border_width}px solid rgb({self._border[0]}, {self._border[1]}, {self._border[2]});
                border-radius: {self._radius}px;
            }}
            """
        )

    def refresh_style(self, config: Dict[str, Any]) -> None:
        self._apply_style(config)
        self._layout.setContentsMargins(*self._padding)
        self._layout.setSpacing(self._spacing)
        if self.isVisible():
            self._rebuild_labels()

    def is_open(self) -> bool:
        return self.isVisible() and bool(self._choices)

    def selected_path(self) -> Optional[Path]:
        if not self._choices:
            return None
        idx = max(0, min(self._selected, len(self._choices) - 1))
        return self._choices[idx][0]

    def show_choices(
        self,
        choices: Sequence[Tuple[Path, str]],
        *,
        anchor_global=None,
        selected_index: int = 0,
    ) -> None:
        self._choices = [(tuple(path), str(san)) for path, san in choices]
        if not self._choices:
            self.hide_overlay()
            return
        self._selected = max(0, min(int(selected_index), len(self._choices) - 1))
        self._rebuild_labels()
        self.adjustSize()
        if anchor_global is not None:
            self.move(anchor_global)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        # Ensure arrow keys reach this popup even when the PGN pane keeps focus (common on Windows).
        self.grabKeyboard()

    def hide_overlay(self) -> None:
        was_visible = self.isVisible()
        if was_visible:
            self.releaseKeyboard()
        self.hide()
        self._choices = []
        self._selected = 0
        self._clear_labels()
        if was_visible:
            self.dismissed.emit()

    def move_selection(self, delta: int) -> None:
        if not self._choices:
            return
        self._selected = (self._selected + int(delta)) % len(self._choices)
        # Update styles in place — do not rebuild widgets (avoids flicker).
        self._refresh_selection_styles()

    def activate_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        self.hide_overlay()
        self.choice_activated.emit(path)

    def _clear_labels(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._labels = []
        self._separator = None

    def _style_label(self, label: QLabel, index: int) -> None:
        selected = index == self._selected
        label.setFont(self._font_selected if selected else self._font)
        if selected:
            bg = self._selected_bg
            fg = self._selected_text
        else:
            bg = self._bg
            fg = self._text if index == 0 else self._muted
        label.setStyleSheet(
            f"""
            QLabel {{
                color: rgb({fg[0]}, {fg[1]}, {fg[2]});
                background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});
                border-radius: {max(2, self._radius - 2)}px;
                padding: 3px 8px;
            }}
            """
        )

    def _refresh_selection_styles(self) -> None:
        for i, label in enumerate(self._labels):
            self._style_label(label, i)

    def _make_separator(self) -> QFrame:
        mt, mr, mb, ml = self._separator_margin
        line = QFrame()
        line.setFrameShape(QFrame.Shape.NoFrame)
        line.setFixedHeight(self._separator_height + mt + mb)
        c = self._separator_color
        line.setStyleSheet(
            f"""
            QFrame {{
                background-color: transparent;
                border: none;
                border-top: {self._separator_height}px solid rgb({c[0]}, {c[1]}, {c[2]});
                margin: {mt}px {mr}px {mb}px {ml}px;
            }}
            """
        )
        return line

    def _rebuild_labels(self) -> None:
        self.setUpdatesEnabled(False)
        try:
            self._clear_labels()
            for i, (_path, san) in enumerate(self._choices):
                label = QLabel(san)
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.setMinimumWidth(self._min_width)
                self._style_label(label, i)
                label.mousePressEvent = self._make_click_handler(i)  # type: ignore[method-assign]
                self._layout.addWidget(label)
                self._labels.append(label)

                if i == 0 and self._separator_enabled and len(self._choices) > 1:
                    self._separator = self._make_separator()
                    self._layout.addWidget(self._separator)
            self.adjustSize()
        finally:
            self.setUpdatesEnabled(True)

    def _make_click_handler(self, index: int) -> Callable[[QMouseEvent], None]:
        def _handler(event: QMouseEvent) -> None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._selected = index
                self.activate_selected()

        return _handler

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.move_selection(-1 if key == Qt.Key.Key_Up else 1)
            event.accept()
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activate_selected()
            event.accept()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Escape):
            self.hide_overlay()
            event.accept()
            return
        super().keyPressEvent(event)
