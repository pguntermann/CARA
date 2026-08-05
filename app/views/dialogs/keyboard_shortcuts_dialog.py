"""Keyboard Shortcuts dialog — view and edit application bindings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter, QResizeEvent, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.keyboard_shortcuts_controller import (
    KeyboardShortcutsController,
    ShortcutConflict,
)
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.keyboard_shortcuts_catalog import ShortcutEntry, shortcut_from_key_event
from app.views.dialogs.confirmation_dialog import ConfirmationDialog
from app.views.style import StyleManager


class _ShortcutCaptureOverlay(QWidget):
    """Dimmed overlay card prompting for a new shortcut key."""

    shortcut_entered = pyqtSignal(str)
    shortcut_cleared = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, config: Dict[str, Any], parent: QWidget) -> None:
        super().__init__(parent)
        self.setVisible(False)
        self.config = config
        self._binding_id: Optional[str] = None
        self._action_label = ""
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._load_config()
        self._setup_ui()
        self._apply_styling()

    def _load_config(self) -> None:
        dialog_config = (
            self.config.get("ui", {}).get("dialogs", {}).get("keyboard_shortcuts", {})
        )
        overlay_cfg = dialog_config.get("overlay", {})
        self.overlay_dim = overlay_cfg.get("dim_color", [0, 0, 0, 150])
        self.card_bg = QColor(
            *overlay_cfg.get(
                "card_background_color",
                dialog_config.get("background_color", [40, 40, 45]),
            )
        )
        self.card_border = QColor(
            *overlay_cfg.get(
                "card_border_color",
                dialog_config.get("border_color", [60, 60, 65]),
            )
        )
        self.card_radius = int(overlay_cfg.get("card_border_radius", 8))
        self.card_width = int(overlay_cfg.get("card_width", 420))
        self.card_margins = overlay_cfg.get("card_margins", [28, 26, 28, 24])
        self.card_spacing = int(overlay_cfg.get("card_spacing", 14))

        self.overlay_title = overlay_cfg.get("title", "Set shortcut")
        self.overlay_prompt = overlay_cfg.get(
            "prompt", 'Press a new key combination for “{action}”.'
        )
        self.overlay_hint = overlay_cfg.get(
            "hint", "Esc removes the shortcut · click outside to cancel"
        )

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )
        self.title_font_size = scale_font_size(
            overlay_cfg.get("title_font_size", dialog_config.get("font_size", 14))
        )
        self.prompt_font_size = scale_font_size(
            overlay_cfg.get(
                "prompt_font_size", labels_config.get("font_size", 11)
            )
        )
        self.hint_font_size = scale_font_size(
            overlay_cfg.get(
                "hint_font_size",
                dialog_config.get("status", {}).get("font_size", 10),
            )
        )
        self.title_text_color = overlay_cfg.get(
            "title_text_color",
            dialog_config.get("text_color", labels_config.get("text_color", [240, 240, 240])),
        )
        self.prompt_text_color = overlay_cfg.get(
            "prompt_text_color",
            labels_config.get("text_color", [200, 200, 200]),
        )
        self.hint_text_color = overlay_cfg.get(
            "hint_text_color",
            dialog_config.get("status", {}).get("text_color", [150, 150, 150]),
        )

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("keyboard_shortcuts_capture_card")
        self.card.setFixedWidth(self.card_width)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(
            int(self.card_margins[0]),
            int(self.card_margins[1]),
            int(self.card_margins[2]),
            int(self.card_margins[3]),
        )
        card_layout.setSpacing(self.card_spacing)

        self.title_label = QLabel(self.overlay_title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        card_layout.addWidget(self.title_label)

        self.prompt_label = QLabel()
        self.prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt_label.setWordWrap(True)
        card_layout.addWidget(self.prompt_label)

        self.hint_label = QLabel(self.overlay_hint)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        card_layout.addWidget(self.hint_label)

        root.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)

    def _apply_styling(self) -> None:
        self.card.setStyleSheet(
            f"#keyboard_shortcuts_capture_card {{"
            f"background-color: rgb({self.card_bg.red()}, {self.card_bg.green()}, {self.card_bg.blue()});"
            f"border: 1px solid rgb({self.card_border.red()}, {self.card_border.green()}, {self.card_border.blue()});"
            f"border-radius: {self.card_radius}px;"
            f"}}"
        )
        self.title_label.setStyleSheet(
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.title_font_size}pt;"
            f"font-weight: bold;"
            f"color: rgb({self.title_text_color[0]}, {self.title_text_color[1]}, {self.title_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        self.prompt_label.setStyleSheet(
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.prompt_font_size}pt;"
            f"color: rgb({self.prompt_text_color[0]}, {self.prompt_text_color[1]}, {self.prompt_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        self.hint_label.setStyleSheet(
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.hint_font_size}pt;"
            f"color: rgb({self.hint_text_color[0]}, {self.hint_text_color[1]}, {self.hint_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        dim = self.overlay_dim if isinstance(self.overlay_dim, list) else [0, 0, 0, 150]
        alpha = int(dim[3]) if len(dim) > 3 else 150
        painter.fillRect(
            self.rect(),
            QColor(int(dim[0]), int(dim[1]), int(dim[2]), alpha),
        )
        super().paintEvent(event)

    def show_for(self, entry: ShortcutEntry) -> None:
        self._binding_id = entry.binding_id
        self._action_label = entry.action
        self.prompt_label.setText(self.overlay_prompt.format(action=entry.action))
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        self.grabKeyboard()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def binding_id(self) -> Optional[str]:
        return self._binding_id

    def hide_overlay(self) -> None:
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._binding_id = None
        self._action_label = ""
        self.hide()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Click on dimmed area (outside card) cancels without changing.
            if not self.card.geometry().contains(event.position().toPoint()):
                self.hide_overlay()
                self.cancelled.emit()
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide_overlay()
            self.shortcut_cleared.emit()
            event.accept()
            return

        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            event.accept()
            return

        shortcut = shortcut_from_key_event(event)
        if not shortcut:
            event.accept()
            return

        self.hide_overlay()
        self.shortcut_entered.emit(shortcut)
        event.accept()


class KeyboardShortcutsDialog(QDialog):
    """Themed dialog for viewing and editing keyboard shortcuts."""

    COL_CATEGORY = 0
    COL_ACTION = 1
    COL_SHORTCUT = 2

    def __init__(
        self,
        config: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.controller = KeyboardShortcutsController(self)
        self._all_entries: List[ShortcutEntry] = []
        self._capture_overlay: Optional[_ShortcutCaptureOverlay] = None
        self._pending_binding_id: Optional[str] = None

        self._load_config()
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(self.dialog_minimum_width, self.dialog_minimum_height)
        self.resize(self.dialog_width, self.dialog_height)

        self._setup_ui()
        self._apply_styling()
        self._reload_entries()

    def _load_config(self) -> None:
        dialog_config = (
            self.config.get("ui", {}).get("dialogs", {}).get("keyboard_shortcuts", {})
        )
        self._dialog_config = dialog_config

        self.dialog_width = int(dialog_config.get("width", 780))
        self.dialog_height = int(dialog_config.get("height", 560))
        self.dialog_minimum_width = int(dialog_config.get("minimum_width", 620))
        self.dialog_minimum_height = int(dialog_config.get("minimum_height", 420))
        self.bottom_button_top_padding = int(
            dialog_config.get("bottom_button_top_padding", 50)
        )

        self.bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.border_color = dialog_config.get("border_color", [60, 60, 65])
        self.text_color = dialog_config.get("text_color", [200, 200, 200])
        self.font_size = scale_font_size(dialog_config.get("font_size", 11))

        layout_config = dialog_config.get("layout", {})
        self.layout_spacing = int(layout_config.get("spacing", 10))
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])

        filter_config = dialog_config.get("filter", {})
        self.filter_placeholder = filter_config.get(
            "placeholder", "Filter by category, action, or shortcut…"
        )
        self.filter_min_height = int(filter_config.get("minimum_height", 28))

        status_config = dialog_config.get("status", {})
        self.status_font_size = scale_font_size(
            status_config.get("font_size", dialog_config.get("font_size", 11))
        )
        self.status_text_color = status_config.get("text_color", self.text_color)

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )
        self.label_text_color = labels_config.get("text_color", self.text_color)

        inputs_config = dialog_config.get("inputs", {})
        self.input_font_family = resolve_font_family(
            inputs_config.get("font_family", "Helvetica Neue")
        )
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = inputs_config.get("text_color", [240, 240, 240])
        self.input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        self.input_border_color = inputs_config.get("border_color", [60, 60, 65])
        self.input_focus_border_color = inputs_config.get(
            "focus_border_color", [70, 90, 130]
        )
        self.input_border_radius = int(inputs_config.get("border_radius", 3))
        self.input_padding = inputs_config.get("padding", [8, 6])

        table_config = dialog_config.get("table", {})
        self.table_bg_color = table_config.get("background_color", [30, 30, 35])
        self.table_text_color = table_config.get("text_color", [240, 240, 240])
        self.table_border_color = table_config.get("border_color", [60, 60, 65])
        self.table_border_radius = int(table_config.get("border_radius", 3))
        self.table_header_bg = table_config.get(
            "header_background_color", [45, 45, 50]
        )
        self.table_header_text = table_config.get(
            "header_text_color", [200, 200, 200]
        )
        self.table_item_padding = int(table_config.get("item_padding", 5))
        self.table_header_padding = int(table_config.get("header_padding", 5))
        self.table_category_width = int(table_config.get("category_column_width", 140))
        self.table_shortcut_width = int(table_config.get("shortcut_column_width", 160))
        self.table_row_height = int(table_config.get("row_height", 28))
        self.table_alternating = bool(table_config.get("alternating_row_colors", True))
        self.table_alternate_bg = table_config.get(
            "alternate_background_color",
            [
                max(0, self.table_bg_color[0] + 8),
                max(0, self.table_bg_color[1] + 8),
                max(0, self.table_bg_color[2] + 8),
            ],
        )
        self.table_selection_bg = table_config.get(
            "selection_background_color",
            [
                min(255, self.bg_color[0] + 20),
                min(255, self.bg_color[1] + 20),
                min(255, self.bg_color[2] + 20),
            ],
        )
        self.table_selection_text = table_config.get(
            "selection_text_color", self.table_text_color
        )
        self.table_hover_bg = table_config.get(
            "hover_background_color", self.table_selection_bg
        )
        self.table_hover_text = table_config.get(
            "hover_text_color", self.table_text_color
        )
        self.table_shortcut_font_family = resolve_font_family(
            table_config.get("shortcut_font_family", "Cascadia Mono")
        )
        self.table_empty_display = table_config.get("empty_shortcut_display", "—")
        _hb = table_config.get("header_section_border", True)
        if isinstance(_hb, str):
            self.table_header_section_border = _hb.strip().lower() in (
                "true",
                "1",
                "yes",
                "on",
            )
        else:
            self.table_header_section_border = bool(_hb)

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 120))
        self.button_height = int(buttons_config.get("height", 30))
        self.button_spacing = int(buttons_config.get("spacing", 10))
        self.button_border_color = buttons_config.get(
            "border_color", self.border_color
        )
        self.action_button_width = int(
            buttons_config.get("action_width", buttons_config.get("width", 140))
        )

    def _setup_ui(self) -> None:
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(self.bg_color[0], self.bg_color[1], self.bg_color[2]),
        )
        self.setPalette(palette)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.layout_spacing)
        margins = self.layout_margins
        main_layout.setContentsMargins(
            int(margins[0]), int(margins[1]), int(margins[2]), int(margins[3])
        )

        filter_row = QHBoxLayout()
        filter_row.setSpacing(self.layout_spacing)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.filter_placeholder)
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumHeight(self.filter_min_height)
        self.filter_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.filter_edit)
        main_layout.addLayout(filter_row)

        self.status_label = QLabel()
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Category", "Action", "Shortcut"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(self.table_alternating)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_ACTION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_SHORTCUT, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_CATEGORY, self.table_category_width)
        self.table.setColumnWidth(self.COL_SHORTCUT, self.table_shortcut_width)

        v_header = self.table.verticalHeader()
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        v_header.setDefaultSectionSize(self.table_row_height)

        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.table, 1)

        main_layout.addSpacing(self.bottom_button_top_padding)

        button_row = QHBoxLayout()
        button_row.setSpacing(self.button_spacing)

        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.clicked.connect(self._clear_all)
        button_row.addWidget(self.clear_all_button)

        self.restore_button = QPushButton("Restore Defaults")
        self.restore_button.clicked.connect(self._restore_defaults)
        button_row.addWidget(self.restore_button)

        button_row.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        main_layout.addLayout(button_row)

        self.filter_edit.setFocus()

    def _ensure_capture_overlay(self) -> _ShortcutCaptureOverlay:
        if self._capture_overlay is None:
            overlay = _ShortcutCaptureOverlay(self.config, self)
            overlay.shortcut_entered.connect(self._on_overlay_shortcut_entered)
            overlay.shortcut_cleared.connect(self._on_overlay_shortcut_cleared)
            overlay.cancelled.connect(self._on_overlay_cancelled)
            self._capture_overlay = overlay
        return self._capture_overlay

    def _is_capturing(self) -> bool:
        return bool(
            self._capture_overlay is not None and self._capture_overlay.isVisible()
        )

    def _apply_styling(self) -> None:
        bg = [int(self.bg_color[0]), int(self.bg_color[1]), int(self.bg_color[2])]
        border = [
            int(self.button_border_color[0]),
            int(self.button_border_color[1]),
            int(self.button_border_color[2]),
        ]

        StyleManager.style_buttons(
            [self.clear_all_button, self.restore_button],
            self.config,
            bg,
            border,
            min_width=self.action_button_width,
            min_height=self.button_height,
        )
        StyleManager.style_buttons(
            [self.close_button],
            self.config,
            bg,
            border,
            min_width=self.button_width,
            min_height=self.button_height,
        )

        StyleManager.style_line_edits(
            [self.filter_edit],
            self.config,
            text_color=self.input_text_color,
            font_family=self.input_font_family,
            font_size=self.input_font_size,
            bg_color=self.input_bg_color,
            border_color=self.input_border_color,
            focus_border_color=self.input_focus_border_color,
            border_radius=self.input_border_radius,
            padding=self.input_padding
            if isinstance(self.input_padding, list)
            else [8, 6],
        )

        status_style = (
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.status_font_size}pt;"
            f"color: rgb({self.status_text_color[0]}, {self.status_text_color[1]}, {self.status_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        self.status_label.setStyleSheet(status_style)

        header_border_qss = (
            f"border: 1px solid rgb({self.table_border_color[0]}, {self.table_border_color[1]}, {self.table_border_color[2]});"
            if self.table_header_section_border
            else "border: none;"
        )
        table_style = (
            f"QTableWidget {{"
            f"background-color: rgb({self.table_bg_color[0]}, {self.table_bg_color[1]}, {self.table_bg_color[2]});"
            f"alternate-background-color: rgb({self.table_alternate_bg[0]}, {self.table_alternate_bg[1]}, {self.table_alternate_bg[2]});"
            f"color: rgb({self.table_text_color[0]}, {self.table_text_color[1]}, {self.table_text_color[2]});"
            f"border: 1px solid rgb({self.table_border_color[0]}, {self.table_border_color[1]}, {self.table_border_color[2]});"
            f"border-radius: {self.table_border_radius}px;"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.font_size}pt;"
            f"gridline-color: rgb({self.table_border_color[0]}, {self.table_border_color[1]}, {self.table_border_color[2]});"
            f"outline: none;"
            f"}}"
            f"QTableWidget::item {{"
            f"padding: {self.table_item_padding}px;"
            f"}}"
            f"QTableWidget::item:selected {{"
            f"background-color: rgb({self.table_selection_bg[0]}, {self.table_selection_bg[1]}, {self.table_selection_bg[2]});"
            f"color: rgb({self.table_selection_text[0]}, {self.table_selection_text[1]}, {self.table_selection_text[2]});"
            f"}}"
            f"QTableWidget::item:hover {{"
            f"background-color: rgb({self.table_hover_bg[0]}, {self.table_hover_bg[1]}, {self.table_hover_bg[2]});"
            f"color: rgb({self.table_hover_text[0]}, {self.table_hover_text[1]}, {self.table_hover_text[2]});"
            f"}}"
            f"QTableWidget::item:selected:hover {{"
            f"background-color: rgb({self.table_selection_bg[0]}, {self.table_selection_bg[1]}, {self.table_selection_bg[2]});"
            f"color: rgb({self.table_selection_text[0]}, {self.table_selection_text[1]}, {self.table_selection_text[2]});"
            f"}}"
            f"QHeaderView::section {{"
            f"background-color: rgb({self.table_header_bg[0]}, {self.table_header_bg[1]}, {self.table_header_bg[2]});"
            f"color: rgb({self.table_header_text[0]}, {self.table_header_text[1]}, {self.table_header_text[2]});"
            f"{header_border_qss}"
            f"padding: {self.table_header_padding}px;"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.font_size}pt;"
            f"}}"
        )
        self.table.setStyleSheet(table_style)
        StyleManager.style_table_scrollbar(
            self.table,
            self.config,
            self.input_bg_color,
            self.input_border_color,
            table_style,
        )

        header = self.table.horizontalHeader()
        if header is not None:
            header_palette = header.palette()
            header_palette.setColor(
                header.backgroundRole(), QColor(*self.table_header_bg)
            )
            header_palette.setColor(
                header.foregroundRole(), QColor(*self.table_header_text)
            )
            header.setPalette(header_palette)
            header.setAutoFillBackground(True)

    def _reload_entries(self) -> None:
        selected_id = self._selected_binding_id()
        self._all_entries = self.controller.list_entries()
        self._apply_filter(self.filter_edit.text(), prefer_binding_id=selected_id)

    def _populate_table(
        self,
        entries: List[ShortcutEntry],
        *,
        prefer_binding_id: Optional[str] = None,
    ) -> None:
        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))

        shortcut_font = QFont(self.table_shortcut_font_family)
        shortcut_font.setPointSizeF(float(self.font_size))
        select_row = -1

        for row, entry in enumerate(entries):
            category_item = QTableWidgetItem(entry.category)
            action_item = QTableWidgetItem(entry.action)
            display = self.controller.display_shortcut(
                entry.shortcut, self.table_empty_display
            )
            shortcut_item = QTableWidgetItem(display)

            for item in (category_item, action_item, shortcut_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, entry)

            shortcut_item.setFont(shortcut_font)
            shortcut_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            self.table.setItem(row, self.COL_CATEGORY, category_item)
            self.table.setItem(row, self.COL_ACTION, action_item)
            self.table.setItem(row, self.COL_SHORTCUT, shortcut_item)
            self.table.setRowHeight(row, self.table_row_height)

            if prefer_binding_id and entry.binding_id == prefer_binding_id:
                select_row = row

        if select_row >= 0:
            self.table.selectRow(select_row)
        self._update_status_label(len(entries), len(self._all_entries))

    def _on_filter_changed(self, text: str) -> None:
        if self._is_capturing():
            return
        self._apply_filter(text)

    def _apply_filter(
        self,
        text: str,
        *,
        prefer_binding_id: Optional[str] = None,
    ) -> None:
        visible = self.controller.filter_entries(self._all_entries, text)
        self._populate_table(visible, prefer_binding_id=prefer_binding_id)

    def _update_status_label(self, visible: int, total: int) -> None:
        self.status_label.setText(
            self.controller.status_summary(
                visible_count=visible,
                total_count=total,
                entries=self._all_entries,
            )
        )

    def _selected_entry(self) -> Optional[ShortcutEntry]:
        rows = (
            self.table.selectionModel().selectedRows()
            if self.table.selectionModel()
            else []
        )
        if not rows:
            return None
        item = self.table.item(rows[0].row(), self.COL_ACTION)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, ShortcutEntry) else None

    def _selected_binding_id(self) -> Optional[str]:
        entry = self._selected_entry()
        return entry.binding_id if entry else None

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        if item is None or self._is_capturing():
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, ShortcutEntry):
            self._start_capture(entry)

    def _start_capture(self, entry: ShortcutEntry) -> None:
        self._pending_binding_id = entry.binding_id
        overlay = self._ensure_capture_overlay()
        overlay.show_for(entry)
        self.filter_edit.setEnabled(False)
        self.clear_all_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.table.setEnabled(False)

    def _end_capture_ui(self) -> None:
        self.filter_edit.setEnabled(True)
        self.clear_all_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.table.setEnabled(True)

    def _on_overlay_shortcut_entered(self, shortcut: str) -> None:
        binding_id = self._pending_binding_id
        self._pending_binding_id = None
        self._end_capture_ui()
        if binding_id:
            self._assign_shortcut(binding_id, shortcut)

    def _on_overlay_shortcut_cleared(self) -> None:
        binding_id = self._pending_binding_id
        self._pending_binding_id = None
        self._end_capture_ui()
        if binding_id:
            self.controller.clear_binding(binding_id)
            self._reload_entries()

    def _on_overlay_cancelled(self) -> None:
        self._pending_binding_id = None
        self._end_capture_ui()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._is_capturing():
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            entry = self._selected_entry()
            if entry is not None:
                self._start_capture(entry)
                event.accept()
                return
        super().keyPressEvent(event)

    def _assign_shortcut(self, binding_id: str, shortcut: str) -> None:
        conflict = self.controller.find_conflict(binding_id, shortcut)
        steal_from = None
        if conflict is not None:
            if not self._confirm_steal(conflict, shortcut):
                self._reload_entries()
                return
            steal_from = conflict.binding_id

        self.controller.set_binding(binding_id, shortcut, steal_from=steal_from)
        self._reload_entries()

    def _confirm_steal(self, conflict: ShortcutConflict, shortcut: str) -> bool:
        dlg = ConfirmationDialog(
            self.config,
            "Shortcut already in use",
            (
                f"“{shortcut}” is already assigned to "
                f"“{conflict.category} → {conflict.action}”.\n\n"
                "Reassign it to the selected action?"
            ),
            self,
        )
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _clear_all(self) -> None:
        dlg = ConfirmationDialog(
            self.config,
            "Clear all shortcuts",
            (
                "Remove every keyboard shortcut?\n\n"
                "You can bring factory defaults back with Restore Defaults."
            ),
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.controller.clear_all()
        self._reload_entries()

    def _restore_defaults(self) -> None:
        dlg = ConfirmationDialog(
            self.config,
            "Restore default shortcuts",
            "Restore all keyboard shortcuts to their factory defaults?",
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.controller.restore_defaults()
        self._reload_entries()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._capture_overlay is not None and self._capture_overlay.isVisible():
            self._capture_overlay.setGeometry(self.rect())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._is_capturing() and self.filter_edit is not None:
            self.filter_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def reject(self) -> None:
        if self._is_capturing() and self._capture_overlay is not None:
            self._capture_overlay.hide_overlay()
            self._on_overlay_cancelled()
            return
        super().reject()
